from flask import Blueprint, render_template, session, redirect, url_for, flash, request
from functools import wraps
from models import db, Broker, Organization, Property, Review, PropertyImage
import random
import string
import cloudinary.uploader
import cloudinary.api

# Create the Blueprint
broker_bp = Blueprint('broker', __name__, template_folder="templates", static_folder="static")

# Protection Decorator - UPGRADED
def broker_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'broker_id' not in session:
            flash("Please log in to access the Broker Portal.", "warning")
            return redirect(url_for('landing.login_portal'))
            
        # THE FIX: Check if they were suspended while already logged in
        broker = Broker.query.get(session['broker_id'])
        if not broker or broker.status == 'Suspended':
            session.pop('broker_id', None)
            flash("Your account has been suspended. Please contact your organization.", "error")
            return redirect(url_for('landing.login_portal'))
            
        return f(*args, **kwargs)
    return decorated_function

@broker_bp.route('/dashboard')
@broker_login_required
def dashboard():
    broker = Broker.query.get(session['broker_id'])
    
    # 1. Generate Review Code
    if not broker.review_code:
        while True:
            random_chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            new_code = f"REV-{random_chars}"
            if not Broker.query.filter_by(review_code=new_code).first():
                broker.review_code = new_code
                db.session.commit()
                break

    # 2. Get their organization details
    organization = Organization.query.get(broker.organization_id)
    
    # 3. Get quick stats
    active_properties = Property.query.filter_by(broker_id=broker.id, is_available=True).count()
    pending_reviews = Review.query.filter_by(broker_id=broker.id, is_approved=False).count()
    
    return render_template(
        'broker_dashboard.html', 
        broker=broker, 
        organization=organization,
        active_properties=active_properties,
        pending_reviews=pending_reviews
    )

@broker_bp.route('/properties')
@broker_login_required
def my_properties():
    broker = Broker.query.get(session['broker_id'])
    
    # Fetch all properties belonging to this broker, newest first
    properties = Property.query.filter_by(broker_id=broker.id).order_by(Property.created_at.desc()).all()
    
    return render_template('broker_properties.html', broker=broker, properties=properties)

@broker_bp.route('/properties/add', methods=['GET', 'POST'])
@broker_login_required
def add_property():
    broker = Broker.query.get(session['broker_id'])
    
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        price = request.form.get('price')
        listing_type = request.form.get('listing_type')
        location = request.form.get('location')
        upi_number = request.form.get('upi_number')
        
        # 1. Create the Property first so we get its ID
        new_property = Property(
            broker_id=broker.id,
            title=title,
            description=description,
            price=price,
            listing_type=listing_type,
            location=location,
            upi_number=upi_number,
            verification_status='Pending'
        )
        db.session.add(new_property)
        db.session.flush() # This safely generates the new_property.id without permanently committing yet
        
        # 2. Handle Multiple Images Upload to Cloudinary
        # HTML file inputs accepting multiple files use getlist()
        images = request.files.getlist('images')
        
        for file in images:
            if file.filename != '':
                # Organize Cloudinary bucket beautifully: RREBP / Brokers / RWA-123... / Properties / property-uuid
                folder_path = f"RREBP/Brokers/{broker.license_number}/Properties/{new_property.id}"
                
                # Push to Cloudinary
                upload_result = cloudinary.uploader.upload(
                    file,
                    folder=folder_path
                )
                
                # Save the secure URL back to our database
                new_image = PropertyImage(
                    property_id=new_property.id,
                    image_url=upload_result.get('secure_url'),
                    public_id=upload_result.get('public_id')
                )
                db.session.add(new_image)
        
        db.session.commit()
        flash("Property listed successfully! Awaiting Admin verification.", "success")
        return redirect(url_for('broker.my_properties'))
        
    return render_template('broker_add_property.html', broker=broker)

@broker_bp.route('/properties/<property_id>/edit', methods=['GET', 'POST'])
@broker_login_required
def edit_property(property_id):
    broker = Broker.query.get(session['broker_id'])
    property_obj = Property.query.get_or_404(property_id)
    
    # Security: Ensure they only edit their own property
    if property_obj.broker_id != broker.id:
        flash("Unauthorized access.", "error")
        return redirect(url_for('broker.my_properties'))
        
    if request.method == 'POST':
        # 1. Update all text fields
        property_obj.title = request.form.get('title')
        property_obj.description = request.form.get('description')
        property_obj.price = request.form.get('price')
        property_obj.listing_type = request.form.get('listing_type')
        property_obj.location = request.form.get('location')
        property_obj.upi_number = request.form.get('upi_number')
        
        # 2. THE SECURITY LOCK: Always revert to pending after any edit
        property_obj.verification_status = 'Pending'
        
        # 3. Handle new images if they uploaded any
        images = request.files.getlist('images')
        for file in images:
            if file.filename != '':
                folder_path = f"RREBP/Brokers/{broker.license_number}/Properties/{property_obj.id}"
                upload_result = cloudinary.uploader.upload(file, folder=folder_path)
                
                new_image = PropertyImage(
                    property_id=property_obj.id,
                    image_url=upload_result.get('secure_url'),
                    public_id=upload_result.get('public_id')
                )
                db.session.add(new_image)
                
        db.session.commit()
        flash("Property updated and submitted for Admin re-verification.", "success")
        return redirect(url_for('broker.my_properties'))
        
    return render_template('broker_edit_property.html', broker=broker, property=property_obj)

@broker_bp.route('/properties/image/<image_id>/delete', methods=['POST'])
@broker_login_required
def delete_image(image_id):
    image = PropertyImage.query.get_or_404(image_id)
    property_obj = Property.query.get(image.property_id)
    broker = Broker.query.get(session['broker_id'])
    
    # Security check
    if property_obj.broker_id != broker.id:
        return {"error": "Unauthorized"}, 403
        
    # 1. Delete from Cloudinary
    try:
        cloudinary.uploader.destroy(image.public_id)
    except Exception as e:
        print(f"Cloudinary deletion failed: {e}")
        
    # 2. Delete from Database
    db.session.delete(image)
    db.session.commit()
    
    return redirect(url_for('broker.edit_property', property_id=property_obj.id))

@broker_bp.route('/properties/<property_id>/delete', methods=['POST'])
@broker_login_required
def delete_property(property_id):
    broker = Broker.query.get(session['broker_id'])
    property_obj = Property.query.get_or_404(property_id)
    
    if property_obj.broker_id != broker.id:
        flash("Unauthorized access.", "error")
        return redirect(url_for('broker.my_properties'))
        
    # 1. Delete all images from Cloudinary first
    for image in property_obj.images:
        try:
            cloudinary.uploader.destroy(image.public_id)
        except:
            pass
            
    # 2. Delete the empty folder from Cloudinary
    folder_path = f"RREBP/Brokers/{broker.license_number}/Properties/{property_obj.id}"
    try:
        cloudinary.api.delete_folder(folder_path)
    except Exception as e:
        print(f"Folder deletion failed (might be already empty/missing): {e}")

    # 3. Delete from Database (Cascade will auto-delete the PropertyImage rows)
    db.session.delete(property_obj)
    db.session.commit()
    
    flash("Property and all associated media have been permanently deleted.", "info")
    return redirect(url_for('broker.my_properties'))

@broker_bp.route('/logout')
def logout():
    session.pop('broker_id', None)
    return redirect(url_for('landing.login_portal'))