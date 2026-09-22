import os
from pathlib import Path

TEST_DB = Path(__file__).parent / "test_hireai.db"
if TEST_DB.exists(): TEST_DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB}"
os.environ["JWT_SECRET"] = "test-secret"

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_signup_login_and_role_protection():
    r = client.post('/api/auth/signup', json={
        'name': 'Test Candidate', 'email': 'candidate@example.com',
        'password': 'secret123', 'confirm_password': 'secret123', 'role': 'candidate'
    })
    assert r.status_code == 200

    duplicate = client.post('/api/auth/signup', json={
        'name': 'Test Candidate', 'email': 'candidate@example.com',
        'password': 'secret123', 'confirm_password': 'secret123', 'role': 'candidate'
    })
    assert duplicate.status_code == 409

    wrong_password = client.post('/api/auth/login', json={
        'email': 'candidate@example.com', 'password': 'wrong123', 'role': 'candidate'
    })
    assert wrong_password.status_code == 401

    wrong_role = client.post('/api/auth/login', json={
        'email': 'candidate@example.com', 'password': 'secret123', 'role': 'recruiter'
    })
    assert wrong_role.status_code == 403

    login = client.post('/api/auth/login', json={
        'email': 'candidate@example.com', 'password': 'secret123', 'role': 'candidate'
    })
    assert login.status_code == 200
    token = login.json()['access_token']

    protected = client.get('/api/me', headers={'Authorization': f'Bearer {token}'})
    assert protected.status_code == 200
    assert protected.json()['role'] == 'candidate'

    recruiter_only = client.get('/api/recruiter/jobs', headers={'Authorization': f'Bearer {token}'})
    assert recruiter_only.status_code == 403
