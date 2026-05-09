from functools import cached_property

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # MySQL 连接
    database_url: str = ""

    # DeepSeek（OpenAI 兼容）
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # 表白名单
    allowed_databases: str = ""
    allowed_tables: str = ""

    # 功能开关
    debug: bool = False
    reasoning_trace_enabled: bool = True

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @cached_property
    def allowed_db_list(self) -> list[str]:
        return [db.strip() for db in self.allowed_databases.split(",") if db.strip()]

    @cached_property
    def allowed_table_list(self) -> list[str]:
        return [t.strip() for t in self.allowed_tables.split(",") if t.strip()]


settings = Settings()
