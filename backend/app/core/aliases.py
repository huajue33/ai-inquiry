"""产品别名 / 同义词的单一数据源。

两处消费，共享同一份数据，集中在此维护（避免在多个文件里各写一遍）：

- search_service.setup_index：配置 Meilisearch 同义词，作用于全文检索匹配。
- price_service：关键词命中分类名时把别名归一到规范词（用于"锁定分类子树"）。

这两个机制是有意分开的（见各自代码注释），但用的是同一批别名，因此数据放一处。
"""

# 规范词 -> 别名列表
SYNONYMS: dict[str, list[str]] = {
    "土豆": ["马铃薯", "洋芋"],
    "番茄": ["西红柿"],
}


def meili_synonyms() -> dict[str, list[str]]:
    """Meilisearch 同义词配置（规范词 -> 别名列表）。"""
    return {canonical: list(aliases) for canonical, aliases in SYNONYMS.items()}


def alias_to_canonical() -> dict[str, str]:
    """别名 -> 规范词映射（price_service 的分类别名归一用）。"""
    result: dict[str, str] = {}
    for canonical, aliases in SYNONYMS.items():
        for alias in aliases:
            result[alias] = canonical
    return result
