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
    cookie_name: str = "praxioj_session"
    csrf_cookie_name: str = "praxioj_csrf"
    cookie_secure: bool = field(default_factory=lambda: flag("PRAXIOJ_COOKIE_SECURE", False))
    auth_session_seconds: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_AUTH_SESSION_SECONDS", "28800")))
    auth_rate_window_seconds: int = 300
    auth_ip_limit: int = 30
    auth_account_limit: int = 10
    allowed_hosts: tuple[str, ...] = ("localhost", "127.0.0.1", "[::1]")
    allowed_origins: tuple[str, ...] = tuple(
        f"{scheme}://{host}:{port}" for scheme in ("http", "https")
        for host in ("localhost", "127.0.0.1", "[::1]") for port in (5173, 8000, 8080)
    ) + tuple(f"https://{host}" for host in ("localhost", "127.0.0.1", "[::1]"))
    max_request_bytes: int = 131_072
    trace_retention_days: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_TRACE_RETENTION_DAYS", "30")))
    trace_retention_max_days: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_TRACE_RETENTION_MAX_DAYS", "90")))
    audit_retention_days: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_AUDIT_RETENTION_DAYS", "90")))
    worker_lease_seconds: float = field(default_factory=lambda: float(os.getenv("PRAXIOJ_WORKER_LEASE_SECONDS", "15")))
    worker_heartbeat_seconds: float = field(default_factory=lambda: float(os.getenv("PRAXIOJ_WORKER_HEARTBEAT_SECONDS", "3")))
    worker_poll_seconds: float = field(default_factory=lambda: float(os.getenv("PRAXIOJ_WORKER_POLL_SECONDS", "0.5")))

    def __post_init__(self) -> None:
        if not 1 <= self.trace_retention_days <= self.trace_retention_max_days <= 90:
            raise ValueError("Trace retention must be between 1 and 90 days")
        if not 1 <= self.audit_retention_days <= 90:
            raise ValueError("Audit retention must be between 1 and 90 days")
        if not math.isfinite(self.worker_lease_seconds) or not 1 <= self.worker_lease_seconds <= 120:
            raise ValueError("Worker lease must be between 1 and 120 seconds")
        if not math.isfinite(self.worker_heartbeat_seconds) or not 0.1 <= self.worker_heartbeat_seconds < self.worker_lease_seconds / 2:
            raise ValueError("Worker heartbeat must be positive and less than half the lease")
        if not math.isfinite(self.worker_poll_seconds) or not 0.01 <= self.worker_poll_seconds <= 30:
            raise ValueError("Worker poll interval must be between 0.01 and 30 seconds")
        if self.environment not in {"development", "test"}:
            raise ValueError("Milestone 3 supports local development only; public deployment security is not established")
        if not 60 <= self.auth_session_seconds <= 86400:
            raise ValueError("Authentication session lifetime must be between 60 and 86400 seconds")
        if not 1 <= self.auth_rate_window_seconds <= 3600 or not 1 <= self.auth_account_limit <= self.auth_ip_limit <= 1000:
            raise ValueError("Invalid authentication rate limits")
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
