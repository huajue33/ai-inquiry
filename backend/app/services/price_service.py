from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_, or_
from datetime import date, timedelta
import logging

from app.models.product import Product
from app.models.price import Price
from app.services.category_cache import get_all_categories, expand_subtree
from app.core.aliases import alias_to_canonical

logger = logging.getLogger(__name__)


def search_products(db: Session, keyword: str, category_ids: list[int] = None, limit: int = 50):
    """
    搜索产品 - 多策略：ID 精确 → 分类名精确联想 → Meilisearch → MySQL LIKE

    分类联想的设计：
    - 当关键词与某个**叶子分类**（level=3）的名字精确等价（包含同义词），
      认为用户想要的是"这个品类的所有产品"，把搜索强制限定到该分类子树。
    - 这样搜"土豆"会被锁在"蔬菜水果 > 根茎类 > 土豆"分类下，不会泄漏到
      "调味品 > 淀粉/调理粉 > 生粉/马铃薯淀粉"等含"马铃薯"字眼的分类。
    - 同义词通过 _CATEGORY_ALIASES 维护（如"马铃薯""洋芋"映射到"土豆"分类）。

    Returns:
        Product ORM 对象列表
    """
    keyword = keyword.strip()
    if not keyword:
        return []

    # 1. 纯数字 → 按 product_id 精确查找
    if keyword.isdigit():
        product = db.query(Product).filter(Product.product_id == int(keyword)).first()
        if product:
            return [product]

    # 2. 关键词命中叶子分类名 → 限定到该分类子树
    scoped_category_ids = _resolve_keyword_to_category_subtree(db, keyword)
    effective_category_ids = _intersect(category_ids, scoped_category_ids)

    # 显式空集（调用方传入分类与子树/权限完全无交集）→ 直接返回空，
    # 不能丢给下游搜索（下游会把 [] 当作 falsy 进而忽略 filter，等于全库搜）
    if effective_category_ids == []:
        return []

    # 3. Meilisearch（带可能的子树过滤）
    try:
        from app.services.search_service import search_products as meili_search
        hits = meili_search(keyword, category_ids=effective_category_ids, limit=limit)
        if hits:
            product_ids = [h["product_id"] for h in hits]
            products = db.query(Product).filter(Product.product_id.in_(product_ids)).all()
            id_order = {pid: idx for idx, pid in enumerate(product_ids)}
            products.sort(key=lambda p: id_order.get(p.product_id, 999))
            return products

        # Meilisearch 在子树内搜没结果，但子树本身有产品 → 直接返回子树全量
        # （场景：用户搜"土豆"，叶子分类下产品名里都不含"土豆"两字的极端情况）
        if scoped_category_ids and not category_ids:
            products = (
                db.query(Product)
                .filter(Product.category_id.in_(scoped_category_ids))
                .limit(limit)
                .all()
            )
            if products:
                return products
    except Exception as e:
        logger.warning(f"Meilisearch 搜索失败，降级到 MySQL: {e}")

    # 4. Fallback: MySQL LIKE
    return _search_mysql(db, keyword, effective_category_ids, limit)


# ===== 关键词 → 分类子树 联想 =====

# 关键词到"规范分类名关键字"的别名表（用户常用别名 → 标准品类名）
# value 会用 LIKE 去 categories.name 模糊匹配，所以填核心词即可。
# 数据源统一在 app/core/aliases.py（与 Meilisearch 同义词共用一份）。
_CATEGORY_ALIASES: dict[str, str] = alias_to_canonical()


def _resolve_keyword_to_category_subtree(db: Session, keyword: str) -> list[int] | None:
    """
    若 keyword 精确匹配某个叶子分类名（或通过别名映射后匹配），
    返回该分类（含其子树）的 ID 集合；否则返回 None。

    只匹配叶子分类（即没有子分类的分类），避免"蔬菜""调味品"这种顶层词
    把范围拉得太大；用户搜顶层词时应走正常的全文搜索 + 分组提示。
    """
    canonical = _CATEGORY_ALIASES.get(keyword, keyword)

    all_cats = get_all_categories()

    # 找名字等于 canonical 的分类
    matched = [c for c in all_cats if c.name == canonical]
    if not matched:
        return None

    # 只在"叶子分类匹配"或"匹配的分类是非顶层"时生效。
    # 一级分类（level=1）的名字（如"蔬菜水果""调味品"）不该走这个路径，
    # 因为它会把整个一级分类锁住，反而影响正常全文搜索。
    if all(c.level == 1 for c in matched):
        return None

    return list(expand_subtree(c.id for c in matched))


def _intersect(a: list[int] | None, b: list[int] | None) -> list[int] | None:
    """两个分类 ID 列表求交集；任一为 None 表示不限制，返回另一个。"""
    if a is None:
        return b
    if b is None:
        return a
    return list(set(a) & set(b))


def _search_mysql(db: Session, keyword: str, category_ids: list[int] = None, limit: int = 50):
    """MySQL LIKE 降级搜索（分类联想已在主路径完成，这里只做朴素 LIKE）"""
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
    return query.limit(limit).all()


def get_latest_prices_batch(
    db: Session,
    product_ids: list[int],
    as_of_date: date = None,
) -> dict[int, Price]:
    """
    批量获取多个产品在指定日期的有效价格（解决 N+1 问题）。

    指定 as_of_date 时返回该日及之前最近一条；不指定时返回最新一条。
    返回 {product_id: Price} 字典。
    """
    if not product_ids:
        return {}

    base_query = db.query(Price).filter(Price.product_id.in_(product_ids))
    if as_of_date is not None:
        base_query = base_query.filter(Price.price_date <= as_of_date)

    # 子查询：每个产品在限定日期范围内的最新日期
    latest_date_sub = (
        base_query.with_entities(
            Price.product_id, func.max(Price.price_date).label("max_date")
        )
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


def get_price_ranking(
    db: Session,
    direction: str = "rise",
    category_ids: list[int] = None,
    limit: int = 10,
    as_of: date = None,
):
    """
    涨跌排行：对比 as_of 当天和前一天的有效价（默认 as_of=今天）。

    生鲜价格不是每天更新，所以两端各自向前回溯到 ≤ 该日的最近一条记录：
      - to_price   = 截至 as_of   的最近一条
      - from_price = 截至 as_of-1 的最近一条
    若两端取到的是同一条记录（即从 as_of-1 到 as_of 之间该产品无新报价），
    不计入排行——这与"价格无变化"是不同的：两条独立记录碰巧同价仍会保留。

    Returns:
        (rows, compare) 元组：
        - rows: list of (product_id, name, prev_price, latest_price, change_pct, unit)
        - compare: dict {"from": date, "to": date}，对比的两个日期（即 as_of-1 和 as_of）
    """
    if as_of is None:
        as_of = date.today()
    to_date = as_of
    from_date = as_of - timedelta(days=1)

    # 各自向前回溯的最近日期（per product）
    to_sub = (
        db.query(
            Price.product_id,
            func.max(Price.price_date).label("d"),
        )
        .filter(Price.price_date <= to_date)
        .group_by(Price.product_id)
        .subquery()
    )
    from_sub = (
        db.query(
            Price.product_id,
            func.max(Price.price_date).label("d"),
        )
        .filter(Price.price_date <= from_date)
        .group_by(Price.product_id)
        .subquery()
    )

    # JOIN 拿到两端完整 Price 行（含 price_value、price_unit）
    to_price = (
        db.query(
            Price.product_id,
            Price.price_value.label("latest_price"),
            Price.price_unit.label("unit"),
            Price.price_date.label("to_date"),
        )
        .join(to_sub, and_(
            Price.product_id == to_sub.c.product_id,
            Price.price_date == to_sub.c.d,
        ))
        .subquery()
    )
    from_price = (
        db.query(
            Price.product_id,
            Price.price_value.label("prev_price"),
            Price.price_date.label("from_date"),
        )
        .join(from_sub, and_(
            Price.product_id == from_sub.c.product_id,
            Price.price_date == from_sub.c.d,
        ))
        .subquery()
    )

    query = (
        db.query(
            Product.product_id,
            Product.product_name,
            from_price.c.prev_price,
            to_price.c.latest_price,
            to_price.c.unit,
        )
        .join(to_price, Product.product_id == to_price.c.product_id)
        .join(from_price, Product.product_id == from_price.c.product_id)
        .filter(from_price.c.prev_price > 0)
        # 排除"两端取到同一条记录"的情况（区间内无新报价 → 不该上榜）
        # 注意是判记录日期相同，不是价格相同——两条独立记录恰好同价应保留
        .filter(to_price.c.to_date != from_price.c.from_date)
    )

    if category_ids:
        query = query.filter(Product.category_id.in_(category_ids))

    change_expr = (
        (to_price.c.latest_price - from_price.c.prev_price) / from_price.c.prev_price
    )
    if direction == "rise":
        query = query.order_by(desc(change_expr))
    else:
        query = query.order_by(change_expr)

    rows = query.limit(limit).all()

    results = []
    for pid, name, prev, latest, unit in rows:
        change_pct = (float(latest) - float(prev)) / float(prev) * 100
        results.append((pid, name, prev, latest, change_pct, unit or ""))

    return results, {"from": from_date, "to": to_date}


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


# 品类价格聚合：参与汇总的最大产品数（防止超大分类拉爆 IN 查询）
_SUMMARY_MAX_PRODUCTS = 2000


def get_category_price_summary(db: Session, category_ids: list[int], as_of: date = None) -> dict:
    """对一个品类（含子树）做价格概览聚合，不返回明细。

    生鲜价格不是每天更新，这里复用 get_latest_prices_batch 的"向前回溯"取每个产品
    截至 as_of 的有效价。不同计价单位（元/斤、元/袋）分别统计，避免混算。

    Returns:
        dict: {
          total_products, priced_products, truncated,
          by_unit: [{unit, count, min, max, avg, median}],   # 按数量降序
          by_brand: [{brand, count, avg, unit}],              # 主流单位下，按数量取前若干品牌
        }
        无产品时返回 {"total_products": 0, ...}
    """
    if as_of is None:
        as_of = date.today()

    rows = (
        db.query(Product.product_id, Product.brand)
        .filter(Product.category_id.in_(category_ids))
        .all()
    )
    total_products = len(rows)
    truncated = total_products > _SUMMARY_MAX_PRODUCTS
    rows = rows[:_SUMMARY_MAX_PRODUCTS]
    pids = [r[0] for r in rows]
    brand_map = {r[0]: (r[1] or "未标注") for r in rows}

    if not pids:
        return {"total_products": 0, "priced_products": 0, "truncated": False,
                "by_unit": [], "by_brand": []}

    price_map = get_latest_prices_batch(db, pids, as_of_date=as_of)

    # 按单位聚合价格；同时记录 品牌×单位 的价格
    unit_prices: dict[str, list[float]] = {}
    brand_unit_prices: dict[tuple[str, str], list[float]] = {}
    for pid in pids:
        pr = price_map.get(pid)
        if not pr:
            continue
        unit = pr.price_unit or ""
        val = float(pr.price_value)
        unit_prices.setdefault(unit, []).append(val)
        brand_unit_prices.setdefault((brand_map[pid], unit), []).append(val)

    priced_products = sum(len(v) for v in unit_prices.values())

    def _stats(vals: list[float]) -> dict:
        s = sorted(vals)
        n = len(s)
        med = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
        return {
            "count": n,
            "min": round(s[0], 2),
            "max": round(s[-1], 2),
            "avg": round(sum(s) / n, 2),
            "median": round(med, 2),
        }

    by_unit = sorted(
        ({"unit": u, **_stats(v)} for u, v in unit_prices.items() if v),
        key=lambda x: x["count"], reverse=True,
    )

    # 主流单位下按品牌汇总，取数量前 8
    by_brand = []
    if by_unit:
        main_unit = by_unit[0]["unit"]
        brand_rows = [
            {"brand": b, "unit": u, "count": len(v), "avg": round(sum(v) / len(v), 2)}
            for (b, u), v in brand_unit_prices.items() if u == main_unit and v
        ]
        by_brand = sorted(brand_rows, key=lambda x: x["count"], reverse=True)[:8]

    return {
        "total_products": total_products,
        "priced_products": priced_products,
        "truncated": truncated,
        "by_unit": by_unit,
        "by_brand": by_brand,
    }
