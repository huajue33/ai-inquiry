"""
数据同步脚本：将 MySQL 中的产品数据同步到 Meilisearch

用法：
    python sync_products.py          # 全量同步
    python sync_products.py --reset  # 清空后重新同步
"""
import sys
import time

from app.database import SessionLocal
from app.models.product import Product, Category
from app.services.search_service import setup_index, sync_products, delete_all_documents, get_index_stats


def load_category_map(db) -> dict[int, str]:
    """加载分类ID到名称的映射（拼接完整路径）"""
    categories = db.query(Category).all()
    cat_dict = {c.id: c for c in categories}

    cat_name_map = {}
    for cat in categories:
        # 拼接分类路径：一级/二级/三级
        names = []
        current = cat
        while current:
            names.insert(0, current.name)
            current = cat_dict.get(current.parent_id)
        cat_name_map[cat.id] = " ".join(names)

    return cat_name_map


def fetch_all_products(db, category_map: dict[int, str]) -> list[dict]:
    """从 MySQL 读取所有产品并转为 Meilisearch 文档格式"""
    products = db.query(Product).all()

    documents = []
    for p in products:
        doc = {
            "product_id": p.product_id,
            "product_name": p.product_name,
            "brand": p.brand or "",
            "base_name": p.base_name or "",
            "quality": p.quality or "",
            "spec": p.spec or "",
            "category_id": p.category_id,
            "category_name": category_map.get(p.category_id, ""),
            "aliases": p.aliases or "",
        }
        documents.append(doc)

    return documents


def main():
    """主入口：将 MySQL 产品数据全量或增量同步到 Meilisearch"""
    reset = "--reset" in sys.argv

    print("=" * 50)
    print("产品数据同步到 Meilisearch")
    print("=" * 50)

    # 1. 初始化索引配置
    print("\n[1/4] 初始化 Meilisearch 索引配置...")
    setup_index()
    print("  ✓ 索引配置完成")

    # 2. 如果需要重置，清空文档
    if reset:
        print("\n[2/4] 清空现有文档...")
        delete_all_documents()
        time.sleep(1)  # 等待异步任务完成
        print("  ✓ 文档已清空")
    else:
        print("\n[2/4] 跳过清空（增量模式）")

    # 3. 从 MySQL 读取数据
    print("\n[3/4] 从 MySQL 读取产品数据...")
    db = SessionLocal()
    try:
        category_map = load_category_map(db)
        print(f"  ✓ 加载了 {len(category_map)} 个分类")

        documents = fetch_all_products(db, category_map)
        print(f"  ✓ 读取了 {len(documents)} 个产品")
    finally:
        db.close()

    # 4. 同步到 Meilisearch
    print("\n[4/4] 同步到 Meilisearch...")
    start = time.time()
    sync_products(documents)
    elapsed = time.time() - start
    print(f"  ✓ 同步完成，耗时 {elapsed:.1f}s")

    # 等待索引完成
    print("\n等待索引构建...")
    time.sleep(3)

    # 显示统计
    stats = get_index_stats()
    print(f"\n索引统计：")
    print(f"  文档数量: {stats.number_of_documents}")
    print(f"  索引中: {'是' if stats.is_indexing else '否'}")

    print("\n" + "=" * 50)
    print("同步完成！")
    print("=" * 50)


if __name__ == "__main__":
    main()
