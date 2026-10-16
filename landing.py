from flask import Flask, redirect, url_for, render_template, session, flash, request, Blueprint
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, Organization, AssociationAdmin, SuperAdmin, Broker

landing = Blueprint('landing', __name__, template_folder="templates", static_folder="static")

@landing.route('/')
def home():
    return render_template("index.html")

@landing.route('/verify', methods=['GET', 'POST'])
def verify():
    broker = None
    if request.method == 'POST':
        license_number = request.form.get('license_number')
        # Search the database for the broker
        broker = Broker.query.filter_by(license_number=license_number).first()
        
        if not broker:
            flash("No broker found matching this license number.", "error")
            
    return render_template("verify.html", broker=broker)

# Authentication function for the login button
@landing.route('/login', methods=['GET', 'POST'])
def login_portal():
    # Fetch active organizations for the registration dropdown
    organizations = Organization.query.filter_by(status='Active').all()
    
    if request.method == 'POST':
        form_type = request.form.get('form_type')
        role = request.form.get('role')
        
        # --- THE REAL LOGIN LOGIC ---
        if form_type == 'login':
            email = request.form.get('email')
            password = request.form.get('password')
            
            if role == 'association':
                admin = AssociationAdmin.query.filter_by(email=email).first()
                
                # Check if they exist and password matches
                if admin and check_password_hash(admin.password_hash, password):
                    # Check if Super Admin actually approved them
                    if admin.account_status == 'Active':
                        session['assoc_admin_id'] = admin.id
                        return redirect(url_for('association.dashboard'))
                    elif admin.account_status == 'Pending':
                        flash("Your account is still pending Super Admin approval.", "info")
                    else:
                        flash("Your account access has been revoked.", "error")
                else:
                    flash("Invalid email or password.", "error")
            
            elif role == 'broker':
                flash("Broker login coming next!", "info")
                
        # --- THE REGISTRATION LOGIC (keep your existing code here) ---
        elif form_type == 'register':
            # ... (your existing admin registration code stays exactly the same) ...
            pass # (I put pass here just to keep the snippet short, keep your real code!)
            
        return redirect(url_for('landing.login_portal'))
        
    return render_template("auth_portal.html", organizations=organizations)

@landing.route('/register-admin', methods=['GET', 'POST'])
def register_admin():
    # Fetch only active organizations so admins can select them
    organizations = Organization.query.filter_by(status='Active').all()
    
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        org_id = request.form.get('organization_id')
        
        # Failsafe: assign to the first super admin to satisfy the database foreign key
        super_admin = SuperAdmin.query.first() 
        
        new_admin = AssociationAdmin(
            full_name=name,
            email=email,
            password_hash=generate_password_hash(password),
            organization_id=org_id,
            account_status='Pending', # Super Admin must approve them!
            created_by=super_admin.id
        )
        db.session.add(new_admin)
        db.session.commit()
        
        flash("Admin application submitted successfully. Awaiting Super Admin approval.", "success")
        return redirect(url_for('landing.home'))
        
    return render_template("register_admin.html", organizations=organizations)