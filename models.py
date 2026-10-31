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
    wallet_address = db.Column(db.String(100), nullable=True)

class Broker(db.Model):
    __tablename__ = 'brokers'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    organization_id = db.Column(db.String(36), db.ForeignKey('organizations.id'), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    professional_title = db.Column(db.String(100))
    license_number = db.Column(db.String(100), unique=True, nullable=False)
    profile_photo_url = db.Column(db.String(255), nullable=True)
    bio = db.Column(db.Text, nullable=True)
    
    # NEW: Broker Work Location
    working_province = db.Column(db.String(100), nullable=True)
    working_district = db.Column(db.String(100), nullable=True)
    
    verification_code = db.Column(db.String(255), nullable=True) 
    
    # Secure code for clients to leave reviews
    review_code = db.Column(db.String(20), unique=True, nullable=True)
    
    status = db.Column(db.String(20), default='Pending Registration')
    
    verified_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    
    # FIX: Made nullable=True to allow public self-registration without breaking the database
    registered_by = db.Column(db.String(36), db.ForeignKey('association_admins.id'), nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    properties = db.relationship('Property', backref='broker', lazy=True, cascade="all, delete-orphan")
    reviews = db.relationship('Review', backref='broker', lazy=True, cascade="all, delete-orphan")

class Property(db.Model):
    __tablename__ = 'properties'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    broker_id = db.Column(db.String(36), db.ForeignKey('brokers.id'), nullable=False)
    
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Numeric(12, 2), nullable=False)
    listing_type = db.Column(db.String(50), nullable=False) # e.g., 'For Rent', 'For Sale'
    
    # Bedrooms and Bathrooms
    bedrooms = db.Column(db.Integer, nullable=True)
    bathrooms = db.Column(db.Integer, nullable=True)
    
    # Direct string columns for locations (handled by static JSON on frontend)
    province = db.Column(db.String(100), nullable=False)
    district = db.Column(db.String(100), nullable=False)
    sector = db.Column(db.String(100), nullable=False)
    cell = db.Column(db.String(100), nullable=False)
    village = db.Column(db.String(100), nullable=False)
    
    property_image = db.Column(db.String(255), nullable=True) # Cloudinary URL
    upi_number = db.Column(db.String(50), nullable=True) # Land Documentation Number
    
    verification_status = db.Column(db.String(50), default='Pending') # Pending, Verified, Rejected
    is_available = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    images = db.relationship('PropertyImage', backref='property', lazy=True, cascade="all, delete-orphan")

class Review(db.Model):
    __tablename__ = 'reviews'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    broker_id = db.Column(db.String(36), db.ForeignKey('brokers.id'), nullable=False)
    
    client_name = db.Column(db.String(100), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=False)
    
    is_approved = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class PropertyImage(db.Model):
    __tablename__ = 'property_images'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    property_id = db.Column(db.String(36), db.ForeignKey('properties.id'), nullable=False)
    
    # Cloudinary URL
    image_url = db.Column(db.String(255), nullable=False)
    
    public_id = db.Column(db.String(255), nullable=False) 
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Audit logs
class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    
    actor_type = db.Column(db.String(50), nullable=False)
    actor_id = db.Column(db.String(36), nullable=False)
    
    action = db.Column(db.String(100), nullable=False)
    
    target_type = db.Column(db.String(50), nullable=True)
    target_id = db.Column(db.String(36), nullable=True)
    
    description = db.Column(db.Text, nullable=False)
    
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)