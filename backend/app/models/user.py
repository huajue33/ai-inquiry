from sqlalchemy import Column, Integer, String, Text, DateTime, Enum, func
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    real_name = Column(String(64), nullable=False)
    role = Column(Enum("admin", "manager", "buyer"), nullable=False, default="buyer")
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())
