import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("COUPON_ORDER_INTERVAL", "5")
os.environ.setdefault("COUPON_DISCOUNT_PERCENT", "10")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    url = "sqlite:///{}".format(db_path)
    monkeypatch.setenv("DATABASE_URL", url)

    import app.config as config
    import app.db as db_module
    from app.db import (
        Base,
        _configure_sqlite_connection,
        _sqlite_begin_immediate,
        get_db,
    )
    from app.main import app
    from app.seed import seed_products

    monkeypatch.setattr(config, "DATABASE_URL", url)
    monkeypatch.setattr(db_module, "DATABASE_URL", url)

    # File DB (not in-memory) so concurrent threads can each open a connection.
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    event.listen(engine, "connect", _configure_sqlite_connection)
    event.listen(engine, "begin", _sqlite_begin_immediate)

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestingSessionLocal)

    Base.metadata.create_all(bind=engine)
    seed_db = TestingSessionLocal()
    seed_products(seed_db)
    seed_db.close()

    def _override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
