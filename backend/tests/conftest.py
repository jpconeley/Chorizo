import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("CHORIZO_JWT_SECRET", "test-secret-that-is-at-least-32-bytes-long")

import chorizo.models  # noqa: E402, F401
from chorizo import seed
from chorizo.analytics import service
from chorizo.api.main import create_app
from chorizo.db import Base, get_session


@pytest.fixture
def session():
    # In-memory SQLite keeps tests self-contained; migrations are tested against Postgres separately.
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as s:
        yield s


@pytest.fixture
def seeded(session):
    seed.seed_reference(session)
    seed.seed_demo(session)
    service.refresh_estimates(session)
    return session


@pytest.fixture
def client(seeded):
    app = create_app()
    app.dependency_overrides[get_session] = lambda: seeded
    return TestClient(app)


@pytest.fixture
def login(client):
    def _login(plan: str) -> dict[str, str]:
        response = client.post(
            "/v1/auth/login",
            json={"email": f"{plan}@chorizo-demo.example.com", "password": seed.DEMO_PASSWORD},
        )
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _login
