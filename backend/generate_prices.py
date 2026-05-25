"""
生成模拟价格数据：从 2026-03-24 到 2026-05-21
策略：
- 以每个产品最后一天的价格为基准
- 每天约 8-12% 的产品价格会变动
- 变动幅度：±1%~6%
- 其余产品价格保持不变（向后填充）
"""
import os
import random
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

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

START_DATE = date(2026, 3, 24)
END_DATE = date(2026, 5, 21)

random.seed(42)


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
    # 确保价格不低于 0.1
    new_price = max(0.1, new_price)
    # 保留4位小数
    return round(new_price, 4)


def main():
    cursor = conn.cursor()

    print("获取基准价格...")
    current_prices = get_latest_prices(cursor)
    print(f"共 {len(current_prices)} 个产品有基准价格")

    product_ids = list(current_prices.keys())
    total_days = (END_DATE - START_DATE).days + 1
    print(f"需要生成 {total_days} 天的数据（{START_DATE} ~ {END_DATE}）")

    current_date = START_DATE
    day_count = 0

    while current_date <= END_DATE:
        day_count += 1
        # 每天 8-12% 的产品价格变动
        change_ratio = random.uniform(0.2, 0.5)
        num_changes = int(len(product_ids) * change_ratio)
        changing_products = set(random.sample(product_ids, num_changes))

        # 更新变动产品的价格
        for pid in changing_products:
            old_price = current_prices[pid]["price_value"]
            current_prices[pid]["price_value"] = generate_new_price(old_price)

        # 批量插入当天所有产品的价格
        batch = []
        for pid in product_ids:
            info = current_prices[pid]
            batch.append((
                pid,
                current_date,
                info["price_value"],
                info["price_unit"],
                info["raw_price"],
            ))

        # 分批插入，每批 2000 条
        batch_size = 2000
        for i in range(0, len(batch), batch_size):
            chunk = batch[i:i + batch_size]
            cursor.executemany(
                "INSERT INTO prices (product_id, price_date, price_value, price_unit, raw_price) VALUES (%s, %s, %s, %s, %s)",
                chunk,
            )

        conn.commit()

        if day_count % 7 == 0 or current_date == END_DATE:
            print(f"  [{day_count}/{total_days}] {current_date} - {num_changes} 个产品价格变动")

        current_date += timedelta(days=1)

    cursor.close()
    conn.close()

    print(f"\n完成！共生成 {day_count} 天 × {len(product_ids)} 产品 ≈ {day_count * len(product_ids)} 条价格记录")


if __name__ == "__main__":
    main()
