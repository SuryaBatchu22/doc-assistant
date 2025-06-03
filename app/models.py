# app/models.py

from flask_login import UserMixin
from app.utils import db 


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)  # will replace username
    password = db.Column(db.String(128), nullable=False)
    
class ChatSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(255), default="New Chat")
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    logs = db.relationship('ChatLog', backref='session', cascade="all, delete-orphan")

class ChatLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('chat_session.id'), nullable=True)  # Nullable for guests
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, server_default=db.func.now())

# Document metadata storage (optional)
class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    session_id = db.Column(db.Integer, nullable=False)
    upload_time = db.Column(db.DateTime, server_default=db.func.now())