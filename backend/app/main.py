import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, auth, conversation, admin

logger = logging.getLogger(__name__)


def _parse_cors_origins() -> list[str]:
    """读取 CORS_ORIGINS 环境变量，逗号分隔；缺省或 '*' 时放行所有。"""
    raw = os.getenv("CORS_ORIGINS", "*").strip()
    if not raw or raw == "*":
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动时初始化 Meilisearch 索引，关闭时清理资源"""
    try:
        from app.services.search_service import setup_index, get_index_stats
        setup_index()
        stats = get_index_stats()
        logger.info(f"Meilisearch 就绪，索引文档数: {stats.number_of_documents}")

        # 首次启动且索引为空时自动同步产品（容器化部署友好）
        if stats.number_of_documents == 0:
            logger.info("Meilisearch 索引为空，开始自动同步产品数据 ...")
            try:
                from sync_products import load_category_map, fetch_all_products
                from app.services.search_service import sync_products
                from app.database import SessionLocal

                db = SessionLocal()
                try:
                    cat_map = load_category_map(db)
                    docs = fetch_all_products(db, cat_map)
                    if docs:
                        sync_products(docs)
                        logger.info(f"已提交 {len(docs)} 个产品到 Meilisearch（异步索引中）")
                    else:
                        logger.warning("MySQL 中无产品数据，跳过同步")
                finally:
                    db.close()
            except Exception as e:
                logger.warning(f"自动同步产品失败（可手动执行 sync_products.py）: {e}")
    except Exception as e:
        logger.warning(f"Meilisearch 初始化失败（搜索将降级到 MySQL）: {e}")
    yield


app = FastAPI(title="AI询价助手", version="1.0.0", lifespan=lifespan)

_cors_origins = _parse_cors_origins()
# 注意：allow_origins=["*"] 时不能同时 allow_credentials=True
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
app.include_router(chat.router, prefix="/api/chat", tags=["对话"])
app.include_router(conversation.router, prefix="/api/conversations", tags=["对话管理"])
app.include_router(admin.router, prefix="/api/admin", tags=["管理后台"])


@app.get("/api/health")
def health_check():
    """健康检查接口"""
    return {"status": "ok"}
