"""
生成模拟价格数据（增量 + 自动保留窗口）

行为：
- 自动识别当前日期：终点 = 系统当天
- 增量生成：起点 = 数据库中最新价格日期的次日（接着已有数据往后补，不重复）
- 自动清理：生成后删除超过保留天数（默认 30 天，即只保留最近一个月）的旧数据

策略（沿用原逻辑）：
- 以每个产品最新一天的价格为基准
- 每天部分产品价格变动，变动幅度 ±1%~6%
- 其余产品价格保持不变（向后填充）

用法：
    python generate_prices.py                 # 增量生成到今天 + 保留最近 30 天
    python generate_prices.py --keep-days 7   # 改为只保留最近 7 天
    python generate_prices.py --no-prune      # 只生成，不删除旧数据
"""
import os
import sys
import random
from datetime import date, timedelta

import pymysql

# 数据库连接（优先读环境变量，方便容器内运行）
conn = pymysql.connect(
    host=os.getenv("DB_HOST", "127.0.0.1"),
    port=int(os.getenv("DB_PORT", "3306")),
    user=os.getenv("DB_USER", "root"),
    password=os.getenv("DB_PASSWORD", ""),
    database=os.getenv("DB_NAME", "quotation"),
    charset="utf8mb4",
)

# 默认保留最近一个月
DEFAULT_KEEP_DAYS = 30


def parse_args() -> tuple[int, bool]:
    """解析命令行参数，返回 (保留天数, 是否清理旧数据)"""
    keep_days = DEFAULT_KEEP_DAYS
    prune = True
    if "--no-prune" in sys.argv:
        prune = False
    if "--keep-days" in sys.argv:
        idx = sys.argv.index("--keep-days")
        try:
            keep_days = int(sys.argv[idx + 1])
        except (IndexError, ValueError):
            print("警告：--keep-days 参数无效，使用默认 30 天")
    return keep_days, prune


def get_max_date(cursor):
    """数据库中已有的最新价格日期（无数据返回 None）"""
    cursor.execute("SELECT MAX(price_date) FROM prices")
    row = cursor.fetchone()
    return row[0] if row and row[0] else None


def get_valid_product_ids(cursor) -> set:
    """products 表中真实存在的产品 ID（用于过滤孤儿价格，避免外键冲突）"""
    cursor.execute("SELECT product_id FROM products")
    return {row[0] for row in cursor.fetchall()}


def delete_orphan_prices(cursor):
    """删除 prices 中 product_id 在 products 表已不存在的孤儿记录"""
    cursor.execute(
        "DELETE FROM prices "
        "WHERE product_id NOT IN (SELECT product_id FROM products)"
    )
    deleted = cursor.rowcount
    conn.commit()
    if deleted:
        print(f"清理孤儿价格：删除 {deleted} 条（对应产品已不在 products 表）")
    else:
        print("无孤儿价格")
    return deleted


def get_latest_prices(cursor):
    """获取每个产品最新一天的价格作为基准"""
    cursor.execute("""
        SELECT p.product_id, p.price_value, p.price_unit, p.raw_price
        FROM prices p
        INNER JOIN (
            SELECT product_id, MAX(price_date) as max_date
            FROM prices
            GROUP BY product_id
        ) latest ON p.product_id = latest.product_id AND p.price_date = latest.max_date
    """)
    rows = cursor.fetchall()
    prices = {}
    for product_id, price_value, price_unit, raw_price in rows:
        prices[product_id] = {
            "price_value": float(price_value),
            "price_unit": price_unit,
            "raw_price": raw_price or "",
        }
    return prices


def generate_new_price(current_price: float) -> float:
    """生成新价格，变动幅度 ±1%~6%"""
    change_pct = random.uniform(0.01, 0.06)
    direction = random.choice([-1, 1])
    new_price = current_price * (1 + direction * change_pct)
    new_price = max(0.1, new_price)  # 确保价格不低于 0.1
    return round(new_price, 4)


def generate_range(cursor, current_prices, product_ids, start_date, end_date):
    """为 [start_date, end_date] 生成每日价格并写入"""
    total_days = (end_date - start_date).days + 1
    print(f"需要生成 {total_days} 天的数据（{start_date} ~ {end_date}）")

    current_date = start_date
    day_count = 0
    while current_date <= end_date:
        day_count += 1
        # 每天部分产品价格变动
        change_ratio = random.uniform(0.2, 0.5)
        num_changes = int(len(product_ids) * change_ratio)
        changing_products = set(random.sample(product_ids, num_changes))

        for pid in changing_products:
            old_price = current_prices[pid]["price_value"]
            current_prices[pid]["price_value"] = generate_new_price(old_price)

        batch = []
        for pid in product_ids:
            info = current_prices[pid]
            batch.append((
                pid, current_date, info["price_value"],
                info["price_unit"], info["raw_price"],
            ))

        batch_size = 2000
        for i in range(0, len(batch), batch_size):
            chunk = batch[i:i + batch_size]
            cursor.executemany(
                "INSERT INTO prices (product_id, price_date, price_value, price_unit, raw_price) "
                "VALUES (%s, %s, %s, %s, %s)",
                chunk,
            )
        conn.commit()

        if day_count % 7 == 0 or current_date == end_date:
            print(f"  [{day_count}/{total_days}] {current_date} - {num_changes} 个产品价格变动")

        current_date += timedelta(days=1)

    return day_count


def prune_old(cursor, cutoff_date):
    """删除 price_date < cutoff_date 的旧数据"""
    print(f"\n清理 {cutoff_date} 之前的旧数据...")
    cursor.execute("DELETE FROM prices WHERE price_date < %s", (cutoff_date,))
    deleted = cursor.rowcount
    conn.commit()
    print(f"  ✓ 删除 {deleted} 条旧记录")
    return deleted


def main():
    keep_days, prune = parse_args()
    cursor = conn.cursor()

    today = date.today()
    max_date = get_max_date(cursor)

    if max_date is None:
        print("错误：prices 表为空，没有基准价格可用于生成。")
        print("请先导入每个产品的初始价格后再运行本脚本。")
        cursor.close()
        conn.close()
        return

    print(f"当前日期：{today}，数据库最新日期：{max_date}")

    # 0. 先清理孤儿价格（产品已从 products 表删除，但价格残留）
    print("\n清理孤儿价格...")
    delete_orphan_prices(cursor)

    # 1. 增量生成：从最新日期次日到今天
    start_date = max_date + timedelta(days=1)
    if start_date > today:
        print("数据已是最新，无需生成新价格。")
    else:
        print("\n获取基准价格...")
        current_prices = get_latest_prices(cursor)
        # 过滤掉 products 表中已不存在的产品（孤儿价格），避免外键冲突
        valid_ids = get_valid_product_ids(cursor)
        product_ids = [pid for pid in current_prices if pid in valid_ids]
        skipped = len(current_prices) - len(product_ids)
        msg = f"共 {len(current_prices)} 个产品有基准价格"
        if skipped:
            msg += f"，其中 {skipped} 个在 products 表中不存在已跳过"
        msg += f"，实际生成 {len(product_ids)} 个产品"
        print(msg)
        days = generate_range(cursor, current_prices, product_ids, start_date, today)
        print(f"\n生成完成：{days} 天 × {len(product_ids)} 产品 ≈ {days * len(product_ids)} 条记录")

    # 2. 清理旧数据：只保留最近 keep_days 天
    if prune:
        cutoff = today - timedelta(days=keep_days)
        prune_old(cursor, cutoff)
        cursor.execute("SELECT COUNT(*), MIN(price_date), MAX(price_date) FROM prices")
        total, dmin, dmax = cursor.fetchone()
        print(f"\n当前价格数据：{total} 条，日期范围 {dmin} ~ {dmax}（保留最近 {keep_days} 天）")
    else:
        print("\n（--no-prune）跳过旧数据清理")

    cursor.close()
    conn.close()
    print("\n完成！")


if __name__ == "__main__":
    main()
