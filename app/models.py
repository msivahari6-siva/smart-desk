from datetime import datetime
from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='customer', nullable=False)  # 'admin' or 'customer'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Ticket(db.Model):
    __tablename__ = 'tickets'

    id = db.Column(db.Integer, primary_key=True)
    reference_no = db.Column(db.String(20), unique=True, nullable=False, index=True)
    customer_name = db.Column(db.String(100), nullable=False)
    customer_email = db.Column(db.String(120), nullable=False, index=True)
    subject = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    
    # Allowed: Open, In Progress, Resolved, Closed
    status = db.Column(db.String(20), default='Open', nullable=False, index=True)
    # Allowed: Technical, Billing, Account, General
    category = db.Column(db.String(30), default='General', nullable=False, index=True)
    # Allowed: Low, Medium, High
    priority = db.Column(db.String(20), default='Medium', nullable=False, index=True)
    
    ai_summary = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    history = db.relationship('TicketStatusHistory', backref='ticket', cascade='all, delete-orphan', order_by='desc(TicketStatusHistory.created_at)')

    @staticmethod
    def generate_reference_no(next_id):
        return f"TKT-{next_id:05d}"

class TicketStatusHistory(db.Model):
    __tablename__ = 'ticket_status_history'

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id', ondelete='CASCADE'), nullable=False)
    previous_status = db.Column(db.String(20), nullable=False)
    new_status = db.Column(db.String(20), nullable=False)
    remark = db.Column(db.Text, nullable=False)
    changed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='status_updates')