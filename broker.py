from flask import Blueprint, render_template, session, redirect, url_for, flash, request
from functools import wraps
from models import db, Broker, Organization, Property, Review, PropertyImage, AuditLog
import random
import string
import cloudinary.uploader
import cloudinary.api
from werkzeug.security import generate_password_hash, check_password_hash

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

@broker_bp.route('/brokerdash/settings', methods=['GET', 'POST'])
def settings():
    if 'broker_id' not in session:
        return redirect(url_for('landing.login_portal'))
        
    broker_id = session['broker_id']
    broker = Broker.query.get_or_404(broker_id)

    if request.method == 'POST':
        action = request.form.get('action')

        # ==========================================
        # 1. PROFILE UPDATE & RE-VERIFICATION
        # ==========================================
        if action == 'update_profile':
            broker.phone = request.form.get('phone')
            broker.professional_title = request.form.get('professional_title')
            broker.bio = request.form.get('bio')
            
            # Handle Cloudinary Profile Picture Upload
            if 'profile_picture' in request.files:
                file = request.files['profile_picture']
                if file and file.filename != '':
                    try:
                        upload_result = cloudinary.uploader.upload(
                            file,
                            folder="rrebp_broker_profiles"
                        )
                        broker.profile_photo_url = upload_result.get('secure_url')
                    except Exception as e:
                        print(f"Cloudinary upload failed: {str(e)}")
                        flash("Profile picture upload failed, but other details were saved.", "warning")

            # THE FLIP: Send them back to the Admin's review queue
            broker.status = 'Pending Approval'
            
            # Log the security event
            log = AuditLog(
                actor_type="Broker",
                actor_id=broker.id,
                action="UPDATE_PROFILE",
                target_type="Broker",
                target_id=broker.id,
                description="Broker updated profile details, triggering re-verification workflow."
            )
            db.session.add(log)
            db.session.commit()
            
            flash("Profile updated! Your account is now paused pending Admin re-verification.", "info")
            # Redirect to dashboard since they are now pending and shouldn't be editing active settings
            return redirect(url_for('broker.dashboard'))

        # ==========================================
        # 2. SECURE PASSWORD CHANGE
        # ==========================================
        elif action == 'update_password':
            current_password = request.form.get('current_password')
            new_password = request.form.get('new_password')

            if not check_password_hash(broker.password_hash, current_password):
                flash("Incorrect current password. Security check failed.", "error")
            elif len(new_password) < 8:
                flash("New password must be at least 8 characters long.", "error")
            else:
                broker.password_hash = generate_password_hash(new_password)
                
                log = AuditLog(
                    actor_type="Broker",
                    actor_id=broker.id,
                    action="CHANGE_PASSWORD",
                    target_type="Broker",
                    target_id=broker.id,
                    description="Broker updated their password securely via settings."
                )
                db.session.add(log)
                db.session.commit()
                
                flash("Password updated successfully.", "success")
                
            return redirect(url_for('broker.settings'))

        # ==========================================
        # 3. NUKE ACCOUNT
        # ==========================================
        elif action == 'delete_account':
            db.session.delete(broker)
            
            log = AuditLog(
                actor_type="Broker",
                actor_id=broker_id,
                action="DELETE_ACCOUNT",
                target_type="Broker",
                target_id=broker_id,
                description="Broker permanently deleted their own account."
            )
            db.session.add(log)
            db.session.commit()
            
            session.pop('broker_id', None)
            flash("Your account has been permanently deleted.", "info")
            return redirect(url_for('landing.home'))

    return render_template("broker_settings.html", broker=broker)

@broker_bp.route('/my-properties/<property_id>/view')
@broker_login_required
def view_property(property_id):
    broker = Broker.query.get(session['broker_id'])
    property_obj = Property.query.get_or_404(property_id)
    
    # Security check: ensure brokers can only view their own properties through this portal route
    if property_obj.broker_id != broker.id:
        flash("Unauthorized access to this property.", "error")
        return redirect(url_for('broker.my_properties'))
        
    return render_template('broker_view_property.html', broker=broker, property=property_obj)