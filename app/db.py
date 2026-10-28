from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import DATABASE_URL

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    # Needed so request threads can share the same engine.
    connect_args["check_same_thread"] = False
    connect_args["timeout"] = 30

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)


def _configure_sqlite_connection(dbapi_conn, _connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
    # We start transactions ourselves with BEGIN IMMEDIATE.
    dbapi_conn.isolation_level = None


def _sqlite_begin_immediate(conn):
    conn.execute(text("BEGIN IMMEDIATE"))


if DATABASE_URL.startswith("sqlite"):
    event.listen(engine, "connect", _configure_sqlite_connection)
    event.listen(engine, "begin", _sqlite_begin_immediate)


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def begin_immediate(session):
    """Open a write lock before we read stock/coupons (see DECISIONS.md)."""
    session.connection()
