from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime, timedelta
from jose import jwt
from passlib.context import CryptContext

# db
SQLALCHEMY_DATABASE_URL = 'sqlite:///./tasks.db'
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={'check_same_thread': False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)

class Task(Base):
    __tablename__ = 'tasks'
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    description = Column(String, nullable=True)
    status = Column(String, default='pending')
    priority = Column(String, default='medium')
    created_at = Column(DateTime, default=datetime.now)
    owner_id = Column(Integer)

Base.metadata.create_all(bind=engine)

#authentification
SECRET_KEY = 'secret'
ALGORITHM = 'HS256'
pwd_context = CryptContext(schemes=['pbkdf2_sha256'], deprecated='auto')
oauth2_scheme = OAuth2PasswordBearer(tokenUrl='token')

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        username = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM]).get('sub')
        if username is None:
            raise HTTPException(status_code=401, detail='Invalid token')
        user = db.query(User).filter(User.username == username).first()
        if user is None:
            raise HTTPException(status_code=401, detail='User not found')
        return user
    except:
        raise HTTPException(status_code=401, detail='Invalid token')

#fastapi
app = FastAPI()

@app.post('/register')
def register(username: str, password: str, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail='Username already exists')

    new_user = User(username=username, hashed_password=get_password_hash(password))
    db.add(new_user)
    db.commit()

    return {'id': new_user.id, 'username': new_user.username}

@app.post('/token')
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail='Incorrect username or password')

    token_data = {'sub': user.username, 'exp': datetime.now() + timedelta(minutes=30)}
    token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)

    return {'access_token': token, 'token_type': 'bearer'}

@app.post('/tasks')
def create_task(title: str, description: str = None, priority: str = 'medium', db: Session = Depends(get_db),
                current_user=Depends(get_current_user)):
    new_task = Task(title=title, description=description, priority=priority, owner_id=current_user.id)
    db.add(new_task)
    db.commit()
    db.refresh(new_task)

    return {
        'id': new_task.id,
        'title': new_task.title,
        'description': new_task.description,
        'status': new_task.status,
        'priority': new_task.priority,
        'created_at': new_task.created_at,
        'owner_id': new_task.owner_id
    }

@app.get('/tasks')
def get_tasks(sort_by: str = None, sort_desc: bool = False, search: str = None, db: Session = Depends(get_db),
        current_user=Depends(get_current_user)):
    tasks_query = db.query(Task).filter(Task.owner_id == current_user.id)

    if search:
        tasks_query = tasks_query.filter(Task.title.contains(search) | Task.description.contains(search))

    if sort_by:
        if sort_by == 'title':
            if sort_desc:
                tasks_query = tasks_query.order_by(Task.title.desc())
            else:
                tasks_query = tasks_query.order_by(Task.title)
        elif sort_by == 'status':
            if sort_desc:
                tasks_query = tasks_query.order_by(Task.status.desc())
            else:
                tasks_query = tasks_query.order_by(Task.status)
        elif sort_by == 'created_at':
            if sort_desc:
                tasks_query = tasks_query.order_by(Task.created_at.desc())
            else:
                tasks_query = tasks_query.order_by(Task.created_at)

    tasks = tasks_query.all()
    return [
        {
            'id': task.id,
            'title': task.title,
            'description': task.description,
            'status': task.status,
            'priority': task.priority,
            'created_at': task.created_at,
            'owner_id': task.owner_id
        }
        for task in tasks
    ]

@app.get('/tasks/top/{n}')
def get_top_tasks(n: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    all_tasks = db.query(Task).filter(Task.owner_id == current_user.id).all()
    priority_values = {'high': 1, 'medium': 2, 'low': 3}
    all_tasks.sort(key=lambda task: priority_values.get(task.priority, float('inf')))
    top_tasks = all_tasks[:n]
    return [
        {
            'id': task.id,
            'title': task.title,
            'description': task.description,
            'status': task.status,
            'priority': task.priority,
            'created_at': task.created_at,
            'owner_id': task.owner_id
        }
        for task in top_tasks
    ]

@app.get('/tasks/{task_id}')
def get_task(task_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    task = db.query(Task).filter(Task.id == task_id, Task.owner_id == current_user.id).first()

    if not task:
        raise HTTPException(status_code=404, detail='Task not found')

    return {
        'id': task.id,
        'title': task.title,
        'description': task.description,
        'status': task.status,
        'priority': task.priority,
        'created_at': task.created_at,
        'owner_id': task.owner_id
    }

@app.put('/tasks/{task_id}')
def update_task(task_id: int, title: str = None, description: str = None, status: str = None,
        priority: str = None, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    task = db.query(Task).filter(Task.id == task_id, Task.owner_id == current_user.id).first()

    if not task:
        raise HTTPException(status_code=404, detail='Task not found')
    
    if title is not None:
        task.title = title
    if description is not None:
        task.description = description
    if status is not None:
        task.status = status
    if priority is not None:
        task.priority = priority

    db.commit()
    db.refresh(task)

    return {
        'id': task.id,
        'title': task.title,
        'description': task.description,
        'status': task.status,
        'priority': task.priority,
        'created_at': task.created_at,
        'owner_id': task.owner_id
    }

@app.delete('/tasks/{task_id}')
def delete_task(task_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    task = db.query(Task).filter(Task.id == task_id, Task.owner_id == current_user.id).first()

    if not task:
        raise HTTPException(status_code=404, detail='Task not found')

    db.delete(task)
    db.commit()

    return {'message': 'Task deleted successfully'}