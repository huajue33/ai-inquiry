from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.core.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    verify_refresh_token,
    get_current_user,
    hash_password,
)

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: int
    username: str
    real_name: str
    role: str


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserInfo(BaseModel):
    user_id: int
    username: str
    real_name: str
    role: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    """验证用户名密码并返回 JWT token"""
    user = db.query(User).filter(User.username == request.username).first()
    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被禁用",
        )

    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        user_id=user.id,
        username=user.username,
        real_name=user.real_name,
        role=user.role,
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_token(request: RefreshRequest, db: Session = Depends(get_db)):
    """用 refresh token 换取新的 access token + refresh token"""
    payload = verify_refresh_token(request.refresh_token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="无效的 refresh token")

    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")

    new_access = create_access_token({"sub": str(user.id)})
    new_refresh = create_refresh_token({"sub": str(user.id)})
    return RefreshResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        token_type="bearer",
    )


@router.get("/me", response_model=UserInfo)
async def get_me(user: User = Depends(get_current_user)):
    """返回当前登录用户的身份信息"""
    return UserInfo(
        user_id=user.id,
        username=user.username,
        real_name=user.real_name,
        role=user.role,
    )


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """修改当前用户的登录密码"""
    if not verify_password(request.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="原密码错误")
    if len(request.new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码至少6位")
    user.password_hash = hash_password(request.new_password)
    db.commit()
    return {"ok": True}
