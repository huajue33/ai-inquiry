"""
分类树进程内缓存。

动机：每次工具调用（search_products / get_latest_prices / 涨跌榜 / 关键词联想等）
都要 `db.query(Category).all()` 全表拉分类再在内存里建树/建路径映射。分类数据由外部
数据同步维护、应用内只读且几乎不变，却被每请求每工具重复查询，纯属浪费。

这里用一个带 TTL 的进程内缓存兜住这些读取。分类通过 sync_products 等外部流程更新，
TTL（默认 60s）足以保证最终一致；缓存的是轻量不可变行对象（CatRow），与 ORM session
解耦，避免 DetachedInstance 之类的问题。
"""
import threading
import time
from dataclasses import dataclass
from typing import Optional

from app.database import SessionLocal
from app.models.product import Category

_CACHE_TTL = 60.0  # 秒
_lock = threading.Lock()
_cache: dict = {"ts": 0.0, "rows": None}


@dataclass(frozen=True)
class CatRow:
    """分类的轻量快照，字段与 Category 中被消费方使用的列对齐。"""
    id: int
    name: str
    parent_id: Optional[int]
    level: int


def get_all_categories(force: bool = False) -> list[CatRow]:
    """返回全部分类（带 TTL 缓存）。

    并发下偶有多个线程同时回源属于可接受的缓存击穿，结果一致、无副作用，
    因此不在查询期间持锁，仅在写回缓存时加锁。
    """
    now = time.monotonic()
    rows = _cache["rows"]
    if not force and rows is not None and (now - _cache["ts"]) < _CACHE_TTL:
        return rows

    db = SessionLocal()
    try:
        cats = db.query(Category).all()
        fresh = [
            CatRow(id=c.id, name=c.name, parent_id=c.parent_id, level=c.level)
            for c in cats
        ]
    finally:
        db.close()

    with _lock:
        _cache["rows"] = fresh
        _cache["ts"] = time.monotonic()
    return fresh


def invalidate() -> None:
    """主动失效缓存（如外部同步分类后想立即生效可调用）。"""
    with _lock:
        _cache["rows"] = None
        _cache["ts"] = 0.0
