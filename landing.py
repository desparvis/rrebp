from flask import redirect, url_for, render_template, session, flash, request, Blueprint
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, Organization, AssociationAdmin, SuperAdmin, Broker, Property, Review
import uuid
from datetime import datetime
import random
import cloudinary
import cloudinary.uploader

landing = Blueprint('landing', __name__, template_folder="templates", static_folder="static")

@landing.route('/')
def home():
    return render_template("index.html")

@landing.route('/verify', methods=['GET', 'POST'])
def verify():
    broker = None
    if request.method == 'POST':
        license_number = request.form.get('license_number')

        broker = Broker.query.filter_by(license_number=license_number).first()
        
        if not broker:
            flash("No broker found matching this license number.", "error")
            
    return render_template("verify.html", broker=broker)

# Login route
@landing.route('/login', methods=['GET', 'POST'])
def login_portal():
    # 1. Fetch ALL active orgs (For Association Admins to join)
    all_active_orgs = Organization.query.filter_by(status='Active').all()
    
    # 2. Filter ONLY orgs that have an Active admin (For Brokers to apply to)
    broker_ready_orgs = [
        org for org in all_active_orgs 
        if any(admin.account_status == 'Active' for admin in org.admins)
    ]
    
    if request.method == 'POST':
        role = request.form.get('role')
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Association Admin Login
        if role == 'association':
            admin = AssociationAdmin.query.filter_by(email=email).first()
            
            if admin and check_password_hash(admin.password_hash, password):
                if admin.account_status == 'Active':
                    session['assoc_admin_id'] = admin.id
                    return redirect(url_for('association.dashboard'))
                elif admin.account_status == 'Pending':
                    flash("Your account is still pending Super Admin approval.", "warning")
                else:
                    flash("Your account access has been revoked.", "error")
            else:
                flash("Invalid email or password.", "error")
        
        # Broker Login
        elif role == 'broker':
            broker = Broker.query.filter_by(email=email).first()
            
            if broker and check_password_hash(broker.password_hash, password):
                if broker.status in ['Active', 'Pending Approval', 'Pending Registration']:
                    session['broker_id'] = broker.id
                    flash(f"Welcome back, {broker.full_name}!", "success")
                    
                    return redirect(url_for('broker.dashboard')) 
                elif broker.status == 'Suspended':
                    flash("Your account has been suspended.", "error")
            else:
                flash("Invalid email or password.", "error")
        
        return redirect(url_for('landing.login_portal'))
        
    return render_template("auth_portal.html", all_active_orgs=all_active_orgs, broker_ready_orgs=broker_ready_orgs)

# Application route
@landing.route('/apply', methods=['POST'])
def apply():
    role = request.form.get('role')
    full_name = request.form.get('full_name')
    email = request.form.get('email')
    password = request.form.get('password')
    
    # Securely hash the password
    hashed_password = generate_password_hash(password)

    # ==========================================
    # BROKER APPLICATION
    # ==========================================
    if role == 'broker':
        phone = request.form.get('phone')
        organization_id = request.form.get('organization_id')
        professional_title = request.form.get('professional_title')
        bio = request.form.get('bio')
        
        # Capture Working Location Fields
        working_province = request.form.get('working_province')
        working_district = request.form.get('working_district')
        
        # --- ADDED: Cloudinary Profile Picture Upload ---
        profile_photo_url = None
        if 'profile_picture' in request.files:
            file = request.files['profile_picture']
            if file and file.filename != '':
                try:
                    upload_result = cloudinary.uploader.upload(
                        file,
                        folder="rrebp_broker_profiles"
                    )
                    profile_photo_url = upload_result.get('secure_url')
                except Exception as e:
                    print(f"Cloudinary upload failed: {str(e)}")
        # ------------------------------------------------

        # Security Check 1: Hard-block if the organization doesn't have an active admin
        active_admin_exists = AssociationAdmin.query.filter_by(
            organization_id=organization_id, 
            account_status='Active'
        ).first()
        
        if not active_admin_exists:
            flash("Registration paused: This organization does not have an active administrator to review applications yet.", "error")
            return redirect(url_for('landing.login_portal'))

        # Security Check 2: Prevent duplicate emails
        if Broker.query.filter_by(email=email).first():
            flash("An application with this email already exists.", "error")
            return redirect(url_for('landing.login_portal'))

        current_year = datetime.now().year
        while True:
            random_digits = ''.join([str(random.randint(0, 9)) for _ in range(10)])
            generated_license = f"RWA-{current_year}-{random_digits}"
            
            # Check database to check uniqueness
            if not Broker.query.filter_by(license_number=generated_license).first():
                break

        # Create Broker
        new_broker = Broker(
            full_name=full_name,
            email=email,
            password_hash=hashed_password, 
            phone=phone,
            license_number=generated_license, 
            organization_id=organization_id,
            professional_title=professional_title,
            working_province=working_province, # SAVED TO DB
            working_district=working_district, # SAVED TO DB
            profile_photo_url=profile_photo_url, # NEW: SAVED FROM CLOUDINARY
            bio=bio,
            status='Pending Approval',
            registered_by=None
        )
        db.session.add(new_broker)
        db.session.commit()
        
        flash(f"Application submitted successfully! Your license number will be {generated_license}", "success")

    # ==========================================
    # ASSOCIATION ADMIN APPLICATION
    # ==========================================
    elif role == 'association':
        organization_id = request.form.get('organization_id')
        
        if AssociationAdmin.query.filter_by(email=email).first():
            flash("An admin with this email already exists.", "error")
            return redirect(url_for('landing.login_portal'))

        super_admin = SuperAdmin.query.first()

        new_admin = AssociationAdmin(
            full_name=full_name,
            email=email,
            password_hash=hashed_password,
            organization_id=organization_id,
            account_status='Pending', 
            created_by=super_admin.id if super_admin else 'system'
        )
        db.session.add(new_admin)
        db.session.commit()
        
        flash("Association application submitted! Awaiting Super Admin review.", "success")

    return redirect(url_for('landing.login_portal'))

@landing.route('/properties') 
def public_properties():
    # Only fetch properties that have been officially Verified
    query = Property.query.filter_by(verification_status='Verified')

    # Get the current page number from the URL (default to 1)
    page = request.args.get('page', 1, type=int)

    # Get location parameters
    province = request.args.get('province')
    district = request.args.get('district')
    sector = request.args.get('sector')
    cell = request.args.get('cell')
    village = request.args.get('village')
    
    # Get property details parameters
    listing_type = request.args.get('listing_type')
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    bedrooms = request.args.get('bedrooms', type=int)
    bathrooms = request.args.get('bathrooms', type=int)

    # Apply location filters
    if province:
        query = query.filter_by(province=province)
    if district:
        query = query.filter_by(district=district)
    if sector:
        query = query.filter_by(sector=sector)
    if cell:
        query = query.filter_by(cell=cell)
    if village:
        query = query.filter_by(village=village)
        
    # Apply property details filters
    if listing_type:
        query = query.filter_by(listing_type=listing_type)
    if min_price is not None:
        query = query.filter(Property.price >= min_price)
    if max_price is not None:
        query = query.filter(Property.price <= max_price)
    if bedrooms is not None:
        query = query.filter(Property.bedrooms >= bedrooms)
    if bathrooms is not None:
        query = query.filter(Property.bathrooms >= bathrooms)

    pagination = query.order_by(Property.created_at.desc()).paginate(page=page, per_page=12, error_out=False)
    
    properties = pagination.items
    
    return render_template('public_properties.html', properties=properties, pagination=pagination)

@landing.route('/properties/<property_id>') 
def public_property_detail(property_id):
    property_obj = Property.query.filter_by(id=property_id, verification_status='Verified').first_or_404()
    
    org = Organization.query.get(property_obj.broker.organization_id)
    org_name = org.name if org else "Independent"
    
    return render_template(
        'public_property_detail.html', 
        property=property_obj,
        org_name=org_name
    )

@landing.route('/leave-review', methods=['GET', 'POST'])
def leave_review():
    prefilled_code = request.args.get('code', '')

    if request.method == 'POST':
        review_code = request.form.get('review_code').strip().upper()
        client_name = request.form.get('client_name')
        rating = request.form.get('rating', type=int)
        comment = request.form.get('comment')
        
        broker = Broker.query.filter_by(review_code=review_code).first()
        
        if not broker:
            flash("Invalid Review Code. Please check the code and try again.", "error")
            return redirect(url_for('landing.leave_review'))
            
        new_review = Review(
            broker_id=broker.id,
            client_name=client_name,
            rating=rating,
            comment=comment,
            is_approved=False 
        )
        db.session.add(new_review)
        db.session.commit()
        
        flash(f"Thank you! Your review for {broker.full_name} has been submitted for moderation.", "success")
        return redirect(url_for('landing.leave_review'))
        
    return render_template('public_leave_review.html', prefilled_code=prefilled_code)

@landing.route('/broker-rankings')
def broker_rankings():
    brokers = Broker.query.filter_by(status='Active').all()
    
    broker_stats = []
    for broker in brokers:
        org = Organization.query.get(broker.organization_id)
        org_name = org.name if org else "Independent"
        
        approved_reviews = Review.query.filter_by(broker_id=broker.id, is_approved=True).all()
        
        avg_rating = 0
        if approved_reviews:
            avg_rating = round(sum(r.rating for r in approved_reviews) / len(approved_reviews), 1)
        
        broker_stats.append({
            'broker': broker,
            'org_name': org_name,
            'avg_rating': avg_rating,
            'review_count': len(approved_reviews)
        })
        
    broker_stats.sort(key=lambda x: (x['avg_rating'], x['review_count']), reverse=True)
    
    return render_template('public_broker_rankings.html', broker_stats=broker_stats)

@landing.route('/broker/<broker_id>')
def public_broker_profile(broker_id):
    broker = Broker.query.filter_by(id=broker_id, status='Active').first_or_404()
    
    org = Organization.query.get(broker.organization_id)
    org_name = org.name if org else "Independent"
    
    properties = Property.query.filter_by(
        broker_id=broker.id, 
        verification_status='Verified'
    ).order_by(Property.created_at.desc()).all()
    
    reviews = Review.query.filter_by(
        broker_id=broker.id, 
        is_approved=True
    ).order_by(Review.created_at.desc()).all()
    
    avg_rating = 0
    if reviews:
        avg_rating = round(sum(r.rating for r in reviews) / len(reviews), 1)
        
    return render_template(
        'public_broker_profile.html', 
        broker=broker, 
        org_name=org_name, 
        properties=properties, 
        reviews=reviews, 
        avg_rating=avg_rating
    )