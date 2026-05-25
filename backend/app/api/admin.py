"""管理后台 API

权限矩阵：
- 数据概览  : admin / manager / buyer 都可见（buyer 只看自己）
- 商品管理  : admin / manager / buyer 都可见
- 对话记录  : admin / manager / buyer 都可见（admin 看全部；manager / buyer 仅自己）
- 用户管理  : admin / manager 可见；buyer 不可访问
              admin: 全权
              manager: 仅查看 + 仅可调整 buyer 的数据权限，不能改密码/角色/启用状态
"""
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.database import get_db
from app.models.user import User
from app.models.product import Product, Category
from app.models.price import Price
from app.models.conversation import Conversation, ChatMessage
from app.models.permission import UserCategoryPermission
from app.core.security import get_current_user, hash_password
from app.core.permissions import (
    require_admin,
    require_admin_or_manager,
    require_authed,
)

router = APIRouter()


# ===== 用户管理 =====

class UserItem(BaseModel):
    id: int
    username: str
    real_name: str
    role: str
    is_active: int
    created_at: str


class CreateUserRequest(BaseModel):
    username: str
    password: str
    real_name: str
    role: str = "buyer"


class UpdateUserRequest(BaseModel):
    real_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[int] = None
    password: Optional[str] = None


@router.get("/users")
async def list_users(
    user: User = Depends(require_admin_or_manager),
    db: Session = Depends(get_db),
):
    """admin 看全部；manager 只看 buyer（用于配置数据权限）"""
    query = db.query(User).order_by(desc(User.created_at))
    if user.role == "manager":
        query = query.filter(User.role == "buyer")
    users = query.all()
    return {
        "users": [
            UserItem(
                id=u.id,
                username=u.username,
                real_name=u.real_name,
                role=u.role,
                is_active=u.is_active,
                created_at=str(u.created_at),
            )
            for u in users
        ]
    }


@router.post("/users")
async def create_user(
    request: CreateUserRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    existing = db.query(User).filter(User.username == request.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")

    user = User(
        username=request.username,
        password_hash=hash_password(request.password),
        real_name=request.real_name,
        role=request.role,
    )
    db.add(user)
    db.commit()
    return {"id": user.id}


@router.put("/users/{user_id}")
async def update_user(
    user_id: int,
    request: UpdateUserRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 禁止管理员把自己禁用或降级，避免锁死
    if user.id == admin.id:
        if request.is_active is not None and request.is_active == 0:
            raise HTTPException(status_code=400, detail="不能禁用自己的账号")
        if request.role is not None and request.role != admin.role:
            raise HTTPException(status_code=400, detail="不能修改自己的角色")
        if request.password:
            raise HTTPException(
                status_code=400,
                detail="请通过 '修改密码' 入口修改自己的密码",
            )

    if request.real_name is not None:
        user.real_name = request.real_name
    if request.role is not None:
        user.role = request.role
    if request.is_active is not None:
        user.is_active = request.is_active
    if request.password:
        user.password_hash = hash_password(request.password)

    db.commit()
    return {"ok": True}


# ===== 数据权限（用户-分类映射） =====

class UserPermissions(BaseModel):
    user_id: int
    category_ids: List[int]


@router.get("/users/{user_id}/permissions")
async def get_user_permissions(
    user_id: int,
    user: User = Depends(require_admin_or_manager),
    db: Session = Depends(get_db),
):
    perms = (
        db.query(UserCategoryPermission)
        .filter(UserCategoryPermission.user_id == user_id)
        .all()
    )
    return {"user_id": user_id, "category_ids": [p.category_id for p in perms]}


@router.put("/users/{user_id}/permissions")
async def set_user_permissions(
    user_id: int,
    payload: UserPermissions,
    user: User = Depends(require_admin_or_manager),
    db: Session = Depends(get_db),
):
    """全量替换：传入的 category_ids 即为该用户的最终授权列表

    - admin: 可改任何人
    - manager: 只能改 buyer
    """
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")

    if user.role == "manager" and target.role != "buyer":
        raise HTTPException(status_code=403, detail="主管仅可调整采购员的数据权限")

    # 校验传入的都是合法分类
    if payload.category_ids:
        cats = db.query(Category).filter(Category.id.in_(payload.category_ids)).all()
        invalid = set(payload.category_ids) - set(c.id for c in cats)
        if invalid:
            raise HTTPException(status_code=400, detail=f"以下分类 ID 不存在：{sorted(invalid)}")

    # 清空 + 重建
    db.query(UserCategoryPermission).filter(
        UserCategoryPermission.user_id == user_id
    ).delete(synchronize_session=False)

    for cat_id in payload.category_ids:
        db.add(UserCategoryPermission(user_id=user_id, category_id=cat_id))
    db.commit()
    return {"ok": True, "count": len(payload.category_ids)}


# ===== 商品管理（所有登录用户可访问） =====

@router.get("/products")
async def list_products(
    keyword: str = "",
    category_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(require_authed),
    db: Session = Depends(get_db),
):
    query = db.query(Product)
    if keyword:
        query = query.filter(Product.product_name.like(f"%{keyword}%"))
    if category_id:
        query = query.filter(Product.category_id == category_id)

    total = query.count()
    products = query.offset((page - 1) * page_size).limit(page_size).all()

    # 分类名（拼接完整路径：一级>二级>三级）
    cat_ids = list(set(p.category_id for p in products if p.category_id))
    cat_map = {}
    if cat_ids:
        all_cats = db.query(Category).all()
        cat_dict = {c.id: c for c in all_cats}
        for cat_id in cat_ids:
            names = []
            current = cat_dict.get(cat_id)
            while current:
                names.insert(0, current.name)
                current = cat_dict.get(current.parent_id)
            cat_map[cat_id] = " > ".join(names)

    # 批量获取最新价格
    product_ids = [p.product_id for p in products]
    latest_prices = {}
    if product_ids:
        from sqlalchemy import and_
        latest_date_sub = (
            db.query(Price.product_id, func.max(Price.price_date).label("max_date"))
            .filter(Price.product_id.in_(product_ids))
            .group_by(Price.product_id)
            .subquery()
        )
        prices = (
            db.query(Price)
            .join(latest_date_sub, and_(
                Price.product_id == latest_date_sub.c.product_id,
                Price.price_date == latest_date_sub.c.max_date,
            ))
            .all()
        )
        for p in prices:
            latest_prices[p.product_id] = {
                "price": float(p.price_value),
                "unit": p.price_unit,
                "date": str(p.price_date),
            }

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "products": [
            {
                "product_id": p.product_id,
                "product_name": p.product_name,
                "brand": p.brand,
                "base_name": p.base_name,
                "quality": p.quality,
                "spec": p.spec,
                "category_id": p.category_id,
                "category_name": cat_map.get(p.category_id, ""),
                "latest_price": latest_prices.get(p.product_id),
            }
            for p in products
        ],
    }


@router.get("/products/{product_id}/prices")
async def get_product_prices(
    product_id: int,
    days: int = Query(30, ge=1, le=365),
    user: User = Depends(require_authed),
    db: Session = Depends(get_db),
):
    """获取商品历史价格"""
    from datetime import date, timedelta
    start_date = date.today() - timedelta(days=days)

    prices = (
        db.query(Price)
        .filter(Price.product_id == product_id, Price.price_date >= start_date)
        .order_by(Price.price_date)
        .all()
    )

    product = db.query(Product).filter(Product.product_id == product_id).first()

    return {
        "product_id": product_id,
        "product_name": product.product_name if product else "",
        "prices": [
            {
                "date": str(p.price_date),
                "price": float(p.price_value),
                "unit": p.price_unit,
            }
            for p in prices
        ],
    }


@router.get("/categories")
async def list_categories(
    user: User = Depends(require_authed),
    db: Session = Depends(get_db),
):
    categories = db.query(Category).order_by(Category.level, Category.name).all()
    return {
        "categories": [
            {"id": c.id, "name": c.name, "parent_id": c.parent_id, "level": c.level}
            for c in categories
        ]
    }


# ===== 对话记录 =====

@router.get("/conversations")
async def list_all_conversations(
    user_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(require_authed),
    db: Session = Depends(get_db),
):
    """admin 可看全部，可按 user_id 过滤；manager / buyer 仅自己的"""
    query = db.query(Conversation)

    if user.role == "admin":
        if user_id:
            query = query.filter(Conversation.user_id == user_id)
    else:
        # manager / buyer 强制只看自己
        query = query.filter(Conversation.user_id == user.id)

    total = query.count()
    convs = (
        query.order_by(desc(Conversation.updated_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    user_ids = list(set(c.user_id for c in convs))
    users = db.query(User).filter(User.id.in_(user_ids)).all() if user_ids else []
    user_map = {u.id: u.real_name for u in users}

    conv_ids = [c.id for c in convs]
    msg_counts = {}
    token_counts = {}
    if conv_ids:
        counts = (
            db.query(
                ChatMessage.conversation_id,
                func.count(ChatMessage.id),
                func.sum(ChatMessage.total_tokens),
            )
            .filter(ChatMessage.conversation_id.in_(conv_ids))
            .group_by(ChatMessage.conversation_id)
            .all()
        )
        for cid, cnt, tokens in counts:
            msg_counts[cid] = cnt
            token_counts[cid] = int(tokens or 0)

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "conversations": [
            {
                "id": c.id,
                "user_id": c.user_id,
                "user_name": user_map.get(c.user_id, ""),
                "title": c.title,
                "is_deleted": c.is_deleted,
                "message_count": msg_counts.get(c.id, 0),
                "token_count": token_counts.get(c.id, 0),
                "created_at": str(c.created_at),
                "updated_at": str(c.updated_at),
            }
            for c in convs
        ],
    }


@router.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: str,
    user: User = Depends(require_authed),
    db: Session = Depends(get_db),
):
    # 非 admin 只能看自己的对话
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    if user.role != "admin" and conv.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权查看该对话")

    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at)
        .all()
    )
    return {
        "messages": [
            {
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "thinking": msg.thinking,
                "duration": msg.duration,
                "prompt_tokens": msg.prompt_tokens or 0,
                "completion_tokens": msg.completion_tokens or 0,
                "total_tokens": msg.total_tokens or 0,
                "created_at": str(msg.created_at),
            }
            for msg in messages
        ]
    }


# ===== 统计概览 =====

@router.get("/stats")
async def get_stats(
    user: User = Depends(require_authed),
    db: Session = Depends(get_db),
):
    """admin 看全局；manager / buyer 看自己范围内的统计"""
    is_admin = user.role == "admin"

    # 用户数 / 商品数 全局可见
    total_users = db.query(func.count(User.id)).scalar()
    total_products = db.query(func.count(Product.product_id)).scalar()

    # 对话 / 消息 / token：非 admin 只看自己的
    conv_q = db.query(func.count(Conversation.id))
    if not is_admin:
        conv_q = conv_q.filter(Conversation.user_id == user.id)
    total_conversations = conv_q.scalar()

    msg_base = db.query(ChatMessage)
    if not is_admin:
        msg_base = msg_base.join(
            Conversation, Conversation.id == ChatMessage.conversation_id
        ).filter(Conversation.user_id == user.id)
    total_messages = msg_base.with_entities(func.count(ChatMessage.id)).scalar()
    total_tokens = msg_base.with_entities(func.sum(ChatMessage.total_tokens)).scalar() or 0

    # 今日对话
    from datetime import date, timedelta
    today_q = db.query(func.count(Conversation.id)).filter(
        func.date(Conversation.created_at) == date.today()
    )
    if not is_admin:
        today_q = today_q.filter(Conversation.user_id == user.id)
    today_conversations = today_q.scalar()

    def daily(field_metric, base_query):
        results = []
        for i in range(6, -1, -1):
            d = date.today() - timedelta(days=i)
            q = base_query
            if field_metric == "count_conv":
                v = q.filter(func.date(Conversation.created_at) == d).with_entities(
                    func.count(Conversation.id)
                ).scalar()
            elif field_metric == "count_msg":
                v = q.filter(func.date(ChatMessage.created_at) == d).with_entities(
                    func.count(ChatMessage.id)
                ).scalar()
            elif field_metric == "sum_tokens":
                v = q.filter(func.date(ChatMessage.created_at) == d).with_entities(
                    func.sum(ChatMessage.total_tokens)
                ).scalar() or 0
            results.append((d, int(v or 0)))
        return results

    # 准备基础查询
    base_conv = db.query(Conversation)
    if not is_admin:
        base_conv = base_conv.filter(Conversation.user_id == user.id)

    base_msg = db.query(ChatMessage)
    if not is_admin:
        base_msg = base_msg.join(
            Conversation, Conversation.id == ChatMessage.conversation_id
        ).filter(Conversation.user_id == user.id)

    daily_conversations = [
        {"date": str(d), "count": v} for d, v in daily("count_conv", base_conv)
    ]
    daily_messages = [
        {"date": str(d), "count": v} for d, v in daily("count_msg", base_msg)
    ]
    daily_tokens = [
        {"date": str(d), "tokens": v} for d, v in daily("sum_tokens", base_msg)
    ]

    return {
        "total_users": total_users,
        "total_products": total_products,
        "total_conversations": total_conversations,
        "total_messages": total_messages,
        "today_conversations": today_conversations,
        "total_tokens": int(total_tokens),
        "daily_conversations": daily_conversations,
        "daily_tokens": daily_tokens,
        "daily_messages": daily_messages,
        "scope": "all" if is_admin else "self",
    }
