"""Server-only local-development settings. Secrets never enter participant models."""
from dataclasses import dataclass, field
import math
import os


def optional(name: str) -> str | None:
    return os.getenv(name, "").strip() or None


def flag(name: str, default: bool) -> bool:
    value = os.getenv(name, str(default)).lower().strip()
    if value not in {"true", "false", "1", "0"}:
        raise ValueError(f"{name} must be true or false")
    return value in {"true", "1"}


def price(name: str) -> float | None:
    value = optional(name)
    return float(value) if value is not None else None


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: os.getenv(
        "DATABASE_URL", "postgresql+psycopg://praxioj:praxioj@127.0.0.1:5432/praxioj"
    ), repr=False)
    environment: str = field(default_factory=lambda: os.getenv("PRAXIOJ_ENV", "development"))
    llm_base_url: str | None = field(default_factory=lambda: optional("PRAXIOJ_LLM_BASE_URL"), repr=False)
    llm_api_key: str | None = field(default_factory=lambda: optional("PRAXIOJ_LLM_API_KEY"), repr=False)
    llm_model: str | None = field(default_factory=lambda: optional("PRAXIOJ_LLM_MODEL"))
    default_profile: str = field(default_factory=lambda: os.getenv("PRAXIOJ_DEFAULT_PROFILE", "mock"))
    llm_supports_tools: bool = field(default_factory=lambda: flag("PRAXIOJ_LLM_SUPPORTS_TOOLS", False))
    llm_supports_system: bool = field(default_factory=lambda: flag("PRAXIOJ_LLM_SUPPORTS_SYSTEM", True))
    llm_supports_temperature: bool = field(default_factory=lambda: flag("PRAXIOJ_LLM_SUPPORTS_TEMPERATURE", True))
    llm_token_parameter: str = field(default_factory=lambda: os.getenv("PRAXIOJ_LLM_TOKEN_PARAMETER", "max_tokens"))
    llm_timeout_seconds: float = field(default_factory=lambda: float(os.getenv("PRAXIOJ_LLM_TIMEOUT_SECONDS", "30")))
    price_input_per_million: float | None = field(default_factory=lambda: price("PRAXIOJ_PRICE_INPUT_PER_MILLION"))
    price_output_per_million: float | None = field(default_factory=lambda: price("PRAXIOJ_PRICE_OUTPUT_PER_MILLION"))
    price_currency: str = field(default_factory=lambda: os.getenv("PRAXIOJ_PRICE_CURRENCY", "USD"))
    cookie_name: str = "praxioj_dev_identity"
    allowed_hosts: tuple[str, ...] = ("localhost", "127.0.0.1", "[::1]")
    allowed_origins: tuple[str, ...] = tuple(
        f"http://{host}:{port}" for host in ("localhost", "127.0.0.1", "[::1]") for port in (5173, 8000, 8080)
    )
    max_request_bytes: int = 131_072

    def __post_init__(self) -> None:
        if self.environment not in {"development", "test"}:
            raise ValueError("Milestone 2 supports local development only; production authentication is not implemented")
        if self.database_url.startswith("sqlite") and self.environment != "test":
            raise ValueError("SQLite is supported only with PRAXIOJ_ENV=test; local development uses PostgreSQL")
        if not (self.database_url.startswith("postgresql+psycopg://") or self.database_url.startswith("sqlite")):
            raise ValueError("Use PostgreSQL with psycopg, or SQLite for tests")
        if self.default_profile not in {"mock", "compatible"}:
            raise ValueError("Invalid default runtime profile")
        if bool(self.llm_base_url) != bool(self.llm_model):
            raise ValueError("LLM base URL and model must be configured together")
        if self.default_profile == "compatible" and not self.llm_base_url:
            raise ValueError("Default compatible profile is not configured")
        if self.llm_token_parameter not in {"max_tokens", "max_completion_tokens"}:
            raise ValueError("Unsupported token limit parameter")
        if not math.isfinite(self.llm_timeout_seconds) or not 0 < self.llm_timeout_seconds <= 120:
            raise ValueError("LLM timeout must be between 0 and 120 seconds")
        for value in (self.price_input_per_million, self.price_output_per_million):
            if value is not None and (not math.isfinite(value) or value < 0):
                raise ValueError("Prices must be finite nonnegative amounts")
        if len(self.price_currency) != 3 or not self.price_currency.isalpha():
            raise ValueError("Price currency must be a three-letter code")
