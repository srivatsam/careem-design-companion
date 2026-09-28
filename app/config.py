"""Runtime configuration, read once from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass
class Settings:
    llm_provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "azure").lower())
    azure_openai_endpoint: str = field(default_factory=lambda: _env("AZURE_OPENAI_ENDPOINT"))
    azure_openai_api_key: str = field(default_factory=lambda: _env("AZURE_OPENAI_API_KEY"))
    azure_openai_api_version: str = field(default_factory=lambda: _env("AZURE_OPENAI_API_VERSION", "2024-10-21"))
    azure_openai_chat_deployment: str = field(default_factory=lambda: _env("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o-mini"))
    azure_openai_embed_deployment: str = field(default_factory=lambda: _env("AZURE_OPENAI_EMBED_DEPLOYMENT"))
    database_path: str = field(default_factory=lambda: _env("DATABASE_PATH", "data/app.db"))
    brand_filter: str = field(default_factory=lambda: _env("BRAND_FILTER"))
    default_lang: str = field(default_factory=lambda: _env("DEFAULT_LANG", "en"))
    admin_token: str = field(default_factory=lambda: _env("ADMIN_TOKEN", "change-me"))
    rate_limit_per_minute: int = field(default_factory=lambda: int(_env("RATE_LIMIT_PER_MINUTE", "30") or 30))
    port: int = field(default_factory=lambda: int(_env("PORT", "8000") or 8000))

    @property
    def llm_enabled(self) -> bool:
        if self.llm_provider == "mock":
            return True
        if self.llm_provider == "azure":
            return bool(self.azure_openai_endpoint and self.azure_openai_api_key)
        return False

    @property
    def embeddings_enabled(self) -> bool:
        return self.llm_provider == "azure" and self.llm_enabled and bool(self.azure_openai_embed_deployment)


settings = Settings()
