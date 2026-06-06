from sqlalchemy import Column, BigInteger, Integer, String, Date, Numeric, DateTime, Index, func
from app.database import Base


class Price(Base):
    __tablename__ = "prices"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    product_id = Column(Integer, nullable=False, index=True)
    price_date = Column(Date, nullable=False, index=True)
    price_value = Column(Numeric(10, 4), nullable=False, default=0)
    price_unit = Column(String(20), nullable=False, default="")
    raw_price = Column(String(100), nullable=False, default="")
    created_at = Column(DateTime, server_default=func.now())

    # 复合索引：所有价格查询都按"某产品截至某日最近一条"回溯
    # （get_latest_prices_batch / get_price_trend / get_price_ranking），
    # (product_id, price_date) 能高效支撑这类按产品分组取最大日期的查询。
    __table_args__ = (
        Index("idx_prices_product_date", "product_id", "price_date"),
    )
