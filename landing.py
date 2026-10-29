from flask import redirect, url_for, render_template, session, flash, request, Blueprint
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, Organization, AssociationAdmin, SuperAdmin, Broker
import uuid 

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
                    return redirect(url_for('association.dashboard')) # Update this with your actual blueprint route
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
                    # return redirect(url_for('broker.dashboard')) # Uncomment when you build the broker dashboard!
                    return redirect(url_for('landing.login_portal')) 
                elif broker.status == 'Suspended':
                    flash("Your account has been suspended.", "error")
            else:
                flash("Invalid email or password.", "error")
        
        return redirect(url_for('landing.login_portal'))
        
    # Pass BOTH lists to the template
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

    # Broker Application
    if role == 'broker':
        phone = request.form.get('phone')
        license_number = request.form.get('license_number')
        organization_id = request.form.get('organization_id')
        professional_title = request.form.get('professional_title')
        bio = request.form.get('bio')
        
        # THE FIX: Hard-block if the organization doesn't have an active admin
        active_admin_exists = AssociationAdmin.query.filter_by(
            organization_id=organization_id, 
            account_status='Active'
        ).first()
        
        if not active_admin_exists:
            flash("Registration paused: This organization does not have an active administrator to review applications yet.", "error")
            return redirect(url_for('landing.login_portal'))

        if Broker.query.filter_by(email=email).first() or Broker.query.filter_by(license_number=license_number).first():
            flash("An application with this email or license number already exists.", "error")
            return redirect(url_for('landing.login_portal'))

        new_broker = Broker(
            full_name=full_name,
            email=email,
            password_hash=hashed_password, 
            phone=phone,
            license_number=license_number,
            organization_id=organization_id,
            professional_title=professional_title,
            bio=bio,
            status='Pending Approval',
            registered_by='self'
        )
        db.session.add(new_broker)
        db.session.commit()
        
        flash("Broker application submitted successfully! Your organization admin will review it shortly.", "success")

    # Association Admin Application
    elif role == 'association':
        # THE FIX: Grab the organization_id directly from the dropdown
        organization_id = request.form.get('organization_id')
        
        if AssociationAdmin.query.filter_by(email=email).first():
            flash("An admin with this email already exists.", "error")
            return redirect(url_for('landing.login_portal'))

        super_admin = SuperAdmin.query.first()

        # Just create the admin and link them to the chosen organization ID
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