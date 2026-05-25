from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_, or_
from datetime import date, timedelta
import logging

from app.models.product import Product, Category
from app.models.price import Price

logger = logging.getLogger(__name__)


def search_products(db: Session, keyword: str, category_ids: list[int] = None, limit: int = 50):
    """
    搜索产品 - 支持 ID 搜索、Meilisearch、MySQL LIKE

    Returns:
        Product ORM 对象列表
    """
    keyword = keyword.strip()
    if not keyword:
        return []

    # 如果关键词是纯数字，尝试按 product_id 精确查找
    if keyword.isdigit():
        product = db.query(Product).filter(Product.product_id == int(keyword)).first()
        if product:
            return [product]

    # 优先尝试 Meilisearch
    try:
        from app.services.search_service import search_products as meili_search
        hits = meili_search(keyword, category_ids=category_ids, limit=limit)
        if hits:
            # 用 product_id 从数据库加载完整 ORM 对象
            product_ids = [h["product_id"] for h in hits]
            products = db.query(Product).filter(Product.product_id.in_(product_ids)).all()
            # 保持 Meilisearch 的相关度排序
            id_order = {pid: idx for idx, pid in enumerate(product_ids)}
            products.sort(key=lambda p: id_order.get(p.product_id, 999))
            return products
    except Exception as e:
        logger.warning(f"Meilisearch 搜索失败，降级到 MySQL: {e}")

    # Fallback: MySQL LIKE 搜索
    return _search_mysql(db, keyword, category_ids, limit)


def _search_mysql(db: Session, keyword: str, category_ids: list[int] = None, limit: int = 50):
    """MySQL LIKE 降级搜索"""
    query = db.query(Product).filter(
        or_(
            Product.product_name.like(f"%{keyword}%"),
            Product.base_name.like(f"%{keyword}%"),
            Product.aliases.like(f"%{keyword}%"),
            Product.brand.like(f"%{keyword}%"),
        )
    )
    if category_ids:
        query = query.filter(Product.category_id.in_(category_ids))
    results = query.limit(limit).all()

    # 如果没结果，尝试分类联想
    if not results:
        matched_cats = db.query(Category).filter(Category.name.like(f"%{keyword}%")).all()
        if matched_cats:
            cat_ids = set()
            for cat in matched_cats:
                cat_ids.add(cat.id)
                children = db.query(Category).filter(Category.parent_id == cat.id).all()
                for child in children:
                    cat_ids.add(child.id)
                    grandchildren = db.query(Category).filter(Category.parent_id == child.id).all()
                    for gc in grandchildren:
                        cat_ids.add(gc.id)
            if category_ids:
                cat_ids = cat_ids.intersection(set(category_ids))
            if cat_ids:
                results = db.query(Product).filter(Product.category_id.in_(cat_ids)).limit(limit).all()

    return results


def get_latest_price(db: Session, product_id: int, as_of_date: date = None) -> Optional[Price]:
    """
    获取产品最新价格（向后填充逻辑）
    如果指定了 as_of_date，返回该日期或之前最近的价格记录
    """
    query = db.query(Price).filter(Price.product_id == product_id)
    if as_of_date:
        query = query.filter(Price.price_date <= as_of_date)
    return query.order_by(desc(Price.price_date)).first()


def get_latest_prices_batch(db: Session, product_ids: list[int]) -> dict[int, Price]:
    """
    批量获取多个产品的最新价格（解决 N+1 问题）
    返回 {product_id: Price} 字典
    """
    if not product_ids:
        return {}

    # 子查询：每个产品的最新日期
    latest_date_sub = (
        db.query(Price.product_id, func.max(Price.price_date).label("max_date"))
        .filter(Price.product_id.in_(product_ids))
        .group_by(Price.product_id)
        .subquery()
    )

    # JOIN 取完整记录
    prices = (
        db.query(Price)
        .join(latest_date_sub, and_(
            Price.product_id == latest_date_sub.c.product_id,
            Price.price_date == latest_date_sub.c.max_date,
        ))
        .all()
    )

    return {p.product_id: p for p in prices}


def get_price_trend(db: Session, product_id: int, days: int = 7) -> list[dict]:
    """
    获取价格趋势（带向后填充）
    返回连续日期的价格序列，如果某天没有记录，用前一天的价格填充

    Returns:
        list[dict] 每个元素包含 price_date, price_value, price_unit, is_filled
    """
    today = date.today()
    start_date = today - timedelta(days=days - 1)

    # 查询日期范围内的实际价格记录
    actual_prices = (
        db.query(Price)
        .filter(
            Price.product_id == product_id,
            Price.price_date >= start_date,
            Price.price_date <= today,
        )
        .order_by(Price.price_date)
        .all()
    )

    # 构建日期到价格的映射
    price_map = {}
    for p in actual_prices:
        price_map[p.price_date] = p

    # 始终查询 start_date 之前最近的一条记录，作为向后填充的初始基准
    base_price = (
        db.query(Price)
        .filter(Price.product_id == product_id, Price.price_date < start_date)
        .order_by(desc(Price.price_date))
        .first()
    )

    # 向后填充：生成连续日期序列
    result = []
    last_known_price = base_price
    current_date = start_date

    while current_date <= today:
        if current_date in price_map:
            price = price_map[current_date]
            last_known_price = price
            result.append({
                "price_date": current_date,
                "price_value": price.price_value,
                "price_unit": price.price_unit,
                "is_filled": False,
            })
        elif last_known_price:
            # 向后填充：用最近已知价格
            result.append({
                "price_date": current_date,
                "price_value": last_known_price.price_value,
                "price_unit": last_known_price.price_unit,
                "is_filled": True,
            })
        # 如果连 last_known_price 都没有，跳过该天
        current_date += timedelta(days=1)

    return result


def get_price_trend_raw(db: Session, product_id: int, days: int = 7) -> list[Price]:
    """获取原始价格记录（不填充），用于兼容旧逻辑"""
    start_date = date.today() - timedelta(days=days)
    return (
        db.query(Price)
        .filter(Price.product_id == product_id, Price.price_date >= start_date)
        .order_by(Price.price_date)
        .all()
    )


def get_price_ranking(db: Session, direction: str = "rise", category_ids: list[int] = None, limit: int = 10):
    """
    涨跌排行：对比最新日期和前一个有数据的日期
    """
    latest_date_sub = db.query(func.max(Price.price_date)).scalar_subquery()
    prev_date_sub = (
        db.query(func.max(Price.price_date))
        .filter(Price.price_date < latest_date_sub)
        .scalar_subquery()
    )

    latest_prices = (
        db.query(Price.product_id, Price.price_value.label("latest_price"))
        .filter(Price.price_date == latest_date_sub)
        .subquery()
    )
    prev_prices = (
        db.query(Price.product_id, Price.price_value.label("prev_price"))
        .filter(Price.price_date == prev_date_sub)
        .subquery()
    )

    query = (
        db.query(
            Product.product_id,
            Product.product_name,
            prev_prices.c.prev_price,
            latest_prices.c.latest_price,
        )
        .join(latest_prices, Product.product_id == latest_prices.c.product_id)
        .join(prev_prices, Product.product_id == prev_prices.c.product_id)
        .filter(prev_prices.c.prev_price > 0)
    )

    if category_ids:
        query = query.filter(Product.category_id.in_(category_ids))

    if direction == "rise":
        query = query.order_by(desc(
            (latest_prices.c.latest_price - prev_prices.c.prev_price) / prev_prices.c.prev_price
        ))
    else:
        query = query.order_by(
            (latest_prices.c.latest_price - prev_prices.c.prev_price) / prev_prices.c.prev_price
        )

    rows = query.limit(limit).all()

    results = []
    for pid, name, prev, latest in rows:
        change_pct = (float(latest) - float(prev)) / float(prev) * 100
        results.append((pid, name, prev, latest, change_pct))
    return results


def group_products_for_clarify(products: list, max_groups: int = 5) -> list[dict]:
    """按 base_name 核心词分组，用于追问引导"""
    groups = {}
    for p in products:
        core_name = _extract_core_name(p)
        if core_name not in groups:
            groups[core_name] = {"name": core_name, "count": 0, "sample_ids": []}
        groups[core_name]["count"] += 1
        if len(groups[core_name]["sample_ids"]) < 3:
            groups[core_name]["sample_ids"].append(p.product_id)

    sorted_groups = sorted(groups.values(), key=lambda x: x["count"], reverse=True)
    return sorted_groups[:max_groups]


def _extract_core_name(product) -> str:
    """从产品中提取核心名称用于分组"""
    import re

    base = product.base_name.strip()
    if not base:
        base = product.product_name

    # 去掉品牌前缀
    if product.brand and base.startswith(product.brand):
        base = base[len(product.brand):].strip()

    # 去掉规格后缀（数字+单位的模式）
    base = re.sub(r'[\d.]+[\w/]*$', '', base).strip()

    # 如果结果为空，回退
    if not base:
        base = product.base_name[:6] if product.base_name else product.product_name[:6]

    return base
