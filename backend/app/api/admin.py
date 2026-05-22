"""管理后台 API"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.database import get_db
from app.models.user import User
from app.models.product import Product, Category
from app.models.price import Price
from app.models.conversation import Conversation, ChatMessage
from app.core.security import get_current_user, hash_password

router = APIRouter()


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


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
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    users = db.query(User).order_by(desc(User.created_at)).all()
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


# ===== 商品管理 =====

@router.get("/products")
async def list_products(
    keyword: str = "",
    category_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = db.query(Product)
    if keyword:
        query = query.filter(Product.product_name.like(f"%{keyword}%"))
    if category_id:
        query = query.filter(Product.category_id == category_id)

    total = query.count()
    products = query.offset((page - 1) * page_size).limit(page_size).all()

    # 批量获取分类名称（拼接完整路径：一级>二级>三级）
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
        # 子查询获取每个产品的最新价格日期
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
    admin: User = Depends(require_admin),
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
    admin: User = Depends(require_admin),
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
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = db.query(Conversation)
    if user_id:
        query = query.filter(Conversation.user_id == user_id)

    total = query.count()
    convs = (
        query.order_by(desc(Conversation.updated_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    # 获取用户名映射
    user_ids = list(set(c.user_id for c in convs))
    users = db.query(User).filter(User.id.in_(user_ids)).all() if user_ids else []
    user_map = {u.id: u.real_name for u in users}

    # 获取每个对话的消息数量和 Token 消耗
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
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
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
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    total_users = db.query(func.count(User.id)).scalar()
    total_products = db.query(func.count(Product.product_id)).scalar()
    total_conversations = db.query(func.count(Conversation.id)).scalar()
    total_messages = db.query(func.count(ChatMessage.id)).scalar()

    # 今日对话数
    from datetime import date, timedelta
    today_conversations = (
        db.query(func.count(Conversation.id))
        .filter(func.date(Conversation.created_at) == date.today())
        .scalar()
    )

    # 总 Token 消耗
    total_tokens = db.query(func.sum(ChatMessage.total_tokens)).scalar() or 0

    # 近7天每日对话数
    daily_conversations = []
    for i in range(6, -1, -1):
        d = date.today() - timedelta(days=i)
        count = (
            db.query(func.count(Conversation.id))
            .filter(func.date(Conversation.created_at) == d)
            .scalar()
        )
        daily_conversations.append({"date": str(d), "count": count})

    # 近7天每日 Token 消耗
    daily_tokens = []
    for i in range(6, -1, -1):
        d = date.today() - timedelta(days=i)
        tokens = (
            db.query(func.sum(ChatMessage.total_tokens))
            .filter(func.date(ChatMessage.created_at) == d)
            .scalar()
        ) or 0
        daily_tokens.append({"date": str(d), "tokens": int(tokens)})

    # 近7天每日消息数
    daily_messages = []
    for i in range(6, -1, -1):
        d = date.today() - timedelta(days=i)
        count = (
            db.query(func.count(ChatMessage.id))
            .filter(func.date(ChatMessage.created_at) == d)
            .scalar()
        )
        daily_messages.append({"date": str(d), "count": count})

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
    }
