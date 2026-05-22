import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, auth, conversation, admin

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from app.services.search_service import setup_index, get_index_stats
        setup_index()
        stats = get_index_stats()
        logger.info(f"Meilisearch 就绪，索引文档数: {stats.number_of_documents}")
    except Exception as e:
        logger.warning(f"Meilisearch 初始化失败（搜索将降级到 MySQL）: {e}")
    yield


app = FastAPI(title="AI询价助手", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
app.include_router(chat.router, prefix="/api/chat", tags=["对话"])
app.include_router(conversation.router, prefix="/api/conversations", tags=["对话管理"])
app.include_router(admin.router, prefix="/api/admin", tags=["管理后台"])


@app.get("/api/health")
def health_check():
    return {"status": "ok"}
