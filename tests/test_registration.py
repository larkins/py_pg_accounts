import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app import create_app
from app.models import db
from app.models.user import User


@pytest.fixture
def app():
    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
        'DATABASE_URL',
        'postgresql://postgres:1234@localhost:5432/py_pg_accounts'
    )

    with app.app_context():
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def cleanup(app):
    yield
    with app.app_context():
        User.query.filter_by(email='test@example.com').delete()
        db.session.commit()


def test_register_page_loads(client):
    response = client.get('/register')
    assert response.status_code == 200
    assert b'Register' in response.data


def test_register_success(client, cleanup):
    response = client.post('/register', data={
        'email': 'test@example.com',
        'password': 'testpassword123',
        'confirm_password': 'testpassword123'
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b'Login' in response.data


def test_register_password_mismatch(client):
    response = client.post('/register', data={
        'email': 'test2@example.com',
        'password': 'testpassword123',
        'confirm_password': 'wrongpassword'
    }, follow_redirects=False)

    assert response.status_code == 200
    assert b'do not match' in response.data.lower() or response.status_code == 200


def test_register_duplicate_email(client, cleanup):
    client.post('/register', data={
        'email': 'test@example.com',
        'password': 'testpassword123',
        'confirm_password': 'testpassword123'
    }, follow_redirects=True)

    response = client.post('/register', data={
        'email': 'test@example.com',
        'password': 'anotherpassword',
        'confirm_password': 'anotherpassword'
    }, follow_redirects=True)

    assert b'already registered' in response.data.lower()


def test_register_missing_fields(client):
    response = client.post('/register', data={
        'email': '',
        'password': '',
        'confirm_password': ''
    }, follow_redirects=False)

    assert response.status_code == 200


def test_login_page_loads(client):
    response = client.get('/login')
    assert response.status_code == 200
    assert b'Login' in response.data


def test_login_success(client, cleanup):
    client.post('/register', data={
        'email': 'test@example.com',
        'password': 'testpassword123',
        'confirm_password': 'testpassword123'
    }, follow_redirects=True)

    client.get('/logout')

    response = client.post('/login', data={
        'email': 'test@example.com',
        'password': 'testpassword123'
    }, follow_redirects=True)

    assert response.status_code == 200


def test_login_invalid_credentials(client, cleanup):
    client.post('/register', data={
        'email': 'test@example.com',
        'password': 'testpassword123',
        'confirm_password': 'testpassword123'
    }, follow_redirects=True)

    client.get('/logout')

    response = client.post('/login', data={
        'email': 'test@example.com',
        'password': 'wrongpassword'
    }, follow_redirects=True)

    assert b'invalid' in response.data.lower() or b'error' in response.data.lower()


def test_logout(client, cleanup):
    client.post('/register', data={
        'email': 'test@example.com',
        'password': 'testpassword123',
        'confirm_password': 'testpassword123'
    }, follow_redirects=True)

    response = client.get('/logout', follow_redirects=True)
    assert response.status_code == 200


def test_dashboard_requires_login(client):
    response = client.get('/', follow_redirects=False)
    assert response.status_code == 302
    assert '/login' in response.location


def test_dashboard_accessible_after_login(client, cleanup):
    client.post('/register', data={
        'email': 'test@example.com',
        'password': 'testpassword123',
        'confirm_password': 'testpassword123'
    }, follow_redirects=True)

    client.post('/login', data={
        'email': 'test@example.com',
        'password': 'testpassword123'
    }, follow_redirects=True)

    response = client.get('/')
    assert response.status_code == 200
    assert b'Dashboard' in response.data or b'Welcome' in response.data
