"""权限模块

集中处理：
1. 角色级权限（require_admin / require_admin_or_manager）
2. 数据范围权限（用户被授权的分类）
3. 通过 ContextVar 把当前用户注入到 LangChain @tool 函数里
"""
from contextvars import ContextVar
from typing import Optional, List

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.permission import UserCategoryPermission
from app.models.product import Category
from app.core.security import get_current_user


# ===== 1. 角色级权限 =====

def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def require_admin_or_manager(user: User = Depends(get_current_user)) -> User:
    if user.role not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="需要管理员或主管权限")
    return user


def require_authed(user: User = Depends(get_current_user)) -> User:
    """登录即可访问（admin / manager / buyer）"""
    return user


# ===== 2. 数据范围权限 =====

def get_allowed_category_ids(db: Session, user: User) -> Optional[List[int]]:
    """
    返回用户允许查询的分类 ID 列表（包含被授权的二级 + 展开后的三级）。

    - admin / manager → 返回 None（无限制）
    - buyer 没有任何授权 → 返回 []（查询应当返回空）
    - buyer 有授权 → 返回二级 ID + 三级叶子 ID（兼容产品关联任意层级）
    """
    if user.role in ("admin", "manager"):
        return None

    perms = (
        db.query(UserCategoryPermission)
        .filter(UserCategoryPermission.user_id == user.id)
        .all()
    )
    if not perms:
        return []

    second_level_ids = [p.category_id for p in perms]

    # 展开到三级
    third_level = (
        db.query(Category)
        .filter(Category.parent_id.in_(second_level_ids))
        .all()
    )
    leaf_ids = [c.id for c in third_level]

    # 返回二级 + 三级，确保无论产品关联哪一级、工具传哪一级都能匹配
    return list(set(second_level_ids + leaf_ids))


def intersect_category_ids(
    allowed: Optional[List[int]],
    requested: Optional[List[int]],
) -> Optional[List[int]]:
    """把"用户被允许的分类"和"本次请求显式指定的分类"求交集

    - allowed=None  无限制 → 返回 requested 原样
    - allowed=[]    无权限 → 返回 [] （触发 "无权限" 提示）
    - requested=None 没指定 → 返回 allowed
    - 都有 → 求交集；如果直接交集为空，尝试展开 requested 的子分类再交
    """
    if allowed is None:
        return requested
    if not allowed:
        return []
    if not requested:
        return allowed

    allowed_set = set(allowed)
    inter = list(allowed_set & set(requested))

    # 如果直接交集为空，可能是 requested 传的是二级分类而 allowed 包含其三级子分类
    # 此时返回 allowed 中属于 requested 子树的那些 ID
    if not inter:
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            # 查找 requested 的子分类
            children = (
                db.query(Category.id)
                .filter(Category.parent_id.in_(requested))
                .all()
            )
            child_ids = set(c[0] for c in children)
            inter = list(allowed_set & child_ids)
        finally:
            db.close()

    return inter


# ===== 3. ContextVar：把当前用户注入到 LangChain tool =====

# tools 是同步函数，无法通过参数注入；改用 ContextVar 在请求生命周期内传递
current_user_var: ContextVar[Optional[User]] = ContextVar("current_user", default=None)


def get_current_user_from_context() -> Optional[User]:
    return current_user_var.get()
