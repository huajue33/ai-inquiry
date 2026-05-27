"""
Meilisearch 搜索服务
负责产品索引管理和搜索查询
"""
import meilisearch
from app.config import get_settings

settings = get_settings()

# Meilisearch 客户端
client = meilisearch.Client(settings.meili_url, settings.meili_master_key or None)

INDEX_NAME = "products"


def get_index():
    """获取产品索引"""
    return client.index(INDEX_NAME)


def setup_index():
    """
    初始化索引配置：
    - 可搜索字段
    - 可过滤字段
    - 排序字段
    - 同义词
    """
    try:
        client.create_index(INDEX_NAME, {"primaryKey": "product_id"})
    except meilisearch.errors.MeilisearchApiError:
        pass  # 索引已存在

    index = get_index()

    # 设置可搜索字段及优先级（越靠前权重越高）
    # 注意：category_name **不**作为可搜索字段。
    # 否则像"马铃薯淀粉"这类分类下的产品，搜"土豆"经同义词→"马铃薯"
    # 会通过分类名字段被误匹配。category_name 只通过"keyword 命中分类名→限定子树"
    # 的方式承接（见 price_service.search_products）。
    index.update_searchable_attributes([
        "product_name",
        "base_name",
        "aliases",
        "brand",
        "quality",
    ])

    # 设置可过滤字段
    index.update_filterable_attributes([
        "brand",
        "category_id",
        "category_name",
        "quality",
        "product_id",
    ])

    # 设置可排序字段
    index.update_sortable_attributes([
        "product_name",
        "brand",
    ])

    # 设置同义词（仅放真同义词，避免上下位词造成误命中）
    # 例：把"食用油 ↔ 花生油"作为同义会让搜花生油也匹配菜籽油，是错的；
    # 这种属于分类关系，应通过"keyword 命中分类名 → 限定子树"的方式承接。
    index.update_synonyms({
        "土豆": ["马铃薯", "洋芋"],
        "番茄": ["西红柿"],
    })

    # 设置 typo tolerance
    index.update_typo_tolerance({
        "enabled": True,
        "minWordSizeForTypos": {
            "oneTypo": 3,
            "twoTypos": 6,
        },
    })

    # 设置分页限制
    index.update_pagination_settings({"maxTotalHits": 1000})

    return index


def search_products(keyword: str, category_ids: list[int] = None, brand: str = "",
                    quality: str = "", limit: int = 50) -> list[dict]:
    """
    使用 Meilisearch 搜索产品

    Args:
        keyword: 搜索关键词
        category_ids: 分类ID过滤
        brand: 品牌过滤
        quality: 品质过滤
        limit: 返回数量限制

    Returns:
        产品列表（dict 格式）
    """
    index = get_index()

    # 构建过滤条件
    filters = []
    if category_ids:
        id_list = ", ".join(str(i) for i in category_ids)
        filters.append(f"category_id IN [{id_list}]")
    if brand:
        filters.append(f'brand = "{brand}"')
    if quality:
        filters.append(f'quality = "{quality}"')

    search_params = {
        "limit": limit,
        "attributesToRetrieve": [
            "product_id", "product_name", "brand", "base_name",
            "quality", "spec", "category_id", "category_name", "aliases",
        ],
    }

    if filters:
        search_params["filter"] = " AND ".join(filters)

    result = index.search(keyword, search_params)
    return result["hits"]


def sync_products(products: list[dict]):
    """
    批量同步产品数据到 Meilisearch

    Args:
        products: 产品数据列表，每个元素是 dict
    """
    index = get_index()
    # Meilisearch 支持批量添加/更新，每批最多 10000 条
    batch_size = 5000
    for i in range(0, len(products), batch_size):
        batch = products[i:i + batch_size]
        index.add_documents(batch)


def delete_all_documents():
    """清空索引中的所有文档"""
    index = get_index()
    index.delete_all_documents()


def get_index_stats():
    """获取索引统计信息"""
    index = get_index()
    return index.get_stats()
