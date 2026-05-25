from sqlalchemy import Column, Integer, ForeignKey, UniqueConstraint, DateTime, func
from app.database import Base


class UserCategoryPermission(Base):
    """用户 - 二级分类权限映射

    - 一条记录 = 用户被授权访问的某个二级分类
    - 实际过滤时由 permissions.get_allowed_category_ids 展开到三级（叶子）
    """
    __tablename__ = "user_category_permissions"
    __table_args__ = (
        UniqueConstraint("user_id", "category_id", name="uk_user_cat"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False, comment="二级分类 ID")
    created_at = Column(DateTime, server_default=func.now())
