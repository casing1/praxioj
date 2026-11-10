"""SQLAlchemy infrastructure. Schema creation is exclusively handled by Alembic."""
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.engine import make_url
from sqlalchemy.pool import StaticPool


def make_engine(url: str) -> Engine:
    options: dict = {"pool_pre_ping": True}
    if url.startswith("postgresql+psycopg://"):
        # Preserve caller options, especially isolated-test search_path. Bounded
        # waits keep a DB outage/contended row from indefinitely stalling shutdown.
        previous = make_url(url).query.get("options", "")
        options.update(pool_timeout=5, connect_args={"connect_timeout": 5,
            "options": previous + " -c statement_timeout=10000 -c lock_timeout=5000 -c idle_in_transaction_session_timeout=15000"})
    if url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url:
            options["poolclass"] = StaticPool
    engine = create_engine(url, **options)
    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def configure_sqlite(connection, _record):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=10000")
            cursor.close()
    return engine


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
