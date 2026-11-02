from flask import redirect, url_for, render_template, session, flash, request, Blueprint
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, Organization, AssociationAdmin, SuperAdmin, Broker, Property, Review, AuditLog
import uuid
from datetime import datetime
import random
import cloudinary
import cloudinary.uploader
import string
from flask import current_app
from flask_mail import Message
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from models import mail

landing = Blueprint('landing', __name__, template_folder="templates", static_folder="static")

def generate_new_review_code():
    """Generates a secure 8-character uppercase code and ensures it is unique"""
    while True:
        random_chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        new_code = f"RWA-{random_chars}"
        
        # Ensure no other broker has this exact code right now
        if not Broker.query.filter_by(review_code=new_code).first():
            return new_code

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
        
        # Look up the broker by the submitted code
        broker = Broker.query.filter_by(review_code=review_code).first()
        
        if not broker:
            flash("Invalid Review Code. It may have already been used or entered incorrectly.", "error")
            return redirect(url_for('landing.leave_review'))
            
        # Save the new review
        new_review = Review(
            broker_id=broker.id,
            client_name=client_name,
            rating=rating,
            comment=comment,
            is_approved=False 
        )
        db.session.add(new_review)
        
        # Rotate the broker's code instantly
        old_code = broker.review_code
        new_code = generate_new_review_code()
        broker.review_code = new_code
        
        # Optional: Log the code rotation for security tracking
        log = AuditLog(
            action="ROTATE_REVIEW_CODE",
            actor_type="System",
            actor_id="Auto",
            target_type="Broker",
            target_id=broker.id,
            description=f"Review code rotated after successful submission by {client_name}"
        )
        db.session.add(log)
        
        db.session.commit()
        
        flash(f"Thank you! Your review for {broker.full_name} has been submitted for moderation.", "success")
        return redirect(url_for('landing.leave_review'))
        
    return render_template('public_leave_review.html', prefilled_code=prefilled_code)

@landing.route('/broker-rankings')
def broker_rankings():
    # 1. Get current page (default to 1) and set limit per page
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
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
        
    # Sort brokers by highest rating first, then by most reviews
    broker_stats.sort(key=lambda x: (x['avg_rating'], x['review_count']), reverse=True)
    
    # 2. Perform List Slicing Pagination
    total_brokers = len(broker_stats)
    total_pages = (total_brokers + per_page - 1) // per_page
    
    # Failsafe if user types a crazy page number in URL
    if page < 1:
        page = 1
    elif page > total_pages and total_pages > 0:
        page = total_pages
        
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    
    # Slice the exact 10 brokers for the current page
    paginated_stats = broker_stats[start_idx:end_idx]
    
    # Calculate button states
    has_prev = page > 1
    has_next = page < total_pages
    
    return render_template(
        'public_broker_rankings.html', 
        broker_stats=paginated_stats,
        page=page,
        total_pages=total_pages,
        has_prev=has_prev,
        has_next=has_next
    )

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

# Password Reset functions

def get_reset_serializer():
    """Generates a secure token serializer using the app's secret key"""
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])

@landing.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        role = request.form.get('role')
        
        # Find the user based on their role
        user = None
        if role == 'broker':
            user = Broker.query.filter_by(email=email).first()
        elif role == 'association':
            user = AssociationAdmin.query.filter_by(email=email).first()
            
        #If user exists, generate token and send email
        if user:
            s = get_reset_serializer()
            # We bundle their email and role into the encrypted token
            token = s.dumps({'email': user.email, 'role': role}, salt='password-reset-salt')
            
            reset_url = url_for('landing.reset_password', token=token, _external=True)
            
            # Craft the email
            msg = Message("Reset Your RREBP Password", recipients=[user.email])
            msg.body = f"""Hello {user.full_name},

You requested a password reset for your RREBP account.
Click the link below to set a new password. This link will expire in 1 hour.

{reset_url}

If you did not request this, you can safely ignore this email.
"""
            try:
                mail.send(msg)
            except Exception as e:
                print(f"Mail error: {e}")
                flash("Error sending email. Please contact support.", "error")
                return redirect(url_for('landing.forgot_password'))
                
        # Security best practice: Always say the same thing whether the email exists or not
        # so hackers can't use this form to guess which emails are registered.
        flash("If an account exists with that email, a password reset link has been sent.", "info")
        return redirect(url_for('landing.login_portal'))
        
    return render_template('public_forgot_password.html')

@landing.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    s = get_reset_serializer()
    
    try:
        # 1. Decrypt token (max_age=3600 seconds = 1 hour)
        data = s.loads(token, salt='password-reset-salt', max_age=3600)
        email = data.get('email')
        role = data.get('role')
    except SignatureExpired:
        flash("The password reset link has expired. Please request a new one.", "error")
        return redirect(url_for('landing.forgot_password'))
    except BadSignature:
        flash("Invalid password reset link.", "error")
        return redirect(url_for('landing.forgot_password'))
        
    if request.method == 'POST':
        new_password = request.form.get('password')
        hashed_password = generate_password_hash(new_password)
        
        # 2. Update the correct database table
        user = None
        if role == 'broker':
            user = Broker.query.filter_by(email=email).first()
        elif role == 'association':
            user = AssociationAdmin.query.filter_by(email=email).first()
            
        if user:
            user.password_hash = hashed_password
            db.session.commit()
            flash("Your password has been successfully reset! You can now log in.", "success")
            return redirect(url_for('landing.login_portal'))
            
    return render_template('public_reset_password.html', token=token)