import os
from pathlib import Path

TEST_DB = Path(__file__).parent / "test_validation.db"
if TEST_DB.exists(): TEST_DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB}"
os.environ["JWT_SECRET"] = "test-secret-2"

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_signup_password_validation():
    r = client.post('/api/auth/signup', json={
        'name': 'Validation User', 'email': 'validation@example.com',
        'password': 'abc', 'confirm_password': 'abc', 'role': 'candidate'
    })
    assert r.status_code == 422

    r = client.post('/api/auth/signup', json={
        'name': 'Validation User', 'email': 'validation@example.com',
        'password': 'abcdef', 'confirm_password': 'different', 'role': 'candidate'
    })
    assert r.status_code == 400
