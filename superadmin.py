from flask import Blueprint, redirect, url_for, render_template, session, flash, request
from werkzeug.security import check_password_hash
from functools import wraps
from models import db, SuperAdmin, Organization, AssociationAdmin
from datetime import datetime, timezone

# Setting the superadmin blueprint
superadmin = Blueprint('superadmin', __name__, template_folder="templates", static_folder="static")

# Decorator to protect routes with session
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'superadmin_id' not in session:
            return redirect(url_for('superadmin.login'))
        return f(*args, **kwargs)
    return decorated_function

@superadmin.route('/spdash/login', methods=['GET', 'POST'])
def login():
    # Bypass login if the session already exists
    if 'superadmin_id' in session:
        return redirect(url_for('superadmin.spdash'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Query the database for the admin
        admin = SuperAdmin.query.filter_by(email=email).first()
        
        # Validate credentials
        if admin and check_password_hash(admin.password_hash, password):
            session['superadmin_id'] = admin.id
            return redirect(url_for('superadmin.spdash'))
        else:
            flash("Invalid email or password.", "error")
            
    return render_template("sp_login.html")

@superadmin.route('/spdash/logout')
def logout():
    # Destroy the session
    session.pop('superadmin_id', None)
    return redirect(url_for('superadmin.login'))

@superadmin.route('/spdash')
@login_required
def spdash():
    # 1. Count active organizations
    active_orgs = Organization.query.filter_by(status='Active').count()
    
    # 2. Count all registered association admins
    total_admins = AssociationAdmin.query.count()
    
    # 3. Count suspended organizations
    suspended_orgs = Organization.query.filter_by(status='Suspended').count()
    
    # Pass the variables to the template
    return render_template("sp_dashboard.html", 
                           active_orgs=active_orgs, 
                           total_admins=total_admins, 
                           suspended_orgs=suspended_orgs)

@superadmin.route('/spdash/organizations')
@login_required
def organizations():
    # Fetch all organizations from the database
    orgs = Organization.query.order_by(Organization.created_at.desc()).all()
    return render_template("sp_organizations.html", organizations=orgs)

@superadmin.route('/spdash/organizations/new', methods=['GET', 'POST'])
@login_required
def new_organization():
    if request.method == 'POST':
        name = request.form.get('name')
        reg_number = request.form.get('registration_number')
        email = request.form.get('email')
        phone = request.form.get('phone')
        address = request.form.get('address')
        
        # Create new organization linked to the logged-in super admin
        new_org = Organization(
            name=name,
            registration_number=reg_number,
            email=email,
            phone=phone,
            address=address,
            created_by=session['superadmin_id']
        )
        db.session.add(new_org)
        db.session.commit()
        flash("Organization registered successfully.", "success")
        return redirect(url_for('superadmin.organizations'))
        
    return render_template("sp_org_form.html", org=None)

@superadmin.route('/spdash/organizations/<org_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_organization(org_id):
    org = Organization.query.get_or_404(org_id)
    
    if request.method == 'POST':
        org.name = request.form.get('name')
        org.registration_number = request.form.get('registration_number')
        org.email = request.form.get('email')
        org.phone = request.form.get('phone')
        org.address = request.form.get('address')
        org.status = request.form.get('status')
        
        db.session.commit()
        flash("Organization updated successfully.", "success")
        return redirect(url_for('superadmin.organizations'))
        
    return render_template("sp_org_form.html", org=org)

@superadmin.route('/spdash/organizations/<org_id>/delete', methods=['POST'])
@login_required
def delete_organization(org_id):
    org = Organization.query.get_or_404(org_id)
    db.session.delete(org)
    db.session.commit()
    flash("Organization deleted.", "info")
    return redirect(url_for('superadmin.organizations'))

@superadmin.route('/spdash/admins')
@login_required
def manage_admins():
    # Fetch all admins and their linked organizations
    admins = AssociationAdmin.query.order_by(AssociationAdmin.created_at.desc()).all()
    return render_template("sp_admins.html", admins=admins)

@superadmin.route('/spdash/admins/<admin_id>/approve', methods=['POST'])
@login_required
def approve_admin(admin_id):
    admin = AssociationAdmin.query.get_or_404(admin_id)
    admin.account_status = 'Active'
    admin.approved_at = datetime.now(timezone.utc)
    db.session.commit()
    flash(f"Admin {admin.full_name} approved.", "success")
    return redirect(url_for('superadmin.manage_admins'))

@superadmin.route('/spdash/admins/<admin_id>/revoke', methods=['POST'])
@login_required
def revoke_admin(admin_id):
    admin = AssociationAdmin.query.get_or_404(admin_id)
    admin.account_status = 'Revoked'
    db.session.commit()
    flash(f"Admin {admin.full_name}'s access has been revoked.", "error")
    return redirect(url_for('superadmin.manage_admins'))

0xa52ECb8501f91E0cfa36608B45dBcD092C6222F6