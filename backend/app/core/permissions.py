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
    返回用户允许查询的"三级分类 ID 列表"。

    - admin / manager → 返回 None（无限制）
    - buyer 没有任何授权 → 返回 []（查询应当返回空）
    - buyer 有授权 → 把二级分类展开到三级叶子并返回
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

    # 兼容：如果授权的本身就是三级或一级，直接用授权 + 展开结果
    if not leaf_ids:
        return list(second_level_ids)
    return leaf_ids


def intersect_category_ids(
    allowed: Optional[List[int]],
    requested: Optional[List[int]],
) -> Optional[List[int]]:
    """把"用户被允许的分类"和"本次请求显式指定的分类"求交集

    - allowed=None  无限制 → 返回 requested 原样
    - allowed=[]    无权限 → 返回 [] （触发 "无权限" 提示）
    - requested=None 没指定 → 返回 allowed
    - 都有 → 求交集；交集为空也返回 []
    """
    if allowed is None:
        return requested
    if not allowed:
        return []
    if not requested:
        return allowed
    inter = list(set(allowed) & set(requested))
    return inter  # 空列表会触发无权限提示


# ===== 3. ContextVar：把当前用户注入到 LangChain tool =====

# tools 是同步函数，无法通过参数注入；改用 ContextVar 在请求生命周期内传递
current_user_var: ContextVar[Optional[User]] = ContextVar("current_user", default=None)


def get_current_user_from_context() -> Optional[User]:
    return current_user_var.get()
