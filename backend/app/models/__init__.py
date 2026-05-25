"""集中导入所有模型，方便 Base.metadata.create_all 时一次性发现"""
from app.models.user import User  # noqa: F401
from app.models.product import Product, Category  # noqa: F401
from app.models.price import Price  # noqa: F401
from app.models.conversation import Conversation, ChatMessage  # noqa: F401
from app.models.permission import UserCategoryPermission  # noqa: F401
