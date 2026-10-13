import uuid
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def generate_uuid():
    return str(uuid.uuid4())

class SuperAdmin(db.Model):
    __tablename__ = 'super_admins'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    organizations_created = db.relationship('Organization', backref='creator', lazy=True)
    admins_created = db.relationship('AssociationAdmin', backref='creator', lazy=True)

class Organization(db.Model):
    __tablename__ = 'organizations'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    name = db.Column(db.String(150), unique=True, nullable=False)
    registration_number = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    address = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='Active')  # 'Active' or 'Suspended'
    
    created_by = db.Column(db.String(36), db.ForeignKey('super_admins.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship to link the organization to its admins
    admins = db.relationship('AssociationAdmin', backref='organization', lazy=True)

class AssociationAdmin(db.Model):
    __tablename__ = 'association_admins'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    
    organization_id = db.Column(db.String(36), db.ForeignKey('organizations.id'), nullable=False)
    account_status = db.Column(db.String(20), default='Active')  # 'Active' or 'Revoked'
    
    approved_at = db.Column(db.DateTime, nullable=True)
    created_by = db.Column(db.String(36), db.ForeignKey('super_admins.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)