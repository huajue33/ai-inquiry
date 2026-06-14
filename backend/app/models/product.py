from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.database import Base


class Category(Base):
    """商品分类（自引用树：一级 / 二级 / 三级）。"""
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    parent_id = Column(Integer, ForeignKey("categories.id"))
    level = Column(Integer, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    parent = relationship("Category", remote_side=[id], backref="children")


class Product(Base):
    """商品基础信息（价格存于 Price 表，按 product_id 关联）。"""
    __tablename__ = "products"

    product_id = Column(Integer, primary_key=True)
    product_name = Column(String(512), nullable=False)
    brand = Column(String(256), nullable=False, default="")
    base_name = Column(String(512), nullable=False, default="")
    quality = Column(String(64), nullable=False, default="")
    spec = Column(String(256), nullable=False, default="")
    category_id = Column(Integer, ForeignKey("categories.id"))
    aliases = Column(String(512), nullable=False, default="")
    description = Column(Text)
    details = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    category = relationship("Category")
