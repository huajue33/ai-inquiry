"""
价格查询工具集（LangChain @tool）

设计原则：
1. 单一职责：每个工具只做一件事
2. 数据与表达分离：返回结构化 JSON，由 LLM 措辞、前端渲染
3. ID 是一等公民：搜索归搜索，取数归取数，趋势必须用真实 product_id
4. 权限只在工具层兜底，错误以结构化形式返回
"""
import json
import logging
from contextvars import ContextVar
from datetime import date
from typing import Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.database import SessionLocal
from app.models.product import Product
from app.services.price_service import (
    search_products as search_products_db,
    get_latest_prices_batch,
    get_price_trend,
    get_price_ranking as get_price_ranking_db,
    get_category_price_summary as get_category_price_summary_db,
    group_products_for_clarify,
)
from app.core.permissions import (
    get_current_user_from_context,
    get_allowed_category_ids,
    intersect_category_ids,
)
from app.services.category_cache import get_all_categories, expand_subtree, build_path_map

logger = logging.getLogger(__name__)


# ===== 权限缓存（请求级，由 chat.py 在每次请求开始时 reset） =====
_allowed_ids_cache: ContextVar[Optional[list[int]]] = ContextVar(
    "_allowed_ids_cache", default=None
)
_allowed_ids_loaded: ContextVar[bool] = ContextVar(
    "_allowed_ids_loaded", default=False
)

# 单次请求内 search_products 的调用计数（防止模型反复换词重试导致死循环 / 撞递归上限）
_search_call_count: ContextVar[int] = ContextVar("_search_call_count", default=0)
MAX_SEARCH_CALLS = 5

# batch_quote（多品询价）约束：条目上限 / 每条内联报价的候选上限 / 每条搜索拉取量
BATCH_MAX_ITEMS = 12
BATCH_CANDIDATES_PER_ITEM = 5
BATCH_SEARCH_FETCH = 30


def reset_permission_cache():
    """请求开始时清空请求级缓存与计数（chat.py 调用）"""
    _allowed_ids_cache.set(None)
    _allowed_ids_loaded.set(False)
    _search_call_count.set(0)


def _allowed_ids(db) -> Optional[list[int]]:
    """
    带缓存的权限查询。
    返回 None 表示无限制；返回 [] 表示完全无权限；返回 [...] 表示限定分类。
    """
    if _allowed_ids_loaded.get():
        return _allowed_ids_cache.get()

    user = get_current_user_from_context()
    if user is None:
        # fail-closed：上下文里拿不到用户（理论上不应发生，如 ContextVar 未传播）时，
        # 一律按"无任何权限"处理，绝不放开数据访问（纵深防御）。
        _allowed_ids_loaded.set(True)
        _allowed_ids_cache.set([])
        return []

    ids = get_allowed_category_ids(db, user)
    _allowed_ids_loaded.set(True)
    _allowed_ids_cache.set(ids)
    return ids


# ===== 统一返回格式 =====

def _err(code: str, message: str, **extra) -> str:
    """构造错误响应 JSON 字符串"""
    payload = {"error": code, "message": message}
    payload.update(extra)
    return json.dumps(payload, ensure_ascii=False)


def _ok(data) -> str:
    """构造成功响应 JSON 字符串"""
    return json.dumps(data, ensure_ascii=False, default=str)


# ===== 权限相关 helper =====

def _check_any_permission(db) -> Optional[str]:
    """检查用户是否完全无权限。返回错误 JSON 或 None"""
    if _allowed_ids(db) == []:
        return _err(
            "no_permission",
            "你当前没有任何分类的查看权限，请联系管理员授权",
        )
    return None


def _resolve_category_filter(db, category_name: str):
    """
    根据分类名展开 category_ids 并与用户权限求交集。

    Returns:
        (category_ids, error_str)
        - category_ids=None 表示不限制（无 category 参数 + 用户无限制）
        - category_ids=[1,2,...] 表示限定到这些分类
        - error_str 不为 None 表示分类不存在或无权限
    """
    if not category_name:
        return _allowed_ids(db), None

    # 展开分类树（一次查询所有分类，内存里 BFS）
    all_cats = get_all_categories()
    matched_ids = {c.id for c in all_cats if category_name in c.name}
    if not matched_ids:
        return None, _err(
            "category_not_found",
            f"未找到名为'{category_name}'的分类",
            name=category_name,
        )

    requested = list(expand_subtree(matched_ids))
    final_ids = intersect_category_ids(_allowed_ids(db), requested)

    if final_ids == []:
        return None, _err(
            "permission_denied",
            f"你没有'{category_name}'分类的查看权限，请联系管理员",
            scope="category",
            name=category_name,
        )

    return final_ids, None


def _filter_allowed_products(db, product_ids: list[int]):
    """
    过滤出用户可见的产品 ID。
    Returns: (allowed_pids, denied_pids)
    denied_pids 包含：无权访问 + 不存在的产品。
    """
    allowed_cats = _allowed_ids(db)
    if allowed_cats is None:
        return list(product_ids), []
    if not allowed_cats:
        return [], list(product_ids)

    rows = (
        db.query(Product.product_id, Product.category_id)
        .filter(Product.product_id.in_(product_ids))
        .all()
    )
    pid_to_cat = {pid: cat for pid, cat in rows}

    allowed_set = set(allowed_cats)
    allowed_pids, denied_pids = [], []
    for pid in product_ids:
        cat = pid_to_cat.get(pid)
        if cat is not None and cat in allowed_set:
            allowed_pids.append(pid)
        else:
            denied_pids.append(pid)
    return allowed_pids, denied_pids


def _filter_brand_quality(products, brand: str, quality: str):
    """按品牌（大小写不敏感子串）与品质（子串）过滤产品列表。"""
    if brand:
        products = [p for p in products if brand.lower() in (p.brand or "").lower()]
    if quality:
        products = [p for p in products if quality in (p.quality or "")]
    return products


def _price_overview(priced: list[dict]) -> list[dict]:
    """对一批已报价候选按计价单位聚合区间/均价（用于 batch_quote 的 overview）。

    不同单位（元/斤、元/袋）分别统计，避免混算；按数量降序。
    """
    by_unit: dict[str, list[float]] = {}
    for x in priced:
        by_unit.setdefault(x["unit"] or "", []).append(x["price"])
    out = [
        {"unit": unit, "count": len(vals),
         "min": round(min(vals), 2), "max": round(max(vals), 2),
         "avg": round(sum(vals) / len(vals), 2)}
        for unit, vals in by_unit.items()
    ]
    return sorted(out, key=lambda d: d["count"], reverse=True)


# ============================================================
# Tool 1: 搜索候选商品
# ============================================================

@tool
def search_products(
    keyword: str,
    brand: str = "",
    quality: str = "",
    category: str = "",
    limit: int = 30,
) -> str:
    """搜索候选商品（仅返回产品 meta，不含价格）。这是查询任何产品信息的第一步。

    Args:
        keyword: 关键词或产品 ID。纯数字时按 product_id 精确查找。
        brand: 品牌名过滤（可选）
        quality: 品质过滤，例如"特级""一级"（可选）
        category: 分类名过滤，例如"蔬菜""调味品"（可选）
        limit: 返回数量上限，默认 30，最大 50

    返回 JSON 字段：
    - total: 命中总数（> returned 表示有更多结果未返回）
    - returned: 实际返回数量
    - products: [{product_id, name, brand, quality, spec, category}]
    - groups: 仅在 total > limit 时返回，按核心名分组的概览，引导用户细化
    - hint: 无结果时给出搜索建议
    """
    db = SessionLocal()
    try:
        # 防死循环：单次请求内 search_products 调用次数超限即拒绝，引导模型停止重试
        _count = _search_call_count.get() + 1
        _search_call_count.set(_count)
        if _count > MAX_SEARCH_CALLS:
            return _err(
                "search_limit",
                "本次已多次搜索，请不要再调用搜索工具。基于已有结果回答；"
                "若始终没有匹配商品，直接告知用户'未找到相关商品'。",
            )

        no_perm = _check_any_permission(db)
        if no_perm:
            return no_perm

        limit = min(max(limit, 1), 50)

        category_ids, err = _resolve_category_filter(db, category)
        if err:
            return err

        # 拉候选：如果有 brand/quality 过滤，多拉一些以保证过滤后还够 limit
        fetch_limit = limit * 5 if (brand or quality) else max(limit * 2, 50)
        products = search_products_db(
            db, keyword, category_ids=category_ids, limit=fetch_limit
        )

        products = _filter_brand_quality(products, brand, quality)

        total = len(products)
        if total == 0:
            return _ok({
                "total": 0,
                "returned": 0,
                "products": [],
                "hint": f"未找到包含'{keyword}'的产品。可尝试更短关键词、产品别名，或不带品牌/品质条件",
            })

        top = products[:limit]
        cat_path_map = build_path_map()

        result = {
            "total": total,
            "returned": len(top),
            "products": [
                {
                    "product_id": p.product_id,
                    "name": p.product_name,
                    "brand": p.brand or "",
                    "quality": p.quality or "",
                    "spec": p.spec or "",
                    "category": cat_path_map.get(p.category_id, ""),
                }
                for p in top
            ],
        }

        # 候选过多时附分组概览，让 LLM 引导用户细化
        if total > limit:
            groups = group_products_for_clarify(products, max_groups=6)
            result["groups"] = [
                {
                    "name": g["name"],
                    "count": g["count"],
                    "sample_ids": g["sample_ids"],
                }
                for g in groups
            ]

        return _ok(result)
    finally:
        db.close()


# ============================================================
# Tool 2: 批量查最新价
# ============================================================

@tool
def get_latest_prices(product_ids: list[int], as_of: str = "") -> str:
    """批量查询多个产品在指定日期的有效价格。需要先用 search_products 拿到 product_id。

    生鲜价格不是每天更新。本工具会自动向前回溯：找到 as_of 当天或之前最近的一条
    价格记录，作为"该日的有效价格"返回。LLM 直接用 date 字段当作"今天的价格"
    告知用户即可，无需关心数据是哪一天录入的。

    Args:
        product_ids: 产品 ID 列表，最多 20 个，重复 ID 会去重。
        as_of: 截止日期 YYYY-MM-DD（可选）。不传则默认为今天。

    返回 JSON 字段：
    - prices: [{product_id, name, brand, price, unit, date, quoted_at}]
      - date：本次查询的有效日期（= as_of 或今天）
      - quoted_at：该价格实际录入日期。等于 date 表示当天有更新，
                   早于 date 表示沿用之前报价（生鲜常态，无需特别说明）
    - missing: 找不到价格、不存在或无权访问的 product_id 列表
    """
    db = SessionLocal()
    try:
        no_perm = _check_any_permission(db)
        if no_perm:
            return no_perm

        if not product_ids:
            return _err("invalid_input", "product_ids 不能为空")

        ids = list(dict.fromkeys(product_ids))[:20]

        if as_of:
            try:
                as_of_date = date.fromisoformat(as_of)
            except ValueError:
                return _err("invalid_input", f"as_of 日期格式错误：{as_of}，应为 YYYY-MM-DD")
        else:
            as_of_date = date.today()

        allowed_pids, denied_pids = _filter_allowed_products(db, ids)
        if not allowed_pids:
            return _err(
                "permission_denied",
                "请求的所有产品都无权访问或不存在",
                missing=denied_pids,
            )

        products = (
            db.query(Product)
            .filter(Product.product_id.in_(allowed_pids))
            .all()
        )
        prod_map = {p.product_id: p for p in products}

        # 一次性批量取 as_of 当天或之前最近一条
        price_map = get_latest_prices_batch(db, allowed_pids, as_of_date=as_of_date)

        items = []
        missing = list(denied_pids)
        for pid in allowed_pids:
            p = prod_map.get(pid)
            price = price_map.get(pid)
            if not p or not price:
                missing.append(pid)
                continue
            items.append({
                "product_id": pid,
                "name": p.product_name,
                "brand": p.brand or "",
                "price": float(price.price_value),
                "unit": price.price_unit,
                "date": str(as_of_date),
                "quoted_at": str(price.price_date),
            })

        return _ok({"prices": items, "missing": missing})
    finally:
        db.close()


# ============================================================
# Tool 3: 单品价格走势
# ============================================================

@tool
def get_price_history(product_id: int, days: int = 7) -> str:
    """查询单个产品的历史价格走势（含趋势摘要）。

    必须传入真实的 product_id。如果用户给的是关键词，请先调 search_products
    选出最匹配的一个产品再调用本工具。

    生鲜价格不是每天更新。本工具会自动向前回溯填充：每一天都返回当时的有效报价。
    LLM 直接把 series 当作每日价格序列展示即可。

    Args:
        product_id: 产品 ID
        days: 天数，默认 7，最大 90。窗口为 [today - days + 1, today]

    返回 JSON 字段：
    - product_id, name, unit
    - series: [{date, price}]，连续日期，每天都有有效价格（向前填充）
    - summary: {first, last, min, max, change_pct, trend}
      trend ∈ {"rise", "fall", "flat"}，change_pct 已带正负号
    - hint: 无任何价格数据时的提示
    """
    db = SessionLocal()
    try:
        no_perm = _check_any_permission(db)
        if no_perm:
            return no_perm

        days = min(max(days, 1), 90)

        allowed_pids, _ = _filter_allowed_products(db, [product_id])
        if not allowed_pids:
            return _err(
                "permission_denied",
                f"产品 {product_id} 不存在或无权访问",
                product_id=product_id,
            )

        product = db.query(Product).filter(Product.product_id == product_id).first()
        trend_data = get_price_trend(db, product_id, days)

        if not trend_data:
            return _ok({
                "product_id": product_id,
                "name": product.product_name if product else "",
                "unit": "",
                "series": [],
                "summary": None,
                "hint": f"近 {days} 天暂无价格数据",
            })

        unit = trend_data[0]["price_unit"]
        series = [
            {
                "date": str(item["price_date"]),
                "price": float(item["price_value"]),
            }
            for item in trend_data
        ]

        prices = [s["price"] for s in series]
        first, last = prices[0], prices[-1]
        change_pct = ((last - first) / first * 100) if first > 0 else 0.0
        if change_pct > 0.5:
            trend = "rise"
        elif change_pct < -0.5:
            trend = "fall"
        else:
            trend = "flat"

        return _ok({
            "product_id": product_id,
            "name": product.product_name if product else "",
            "unit": unit,
            "series": series,
            "summary": {
                "first": first,
                "last": last,
                "min": min(prices),
                "max": max(prices),
                "change_pct": round(change_pct, 2),
                "trend": trend,
            },
        })
    finally:
        db.close()


# ============================================================
# Tool 4: 涨跌排行
# ============================================================

@tool
def get_price_ranking(
    direction: str = "rise",
    category: str = "",
    limit: int = 10,
) -> str:
    """查询价格涨跌排行榜（今天 vs 昨天）。

    生鲜价格不是每天更新。本工具会针对每个产品分别向前回溯：
    - 今天的有效价 = 截至今天最近一条记录
    - 昨天的有效价 = 截至昨天最近一条记录
    若两端取到同一条记录（即区间内未发生价格变动），不计入排行。

    Args:
        direction: "rise"（涨幅榜）或 "fall"（跌幅榜），默认 rise
        category: 分类名过滤（可选），例如"蔬菜""调味品"
        limit: 返回数量，默认 10，最大 30

    返回 JSON 字段：
    - direction
    - compare: {from, to}  对比的两个日期（昨天 与 今天）
    - items: [{product_id, name, prev_price, latest_price, change_pct, unit}]
      change_pct 为百分比（已带正负号）
    - hint: items 为空时的说明（例如近期无价格变动）
    """
    db = SessionLocal()
    try:
        no_perm = _check_any_permission(db)
        if no_perm:
            return no_perm

        if direction not in ("rise", "fall"):
            return _err("invalid_input", "direction 必须是 rise 或 fall")

        limit = min(max(limit, 1), 30)

        category_ids, err = _resolve_category_filter(db, category)
        if err:
            return err

        results, compare = get_price_ranking_db(db, direction, category_ids, limit)

        if not results:
            return _ok({
                "direction": direction,
                "compare": {"from": str(compare["from"]), "to": str(compare["to"])},
                "items": [],
                "hint": f"{compare['from']} 至 {compare['to']} 期间无产品发生价格变动",
            })

        items = [
            {
                "product_id": pid,
                "name": name,
                "prev_price": float(prev),
                "latest_price": float(latest),
                "change_pct": round(change_pct, 2),
                "unit": unit,
            }
            for pid, name, prev, latest, change_pct, unit in results
        ]

        return _ok({
            "direction": direction,
            "compare": {
                "from": str(compare["from"]),
                "to": str(compare["to"]),
            },
            "items": items,
        })
    finally:
        db.close()


# ============================================================
# Tool 5: 品类价格概览（聚合，不枚举明细）
# ============================================================

@tool
def get_category_price_summary(category: str, as_of: str = "") -> str:
    """查询某个品类的整体价格概览（区间/均价/中位数 + 品牌分布）。

    适合"X 大概什么价""X 价格行情""X 多少钱"这类**宽泛、品类级**的问题——当某品类下
    商品很多时，用本工具给出聚合概览，而不是逐个枚举商品（避免遗漏与信息过载）。
    若用户想要某个具体商品，再用 search_products + get_latest_prices。

    Args:
        category: 品类/分类名或关键词，例如"土豆""蔬菜""食用油"。必填。
        as_of: 截止日期 YYYY-MM-DD（可选，默认今天）。

    返回 JSON 字段：
    - total_products: 该品类（含子分类）下的商品总数
    - priced_products: 其中有有效报价的商品数
    - by_unit: [{unit, count, min, max, avg, median}]，按计价单位分别统计（不同单位不混算）
    - by_brand: [{brand, count, avg, unit}]，主流单位下按数量排前几的品牌均价
    - hint: 无数据时的说明
    """
    db = SessionLocal()
    try:
        no_perm = _check_any_permission(db)
        if no_perm:
            return no_perm

        if not category or not category.strip():
            return _err("invalid_input", "请提供要查询的品类名，例如'土豆''蔬菜'")

        category_ids, err = _resolve_category_filter(db, category)
        if err:
            return err
        if not category_ids:
            return _err("category_not_found", f"未找到名为'{category}'的分类", name=category)

        if as_of:
            try:
                as_of_date = date.fromisoformat(as_of)
            except ValueError:
                return _err("invalid_input", f"as_of 日期格式错误：{as_of}，应为 YYYY-MM-DD")
        else:
            as_of_date = date.today()

        summary = get_category_price_summary_db(db, category_ids, as_of_date)

        if not summary or summary.get("priced_products", 0) == 0:
            return _ok({
                "category": category,
                "as_of": str(as_of_date),
                "total_products": summary.get("total_products", 0) if summary else 0,
                "priced_products": 0,
                "by_unit": [],
                "by_brand": [],
                "hint": f"'{category}'分类下暂无有效价格数据",
            })

        return _ok({"category": category, "as_of": str(as_of_date), **summary})
    finally:
        db.close()


# ============================================================
# Tool 6: 多品批量询价（询价单）
# ============================================================

class QuoteItem(BaseModel):
    """单个询价条目。"""
    keyword: str = Field(description="商品名或关键词，必填")
    brand: str = Field(default="", description="品牌过滤，可选")
    quality: str = Field(default="", description="品质过滤，如'特级''一级'，可选")
    category: str = Field(default="", description="分类名过滤，如'蔬菜''调味品'，可选")


@tool
def batch_quote(items: list[QuoteItem], as_of: str = "") -> str:
    """一次性查询多个商品的当前价格（询价单 / 多品询价场景）。

    当用户在一句话里询问多个商品价格（如"土豆、白菜、鸡蛋各多少钱"）时用本工具：
    把每个商品填入 items，一次调用返回全部结果，不要逐个调用 search_products。
    单个商品的快速查价也可用本工具（items 只放一个）。

    内部对每条 item 自动走"搜索 → 取价"，按命中情况返回不同 status：
    - ok                命中唯一商品，matched 含价格
    - multi             命中数款（≤5），candidates 列出各自价格供用户挑选
    - overview          命中很多（>5），by_unit 给价格区间/均价，samples 给最便宜的几款
                        代表（含价格）；直接报区间+代表款，细化是可选项而非前置条件
    - not_found         未找到，或找到商品但近期无报价
    - permission_denied / category_not_found  无该分类权限 / 分类不存在

    Args:
        items: 询价条目列表，最多 12 个（超出截断）。
        as_of: 截止日期 YYYY-MM-DD（可选，默认今天）。

    返回 JSON 字段：
    - as_of
    - results: [{keyword, status, matched?, candidates?, by_unit?, samples?, total?, hint?}]
      价格对象：{product_id, name, brand, price, unit, quoted_at}
      by_unit：[{unit, count, min, max, avg}]（overview 时按计价单位统计）
    - summary: 各 status 的计数 + total
    """
    db = SessionLocal()
    try:
        no_perm = _check_any_permission(db)
        if no_perm:
            return no_perm
        if not items:
            return _err("invalid_input", "items 不能为空")

        if as_of:
            try:
                as_of_date = date.fromisoformat(as_of)
            except ValueError:
                return _err("invalid_input", f"as_of 日期格式错误：{as_of}，应为 YYYY-MM-DD")
        else:
            as_of_date = date.today()

        items = items[:BATCH_MAX_ITEMS]

        # 阶段 1：逐条搜索 + 权限过滤；命中的候选一律暂存、汇总待批量取价（不再有"只问不报价"分支）
        plans: list[dict] = []
        price_pids: list[int] = []
        for item in items:
            keyword = (item.keyword or "").strip()
            if not keyword:
                plans.append({"keyword": item.keyword or "", "status": "not_found", "hint": "关键词为空"})
                continue

            category_ids, err = _resolve_category_filter(db, item.category)
            if err:
                e = json.loads(err)
                plans.append({"keyword": keyword, "status": e.get("error", "not_found"),
                              "hint": e.get("message", "")})
                continue

            products = search_products_db(db, keyword, category_ids=category_ids, limit=BATCH_SEARCH_FETCH)
            products = _filter_brand_quality(products, item.brand, item.quality)

            if not products:
                plans.append({"keyword": keyword, "status": "not_found",
                              "hint": f"未找到包含'{keyword}'的商品"})
            else:
                price_pids.extend(p.product_id for p in products)
                plans.append({"keyword": keyword, "total": len(products), "_products": products})

        # 阶段 2：所有候选一次性批量取价
        price_map = get_latest_prices_batch(db, price_pids, as_of_date=as_of_date) if price_pids else {}

        def _priced(p) -> Optional[dict]:
            pr = price_map.get(p.product_id)
            if not pr:
                return None
            return {"product_id": p.product_id, "name": p.product_name, "brand": p.brand or "",
                    "price": float(pr.price_value), "unit": pr.price_unit, "quoted_at": str(pr.price_date)}

        # 阶段 3：回填价格并定 status（多款 → 列表 multi；很多 → 区间概览 overview；都给价）
        results: list[dict] = []
        for plan in plans:
            cand = plan.pop("_products", None)
            if cand is None:
                results.append(plan)
                continue
            priced = [x for x in (_priced(p) for p in cand) if x]
            if not priced:
                results.append({"keyword": plan["keyword"], "status": "not_found",
                                "hint": "找到商品但近期无报价数据"})
            elif len(priced) == 1:
                results.append({"keyword": plan["keyword"], "status": "ok", "matched": priced[0]})
            elif len(priced) <= BATCH_CANDIDATES_PER_ITEM:
                results.append({"keyword": plan["keyword"], "status": "multi", "candidates": priced})
            else:
                cheapest = sorted(priced, key=lambda x: x["price"])[:BATCH_CANDIDATES_PER_ITEM]
                results.append({"keyword": plan["keyword"], "status": "overview",
                                "total": plan.get("total", len(priced)),
                                "by_unit": _price_overview(priced), "samples": cheapest})

        summary: dict[str, int] = {"total": len(results)}
        for r in results:
            summary[r["status"]] = summary.get(r["status"], 0) + 1

        return _ok({"as_of": str(as_of_date), "results": results, "summary": summary})
    finally:
        db.close()
