from flask import Blueprint, render_template, session, redirect, url_for, flash, request
from functools import wraps
from models import db, Broker, Organization, Property, Review, PropertyImage
import random
import string
import cloudinary.uploader
import cloudinary.api

broker_bp = Blueprint('broker', __name__, template_folder="templates", static_folder="static")

def broker_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'broker_id' not in session:
            flash("Please log in to access the Broker Portal.", "warning")
            return redirect(url_for('landing.login_portal'))
            
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
    
    if not broker.review_code:
        while True:
            random_chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            new_code = f"REV-{random_chars}"
            if not Broker.query.filter_by(review_code=new_code).first():
                broker.review_code = new_code
                db.session.commit()
                break

    organization = Organization.query.get(broker.organization_id)
    active_properties = Property.query.filter_by(broker_id=broker.id, is_available=True).count()
    pending_reviews = Review.query.filter_by(broker_id=broker.id, is_approved=False).count()
    
    return render_template(
        'broker_dashboard.html', 
        broker=broker, 
        organization=organization,
        active_properties=active_properties,
        pending_reviews=pending_reviews
    )

@broker_bp.route('/my-properties')
@broker_login_required
def my_properties():
    broker = Broker.query.get(session['broker_id'])
    
    query = Property.query.filter_by(broker_id=broker.id)

    province = request.args.get('province')
    district = request.args.get('district')
    sector = request.args.get('sector')
    cell = request.args.get('cell')
    village = request.args.get('village')
    listing_type = request.args.get('listing_type')
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    bedrooms = request.args.get('bedrooms', type=int)
    bathrooms = request.args.get('bathrooms', type=int)

    if province: query = query.filter_by(province=province)
    if district: query = query.filter_by(district=district)
    if sector: query = query.filter_by(sector=sector)
    if cell: query = query.filter_by(cell=cell)
    if village: query = query.filter_by(village=village)
    if listing_type: query = query.filter_by(listing_type=listing_type)
    if min_price is not None: query = query.filter(Property.price >= min_price)
    if max_price is not None: query = query.filter(Property.price <= max_price)
    if bedrooms is not None: query = query.filter(Property.bedrooms >= bedrooms)
    if bathrooms is not None: query = query.filter(Property.bathrooms >= bathrooms)

    properties = query.order_by(Property.created_at.desc()).all()
    
    return render_template('broker_properties.html', broker=broker, properties=properties)

@broker_bp.route('/my-properties/add', methods=['GET', 'POST'])
@broker_login_required
def add_property():
    broker = Broker.query.get(session['broker_id'])
    
    if request.method == 'POST':
        new_property = Property(
            broker_id=broker.id,
            title=request.form.get('title'),
            description=request.form.get('description'),
            price=request.form.get('price'),
            listing_type=request.form.get('listing_type'),
            province=request.form.get('province'),
            district=request.form.get('district'),
            sector=request.form.get('sector'),
            cell=request.form.get('cell'),
            village=request.form.get('village'),
            bedrooms=request.form.get('bedrooms', type=int),
            bathrooms=request.form.get('bathrooms', type=int),
            upi_number=request.form.get('upi_number'),
            verification_status='Pending'
        )
        db.session.add(new_property)
        db.session.flush() 
        
        images = request.files.getlist('images')
        for file in images:
            if file.filename != '':
                folder_path = f"RREBP/Brokers/{broker.license_number}/Properties/{new_property.id}"
                upload_result = cloudinary.uploader.upload(file, folder=folder_path)
                
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

@broker_bp.route('/my-properties/<property_id>/edit', methods=['GET', 'POST'])
@broker_login_required
def edit_property(property_id):
    broker = Broker.query.get(session['broker_id'])
    property_obj = Property.query.get_or_404(property_id)
    
    if property_obj.broker_id != broker.id:
        flash("Unauthorized access.", "error")
        return redirect(url_for('broker.my_properties'))
        
    if request.method == 'POST':
        property_obj.title = request.form.get('title')
        property_obj.description = request.form.get('description')
        property_obj.price = request.form.get('price')
        property_obj.listing_type = request.form.get('listing_type')
        property_obj.province = request.form.get('province')
        property_obj.district = request.form.get('district')
        property_obj.sector = request.form.get('sector')
        property_obj.cell = request.form.get('cell')
        property_obj.village = request.form.get('village')
        property_obj.bedrooms = request.form.get('bedrooms', type=int)
        property_obj.bathrooms = request.form.get('bathrooms', type=int)
        property_obj.upi_number = request.form.get('upi_number')
        property_obj.verification_status = 'Pending'
        
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

@broker_bp.route('/my-properties/image/<image_id>/delete', methods=['POST'])
@broker_login_required
def delete_image(image_id):
    image = PropertyImage.query.get_or_404(image_id)
    property_obj = Property.query.get(image.property_id)
    broker = Broker.query.get(session['broker_id'])
    
    if property_obj.broker_id != broker.id:
        return {"error": "Unauthorized"}, 403
        
    try:
        cloudinary.uploader.destroy(image.public_id)
    except Exception as e:
        print(f"Cloudinary deletion failed: {e}")
        
    db.session.delete(image)
    db.session.commit()
    
    return redirect(url_for('broker.edit_property', property_id=property_obj.id))

@broker_bp.route('/my-properties/<property_id>/delete', methods=['POST'])
@broker_login_required
def delete_property(property_id):
    broker = Broker.query.get(session['broker_id'])
    property_obj = Property.query.get_or_404(property_id)
    
    if property_obj.broker_id != broker.id:
        flash("Unauthorized access.", "error")
        return redirect(url_for('broker.my_properties'))
        
    for image in property_obj.images:
        try:
            cloudinary.uploader.destroy(image.public_id)
        except:
            pass
            
    folder_path = f"RREBP/Brokers/{broker.license_number}/Properties/{property_obj.id}"
    try:
        cloudinary.api.delete_folder(folder_path)
    except Exception as e:
        print(f"Folder deletion failed: {e}")

    db.session.delete(property_obj)
    db.session.commit()
    
    flash("Property and all associated media have been permanently deleted.", "info")
    return redirect(url_for('broker.my_properties'))

@broker_bp.route('/logout')
def logout():
    session.pop('broker_id', None)
    return redirect(url_for('landing.login_portal'))

@broker_bp.route('/my-reviews')
@broker_login_required
def my_reviews():
    broker = Broker.query.get(session['broker_id'])
    
    # Fetch all reviews for this broker, newest first
    reviews = Review.query.filter_by(broker_id=broker.id).order_by(Review.created_at.desc()).all()
    
    # Calculate average rating from approved reviews only
    approved_reviews = [r for r in reviews if r.is_approved]
    avg_rating = 0
    if approved_reviews:
        avg_rating = round(sum(r.rating for r in approved_reviews) / len(approved_reviews), 1)
        
    return render_template('broker_reviews.html', broker=broker, reviews=reviews, avg_rating=avg_rating)