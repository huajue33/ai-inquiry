from langchain_core.tools import tool
from app.database import SessionLocal
from app.services.price_service import (
    search_products,
    get_latest_price,
    get_price_trend,
    get_price_ranking,
    group_products_for_clarify,
)
from app.core.permissions import (
    get_current_user_from_context,
    get_allowed_category_ids,
    intersect_category_ids,
)


def _resolve_category_ids(db, requested_ids):
    """根据当前请求用户，返回最终允许查询的分类 ID。

    返回元组 (final_ids, denied)。
    - final_ids=None 表示无限制
    - final_ids=[]   表示用户没有任何可访问分类，调用方应直接返回提示
    - denied=True    表示用户对"显式请求的分类"无权限
    """
    user = get_current_user_from_context()
    if user is None:
        # 兜底：没有用户上下文时按无限制处理（理论上不该走到这里）
        return requested_ids, False

    allowed = get_allowed_category_ids(db, user)
    final_ids = intersect_category_ids(allowed, requested_ids)

    # 用户主动指定了分类但被权限砍成空列表 → 视为越权
    denied = bool(requested_ids) and final_ids == []
    return final_ids, denied


@tool
def query_latest_price(product_name: str, brand: str = "", category: str = "", quality: str = "") -> str:
    """查询产品最新价格。参数：product_name(产品名称关键词或产品ID), brand(品牌,可选), category(分类,可选), quality(品质,可选)"""
    db = SessionLocal()
    try:
        from app.models.product import Category as CatModel

        # 如果指定了分类，先查分类 ID
        requested_category_ids = None
        if category:
            cats = db.query(CatModel).filter(CatModel.name.like(f"%{category}%")).all()
            if cats:
                requested_category_ids = [c.id for c in cats]

        # 与用户被授权的分类求交集
        category_ids, denied = _resolve_category_ids(db, requested_category_ids)
        if denied:
            return f"你没有'{category}'分类的查看权限，请联系管理员。"
        if category_ids == []:
            return "你当前没有任何分类的查看权限，请联系管理员授权。"

        products = search_products(db, product_name, category_ids=category_ids)

        # 如果指定了品牌，进一步过滤
        if brand and products:
            filtered = [p for p in products if brand.lower() in (p.brand or "").lower()]
            if filtered:
                products = filtered

        # 如果指定了品质，进一步过滤
        if quality and products:
            filtered = [p for p in products if quality in (p.quality or "")]
            if filtered:
                products = filtered

        if not products:
            return f"未找到包含'{product_name}'的产品。建议：1) 尝试更短的关键词 2) 尝试产品的别名 3) 尝试搜索分类名"

        if len(products) > 50:
            # 结果非常多，必须引导用户细化
            groups = group_products_for_clarify(products)
            group_text = "\n".join([f"- {g['name']}（{g['count']}个产品）" for g in groups])
            return f"搜索'{product_name}'找到{len(products)}个产品，种类较多，请选择具体类型：\n{group_text}"

        # 即使结果较多（20-50条），也直接返回前10条价格，不再触发追问循环
        results = []
        for p in products[:10]:
            price = get_latest_price(db, p.product_id)
            if price:
                results.append({
                    "product_id": p.product_id,
                    "product_name": p.product_name,
                    "brand": p.brand,
                    "quality": p.quality,
                    "spec": p.spec,
                    "price": float(price.price_value),
                    "unit": price.price_unit,
                    "date": str(price.price_date),
                })

        if not results:
            return f"找到产品'{product_name}'但暂无价格数据。"

        lines = []
        if len(products) > 10:
            lines.append(f"共找到{len(products)}个相关产品，以下是前10个的最新价格：")
        for r in results:
            brand_str = f"[{r['brand']}]" if r["brand"] else ""
            quality_str = f"({r['quality']})" if r["quality"] else ""
            lines.append(f"{brand_str}{r['product_name']}{quality_str}{{#id={r['product_id']}}} - {r['price']}元/{r['unit']}（{r['date']}）")
        if len(products) > 10:
            lines.append(f"\n如需查看更多，请提供更具体的品牌或规格信息。")
        return "\n".join(lines)
    finally:
        db.close()


@tool
def query_price_trend(product_name: str, days: int = 7) -> str:
    """查询产品价格趋势。参数：product_name(产品名称关键词或产品ID), days(天数,默认7)"""
    db = SessionLocal()
    try:
        category_ids, _ = _resolve_category_ids(db, None)
        if category_ids == []:
            return "你当前没有任何分类的查看权限，请联系管理员授权。"

        products = search_products(db, product_name, category_ids=category_ids, limit=5)
        if not products:
            return f"未找到包含'{product_name}'的产品（或无权访问）。建议尝试更短的关键词或产品别名。"

        product = products[0]
        # 使用带向后填充的趋势查询
        trend_data = get_price_trend(db, product.product_id, days)

        if not trend_data:
            return f"'{product.product_name}'暂无近{days}天的价格数据。"

        lines = [f"'{product.product_name}'{{#id={product.product_id}}} 近{days}天价格走势："]
        for item in trend_data:
            fill_mark = "（填充）" if item["is_filled"] else ""
            lines.append(f"  {item['price_date']} - {float(item['price_value'])}元/{item['price_unit']}{fill_mark}")

        if len(trend_data) >= 2:
            first_price = float(trend_data[0]["price_value"])
            last_price = float(trend_data[-1]["price_value"])
            if first_price > 0:
                change_pct = (last_price - first_price) / first_price * 100
                trend = "↑涨" if change_pct > 0 else "↓跌" if change_pct < 0 else "持平"
                lines.append(f"  趋势：{trend} {abs(change_pct):.1f}%")

        return "\n".join(lines)
    finally:
        db.close()


@tool
def query_price_ranking(direction: str = "rise", category: str = "", limit: int = 10) -> str:
    """查询价格涨跌排行。参数：direction(rise涨/fall跌), category(分类,可选), limit(数量,默认10)"""
    db = SessionLocal()
    try:
        from app.models.product import Category

        requested_category_ids = None
        if category:
            cats = db.query(Category).filter(Category.name.like(f"%{category}%")).all()
            if cats:
                requested_category_ids = [c.id for c in cats]
                # 也包含子分类
                child_cats = db.query(Category).filter(Category.parent_id.in_(requested_category_ids)).all()
                if child_cats:
                    requested_category_ids.extend([c.id for c in child_cats])
                    grandchild_cats = db.query(Category).filter(
                        Category.parent_id.in_([c.id for c in child_cats])
                    ).all()
                    if grandchild_cats:
                        requested_category_ids.extend([c.id for c in grandchild_cats])

        category_ids, denied = _resolve_category_ids(db, requested_category_ids)
        if denied:
            return f"你没有'{category}'分类的查看权限，请联系管理员。"
        if category_ids == []:
            return "你当前没有任何分类的查看权限，请联系管理员授权。"

        results = get_price_ranking(db, direction, category_ids, limit)

        if not results:
            direction_text = "涨幅" if direction == "rise" else "跌幅"
            return f"暂无{direction_text}排行数据。"

        direction_text = "涨幅" if direction == "rise" else "跌幅"
        lines = [f"{direction_text}排行TOP{limit}："]
        for pid, name, prev, latest, change_pct in results:
            arrow = "↑" if change_pct > 0 else "↓"
            lines.append(f"  {name}{{#id={pid}}} | {float(prev):.2f}→{float(latest):.2f} | {arrow}{abs(change_pct):.1f}%")

        return "\n".join(lines)
    finally:
        db.close()


@tool
def compare_products(product_names: list[str], compare_type: str = "brand") -> str:
    """比较多个产品的价格。参数：product_names(产品名称列表), compare_type(brand品牌对比/quality品质对比)"""
    db = SessionLocal()
    try:
        category_ids, _ = _resolve_category_ids(db, None)
        if category_ids == []:
            return "你当前没有任何分类的查看权限，请联系管理员授权。"

        all_results = []
        for name in product_names:
            products = search_products(db, name, category_ids=category_ids, limit=5)
            for p in products:
                price = get_latest_price(db, p.product_id)
                if price:
                    all_results.append({
                        "product_id": p.product_id,
                        "name": p.product_name,
                        "brand": p.brand,
                        "quality": p.quality,
                        "price": float(price.price_value),
                        "unit": price.price_unit,
                    })

        if not all_results:
            return "未找到可对比的产品价格数据（或无权访问）。建议尝试更具体的产品名称。"

        lines = ["价格对比结果："]
        sorted_results = sorted(all_results, key=lambda x: x["price"])
        for r in sorted_results:
            brand_str = f"[{r['brand']}]" if r["brand"] else ""
            quality_str = f"({r['quality']})" if r["quality"] else ""
            lines.append(f"  {brand_str}{r['name']}{quality_str}{{#id={r['product_id']}}} - {r['price']}元/{r['unit']}")

        if len(sorted_results) >= 2:
            cheapest = sorted_results[0]
            most_expensive = sorted_results[-1]
            diff = most_expensive["price"] - cheapest["price"]
            lines.append(f"  最大价差: {diff:.2f}元")

        return "\n".join(lines)
    finally:
        db.close()


@tool
def clarify_product(keyword: str, max_groups: int = 5) -> str:
    """当搜索结果过多时，返回分类选项让用户进一步选择。参数：keyword(搜索关键词), max_groups(最多返回几组,默认5)"""
    db = SessionLocal()
    try:
        category_ids, _ = _resolve_category_ids(db, None)
        if category_ids == []:
            return "你当前没有任何分类的查看权限，请联系管理员授权。"

        products = search_products(db, keyword, category_ids=category_ids, limit=200)
        if not products:
            return f"未找到包含'{keyword}'的产品（或无权访问）。建议尝试更短的关键词。"

        if len(products) <= 10:
            # 结果不多，直接返回价格
            results = []
            for p in products:
                price = get_latest_price(db, p.product_id)
                if price:
                    brand_str = f"[{p.brand}]" if p.brand else ""
                    results.append(f"{brand_str}{p.product_name}{{#id={p.product_id}}} - {float(price.price_value)}元/{price.price_unit}")
            if results:
                return f"'{keyword}'相关产品价格：\n" + "\n".join(results)
            return f"找到产品'{keyword}'但暂无价格数据。"

        groups = group_products_for_clarify(products, max_groups)
        lines = [f"'{keyword}'相关产品共{len(products)}个，包含以下类型："]
        for i, g in enumerate(groups, 1):
            lines.append(f"  {i}. {g['name']}（{g['count']}个产品）")
        lines.append("\n请告诉我你需要哪种类型，我帮你查具体价格。")

        return "\n".join(lines)
    finally:
        db.close()
