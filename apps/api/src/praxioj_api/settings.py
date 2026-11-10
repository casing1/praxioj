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
    auth_max_sessions: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_AUTH_MAX_SESSIONS", "5")))
    auth_reauthentication_seconds: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_AUTH_REAUTHENTICATION_SECONDS", "300")))
    api_rate_window_seconds: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_API_RATE_WINDOW_SECONDS", "60")))
    api_ip_limit: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_API_IP_LIMIT", "600")))
    auth_rate_window_seconds: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_AUTH_RATE_WINDOW_SECONDS", "300")))
    auth_ip_limit: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_AUTH_IP_LIMIT", "30")))
    auth_account_limit: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_AUTH_ACCOUNT_LIMIT", "10")))
    allowed_hosts: tuple[str, ...] = ("localhost", "127.0.0.1", "[::1]")
    allowed_origins: tuple[str, ...] = tuple(
        f"{scheme}://{host}:{port}" for scheme in ("http", "https")
        for host in ("localhost", "127.0.0.1", "[::1]") for port in (5173, 8000, 8080)
    ) + tuple(f"https://{host}" for host in ("localhost", "127.0.0.1", "[::1]"))
    max_request_bytes: int = 131_072
    export_max_bytes: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_EXPORT_MAX_BYTES", "16777216")))
    export_max_rows: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_EXPORT_MAX_ROWS", "10000")))
    trace_retention_days: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_TRACE_RETENTION_DAYS", "30")))
    trace_retention_max_days: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_TRACE_RETENTION_MAX_DAYS", "90")))
    audit_retention_days: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_AUDIT_RETENTION_DAYS", "90")))
    worker_lease_seconds: float = field(default_factory=lambda: float(os.getenv("PRAXIOJ_WORKER_LEASE_SECONDS", "15")))
    worker_heartbeat_seconds: float = field(default_factory=lambda: float(os.getenv("PRAXIOJ_WORKER_HEARTBEAT_SECONDS", "3")))
    worker_poll_seconds: float = field(default_factory=lambda: float(os.getenv("PRAXIOJ_WORKER_POLL_SECONDS", "0.5")))

    account_active_sessions: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_ACCOUNT_ACTIVE_SESSIONS", "10")))
    account_retained_sessions: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_ACCOUNT_RETAINED_SESSIONS", "100")))
    system_retained_sessions: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_SYSTEM_RETAINED_SESSIONS", "10000")))
    account_active_runs: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_ACCOUNT_ACTIVE_RUNS", "2")))
    queue_max_pending: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_QUEUE_MAX_PENDING", "100")))
    worker_max_running: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_WORKER_MAX_RUNNING", "4")))
    worker_shutdown_seconds: float = field(default_factory=lambda: float(os.getenv("PRAXIOJ_WORKER_SHUTDOWN_SECONDS", "5")))
    account_daily_model_calls: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_ACCOUNT_DAILY_MODEL_CALLS", "200")))
    problem_daily_model_calls: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_PROBLEM_DAILY_MODEL_CALLS", "2000")))
    system_daily_model_calls: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_SYSTEM_DAILY_MODEL_CALLS", "10000")))
    account_daily_tool_calls: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_ACCOUNT_DAILY_TOOL_CALLS", "400")))
    problem_daily_tool_calls: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_PROBLEM_DAILY_TOOL_CALLS", "4000")))
    system_daily_tool_calls: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_SYSTEM_DAILY_TOOL_CALLS", "20000")))
    account_daily_token_allowance: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_ACCOUNT_DAILY_TOKEN_ALLOWANCE", "2000000")))
    problem_daily_token_allowance: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_PROBLEM_DAILY_TOKEN_ALLOWANCE", "20000000")))
    system_daily_token_allowance: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_SYSTEM_DAILY_TOKEN_ALLOWANCE", "100000000")))
    call_token_reservation: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_CALL_TOKEN_RESERVATION", "16384")))
    session_artifact_max_bytes: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_SESSION_ARTIFACT_MAX_BYTES", "1048576")))
    session_trace_max_bytes: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_SESSION_TRACE_MAX_BYTES", "8388608")))
    session_trace_max_events: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_SESSION_TRACE_MAX_EVENTS", "2000")))
    account_artifact_capacity_bytes: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_ACCOUNT_ARTIFACT_CAPACITY_BYTES", "16777216")))
    system_artifact_capacity_bytes: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_SYSTEM_ARTIFACT_CAPACITY_BYTES", "268435456")))
    account_trace_capacity_bytes: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_ACCOUNT_TRACE_CAPACITY_BYTES", "268435456")))
    system_trace_capacity_bytes: int = field(default_factory=lambda: int(os.getenv("PRAXIOJ_SYSTEM_TRACE_CAPACITY_BYTES", "2147483648")))

    def __post_init__(self) -> None:
        quota_names = ("account_active_sessions", "account_retained_sessions", "system_retained_sessions",
            "account_active_runs", "queue_max_pending", "worker_max_running", "call_token_reservation",
            "session_artifact_max_bytes", "session_trace_max_bytes", "session_trace_max_events",
            "account_artifact_capacity_bytes", "system_artifact_capacity_bytes",
            "account_trace_capacity_bytes", "system_trace_capacity_bytes")
        quota_names += tuple(prefix + suffix for prefix in ("account", "problem", "system")
            for suffix in ("_daily_model_calls", "_daily_tool_calls", "_daily_token_allowance"))
        if any(type(getattr(self, name)) is not int or not 1 <= getattr(self, name) <= 10**12 for name in quota_names):
            raise ValueError("Quota limits must be positive bounded integers")
        if self.worker_max_running > 64 or self.queue_max_pending > 10000 or self.system_retained_sessions > 100000:
            raise ValueError("Operational capacity exceeds the supported development bounds")
        if self.session_trace_max_events > 10000 or self.session_trace_max_bytes > 64 * 1024 * 1024:
            raise ValueError("Per-session trace capacity exceeds the supported bounds")
        if not math.isfinite(self.worker_shutdown_seconds) or not 0 <= self.worker_shutdown_seconds <= 30:
            raise ValueError("Worker graceful drain must be between zero and 30 seconds")
        if not 1024 <= self.export_max_bytes <= 67_108_864 or not 100 <= self.export_max_rows <= 100_000:
            raise ValueError("Export limits must be 1 KiB–64 MiB and 100–100000 rows")
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
        if not 1 <= self.auth_max_sessions <= 10:
            raise ValueError("Active authentication session cap must be between 1 and 10")
        if not 60 <= self.auth_reauthentication_seconds <= 900:
            raise ValueError("Password confirmation lifetime must be between 60 and 900 seconds")
        if not 1 <= self.api_rate_window_seconds <= 3600 or not 1 <= self.api_ip_limit <= 10000:
            raise ValueError("Invalid API request rate limits")
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
