import uuid
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db import Base, get_db
from app.db_triggers import AUDIT_EVENT_IMMUTABILITY_SQL
from app.main import app
from app.models import AppUser, Tenant, TenantMembership
from app.security import create_access_token, hash_password

TEST_DB_NAME = "audit_test"


def _replace_db_name(url: str, db_name: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{db_name}", "", ""))


@pytest.fixture(scope="session", autouse=True)
def _test_database():
    admin_url = _replace_db_name(settings.database_url, "postgres").replace("postgresql+psycopg", "postgresql")
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB_NAME}")
        conn.execute(f"CREATE DATABASE {TEST_DB_NAME}")
    yield
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB_NAME}")


@pytest.fixture(scope="session")
def engine(_test_database):
    test_url = _replace_db_name(settings.database_url, TEST_DB_NAME)
    eng = create_engine(test_url, future=True)
    Base.metadata.create_all(eng)
    with eng.begin() as conn:
        for statement in AUDIT_EVENT_IMMUTABILITY_SQL:
            conn.execute(text(statement))
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine):
    SessionTest = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = SessionTest()
    try:
        yield session
    finally:
        session.close()
        with engine.begin() as conn:
            # audit_event's immutability trigger (see app/db_triggers.py) blocks
            # DELETE too — briefly disable it so between-test cleanup can still
            # truncate it, then restore it before the next test runs.
            conn.execute(text("ALTER TABLE audit_event DISABLE TRIGGER ALL"))
            for table in reversed(Base.metadata.sorted_tables):
                conn.execute(table.delete())
            conn.execute(text("ALTER TABLE audit_event ENABLE TRIGGER ALL"))


@pytest.fixture
def client(db):
    def _get_db_override():
        yield db

    app.dependency_overrides[get_db] = _get_db_override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def make_principal(db):
    """Creates a tenant + user + admin membership directly (bypassing the signup
    endpoint, since these tests are about what happens *after* auth, not auth
    itself) and returns (auth_headers, user_id, tenant_id)."""

    def _make(role: str = "admin", tenant_id: uuid.UUID | None = None) -> tuple[dict, uuid.UUID, uuid.UUID]:
        tenant = Tenant(id=tenant_id or uuid.uuid4(), name="Test Tenant")
        if tenant_id is None:
            db.add(tenant)
        else:
            existing = db.get(Tenant, tenant_id)
            if existing is None:
                db.add(tenant)
            else:
                tenant = existing

        user = AppUser(email=f"{uuid.uuid4()}@example.com", password_hash=hash_password("not-used-in-tests"))
        db.add(user)
        db.flush()

        membership = TenantMembership(tenant_id=tenant.id, user_id=user.id, role=role)
        db.add(membership)
        db.commit()

        token = create_access_token(user.id, tenant.id)
        return {"Authorization": f"Bearer {token}"}, user.id, tenant.id

    return _make
