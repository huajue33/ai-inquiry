from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    dashscope_api_key: str
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_model: str = "qwen-max"
    dashscope_lite_model: str = "qwen-turbo"

    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "quotation"

    # 连接池：默认值偏小容易在并发时排队等连接。
    # 总连接数 ≈ worker 数 ×（db_pool_size + db_max_overflow），需 ≤ MySQL max_connections。
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_recycle: int = 3600

    meili_url: str = "http://127.0.0.1:7700"
    meili_master_key: str = ""

    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    """获取应用配置单例"""
    return Settings()
