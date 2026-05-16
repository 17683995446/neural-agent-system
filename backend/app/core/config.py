# Configuration Management
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App Settings
    app_name: str = "Neural Agent System"
    app_version: str = "1.0.0"
    debug: bool = False

    # API Settings
    api_v1_prefix: str = "/api/v1"

    # Redis Settings
    redis_url: str = "redis://localhost:6379/0"

    # PostgreSQL Settings
    postgres_url: str = "postgresql://USER:PASS@localhost:5432/neural_agent"

    # RabbitMQ Settings
    rabbitmq_url: str = "amqp://USER:PASS@localhost:5672/"

    # Milvus Settings
    milvus_url: str = "http://localhost:19530"

    # LLM Settings - Anthropic (Primary)
    anthropic_auth_token: Optional[str] = None
    anthropic_base_url: str = "https://aigw-gzgy2.cucloud.cn:8443"
    anthropic_model: str = "MiniMax-M2.5"

    # LLM Settings - Legacy/Backup
    litellm_api_key: Optional[str] = None
    litellm_api_base: Optional[str] = None
    litellm_model: Optional[str] = None
    openai_api_key: Optional[str] = None

    default_llm_model: str = "glm-4-flash"

    # Cheap LLM Mode — 极便宜API, 无限agent并行
    cheap_llm_mode: bool = False
    cheap_llm_model: Optional[str] = None
    cheap_llm_max_tokens: int = 1024
    cheap_llm_temperature: float = 0.3
    cheap_llm_max_workers: int = 0  # 0=auto(CPU*4)

    # Task Settings
    max_iteration: int = 5
    default_learning_rate: float = 0.1

    # Trust Settings
    trust_initial_value: float = 1.0
    trust_min_value: float = 0.0
    trust_max_value: float = 2.0

    # Security
    pickle_hmac_key: str = "neural_agent_cache_key_v1"

    # CORS Settings
    allowed_cors_origins: str = "http://localhost:3000,http://localhost:8080"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()