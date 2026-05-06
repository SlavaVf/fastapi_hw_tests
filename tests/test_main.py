import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app, get_db, Base, get_password_hash
from unittest.mock import Mock, patch

SQLALCHEMY_TEST_URL = 'sqlite:///./test.db'
engine = create_engine(SQLALCHEMY_TEST_URL, connect_args={'check_same_thread': False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture
def client(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()

@pytest.fixture
def auth_token(client):
    client.post('/register', params={'username': 'testuser', 'password': 'test123'})
    response = client.post('/token', data={'username': 'testuser', 'password': 'test123'})
    return response.json()['access_token']

def test_password_hashing():
    password = 'mypass123'
    hashed = get_password_hash(password)
    assert hashed != password
    assert isinstance(hashed, str)

def test_register_success(client):
    response = client.post('/register', params={'username': 'newuser', 'password': 'pass123'})
    assert response.status_code == 200
    assert 'id' in response.json()

def test_register_duplicate(client):
    client.post('/register', params={'username': 'duplicate', 'password': 'pass'})
    response = client.post('/register', params={'username': 'duplicate', 'password': 'pass'})
    assert response.status_code == 400

def test_login_success(client):
    client.post('/register', params={'username': 'logintest', 'password': 'pass123'})
    response = client.post('/token', data={'username': 'logintest', 'password': 'pass123'})
    assert response.status_code == 200
    assert 'access_token' in response.json()

def test_login_wrong_password(client):
    client.post('/register', params={'username': 'wrongpass', 'password': 'correct'})
    response = client.post('/token', data={'username': 'wrongpass', 'password': 'wrong'})
    assert response.status_code == 401

def test_invalid_token(client):
    headers = {'Authorization': 'Bearer invalid_token_12345'}
    response = client.get('/tasks', headers=headers)
    assert response.status_code == 401

def test_create_task(client, auth_token):
    headers = {'Authorization': f'Bearer {auth_token}'}
    response = client.post('/tasks', params={'title': 'My Task'}, headers=headers)
    assert response.status_code == 200
    assert response.json()['title'] == 'My Task'

def test_create_task_with_all_params(client, auth_token):
    headers = {'Authorization': f'Bearer {auth_token}'}
    response = client.post(
        '/tasks',
        params={
            'title': 'Full Task',
            'description': 'Full description',
            'priority': 'high'
        },
        headers=headers
    )
    assert response.status_code == 200
    assert response.json()['description'] == 'Full description'
    assert response.json()['priority'] == 'high'

def test_create_task_unauthorized(client):
    response = client.post('/tasks', params={'title': 'No Auth'})
    assert response.status_code == 401

def test_get_tasks(client, auth_token):
    headers = {'Authorization': f'Bearer {auth_token}'}
    client.post('/tasks', params={'title': 'Task 1'}, headers=headers)
    client.post('/tasks', params={'title': 'Task 2'}, headers=headers)

    response = client.get('/tasks', headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 2

def test_get_task(client, auth_token):
    headers = {'Authorization': f'Bearer {auth_token}'}
    create = client.post('/tasks', params={'title': 'Specific'}, headers=headers)
    task_id = create.json()['id']

    response = client.get(f'/tasks/{task_id}', headers=headers)
    assert response.status_code == 200
    assert response.json()['title'] == 'Specific'

def test_get_task_not_found(client, auth_token):
    headers = {'Authorization': f'Bearer {auth_token}'}
    response = client.get('/tasks/99999', headers=headers)
    assert response.status_code == 404

def test_update_task(client, auth_token):
    headers = {'Authorization': f'Bearer {auth_token}'}
    create = client.post('/tasks', params={'title': 'Old'}, headers=headers)
    task_id = create.json()['id']

    response = client.put(f'/tasks/{task_id}', params={'title': 'New', 'status': 'completed'}, headers=headers)
    assert response.status_code == 200
    assert response.json()['title'] == 'New'
    assert response.json()['status'] == 'completed'

def test_update_task_partial(client, auth_token):
    headers = {'Authorization': f'Bearer {auth_token}'}
    create = client.post('/tasks',
                         params={'title': 'Test', 'description': 'Old desc', 'status': 'pending', 'priority': 'low'},
                         headers=headers)
    task_id = create.json()['id']

    r1 = client.put(f'/tasks/{task_id}', params={'priority': 'high'}, headers=headers)
    assert r1.json()['priority'] == 'high'

    r2 = client.put(f'/tasks/{task_id}', params={'description': 'New desc'}, headers=headers)
    assert r2.json()['description'] == 'New desc'

    r3 = client.put(f'/tasks/{task_id}', params={'status': 'completed'}, headers=headers)
    assert r3.json()['status'] == 'completed'

def test_update_nonexistent_task(client, auth_token):
    headers = {'Authorization': f'Bearer {auth_token}'}
    response = client.put('/tasks/99999', params={'title': 'New'}, headers=headers)
    assert response.status_code == 404

def test_delete_task(client, auth_token):
    headers = {'Authorization': f'Bearer {auth_token}'}
    create = client.post('/tasks', params={'title': 'To Delete'}, headers=headers)
    task_id = create.json()['id']

    response = client.delete(f'/tasks/{task_id}', headers=headers)
    assert response.status_code == 200

    get_response = client.get(f'/tasks/{task_id}', headers=headers)
    assert get_response.status_code == 404

def test_delete_nonexistent_task(client, auth_token):
    headers = {'Authorization': f'Bearer {auth_token}'}
    response = client.delete('/tasks/99999', headers=headers)
    assert response.status_code == 404

def test_get_top_tasks(client, auth_token):
    headers = {'Authorization': f'Bearer {auth_token}'}
    client.post('/tasks', params={'title': 'High', 'priority': 'high'}, headers=headers)
    client.post('/tasks', params={'title': 'Medium', 'priority': 'medium'}, headers=headers)
    client.post('/tasks', params={'title': 'Low', 'priority': 'low'}, headers=headers)

    response = client.get('/tasks/top/2', headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 2

    response2 = client.get('/tasks/top/10', headers=headers)
    assert response2.status_code == 200
    assert len(response2.json()) == 3

    response3 = client.get('/tasks/top/0', headers=headers)
    assert response3.status_code == 200
    assert len(response3.json()) == 0

def test_search_tasks(client, auth_token):
    headers = {'Authorization': f'Bearer {auth_token}'}
    client.post('/tasks', params={'title': 'Special Task', 'description': 'Important'}, headers=headers)

    response1 = client.get('/tasks', params={'search': 'Special'}, headers=headers)
    assert response1.status_code == 200
    assert len(response1.json()) == 1
    response2 = client.get('/tasks', params={'search': 'nonexistentword'}, headers=headers)
    assert response2.status_code == 200
    assert len(response2.json()) == 0

def test_sort_tasks(client, auth_token):
    headers = {'Authorization': f'Bearer {auth_token}'}
    client.post('/tasks', params={'title': 'B Task'}, headers=headers)
    client.post('/tasks', params={'title': 'A Task'}, headers=headers)
    response_asc = client.get('/tasks', params={'sort_by': 'title'}, headers=headers)
    titles_asc = [t['title'] for t in response_asc.json()]
    assert titles_asc == sorted(titles_asc)

    response_desc = client.get('/tasks', params={'sort_by': 'title', 'sort_desc': True}, headers=headers)
    titles_desc = [t['title'] for t in response_desc.json()]
    assert titles_desc == sorted(titles_desc, reverse=True)

    response_status = client.get('/tasks', params={'sort_by': 'status'}, headers=headers)
    assert response_status.status_code == 200

    response_created = client.get('/tasks', params={'sort_by': 'created_at'}, headers=headers)
    assert response_created.status_code == 200


def test_user_isolation(client):
    client.post('/register', params={'username': 'user1', 'password': 'pass1'})
    token1 = client.post('/token', data={'username': 'user1', 'password': 'pass1'}).json()['access_token']
    headers1 = {'Authorization': f'Bearer {token1}'}

    client.post('/register', params={'username': 'user2', 'password': 'pass2'})
    token2 = client.post('/token', data={'username': 'user2', 'password': 'pass2'}).json()['access_token']
    headers2 = {'Authorization': f'Bearer {token2}'}

    task = client.post('/tasks', params={'title': 'Secret'}, headers=headers1)
    task_id = task.json()['id']

    response = client.get(f'/tasks/{task_id}', headers=headers2)
    assert response.status_code == 404


def test_get_current_user_with_mock():
    mock_db = Mock()
    mock_token = 'fake_token'

    with patch('src.main.jwt.decode') as mock_decode:
        mock_decode.return_value = {'sub': 'testuser'}
        mock_user = Mock(username='testuser', id=1)
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        from src.main import get_current_user
        user = get_current_user(mock_token, mock_db)

        assert user.username == 'testuser'
        mock_decode.assert_called_once()


def test_verify_password_with_mock():
    from src.main import verify_password

    with patch('src.main.pwd_context.verify') as mock_verify:
        mock_verify.return_value = True
        result = verify_password('testpass', 'hashed')
        assert result is True
        mock_verify.assert_called_once_with('testpass', 'hashed')