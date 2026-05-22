from sqlalchemy import Column, BigInteger, Integer, String, Date, Numeric, DateTime, func
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
