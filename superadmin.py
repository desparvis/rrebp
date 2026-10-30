from flask import Blueprint, redirect, url_for, render_template, session, flash, request
from werkzeug.security import check_password_hash
from functools import wraps
from models import db, SuperAdmin, Organization, AssociationAdmin
from datetime import datetime, timezone
import random  # Added for auto-generation

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
    if 'superadmin_id' in session:
        return redirect(url_for('superadmin.spdash'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        admin = SuperAdmin.query.filter_by(email=email).first()
        
        if admin and check_password_hash(admin.password_hash, password):
            session['superadmin_id'] = admin.id
            return redirect(url_for('superadmin.spdash'))
        else:
            flash("Invalid email or password.", "error")
            
    return render_template("sp_login.html")

@superadmin.route('/spdash/logout')
def logout():
    session.pop('superadmin_id', None)
    return redirect(url_for('superadmin.login'))

@superadmin.route('/spdash')
@login_required
def spdash():
    active_orgs = Organization.query.filter_by(status='Active').count()
    total_admins = AssociationAdmin.query.count()
    suspended_orgs = Organization.query.filter_by(status='Suspended').count()
    
    return render_template("sp_dashboard.html", 
                           active_orgs=active_orgs, 
                           total_admins=total_admins, 
                           suspended_orgs=suspended_orgs)

@superadmin.route('/spdash/organizations')
@login_required
def organizations():
    orgs = Organization.query.order_by(Organization.created_at.desc()).all()
    return render_template("sp_organizations.html", organizations=orgs)

@superadmin.route('/spdash/organizations/new', methods=['GET', 'POST'])
@login_required
def new_organization():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        address = request.form.get('address')
        
        # --- THE FIX: Auto-Generate Registration Number ---
        # Get first 3 letters, uppercase. If name is shorter than 3, just use what exists.
        name_prefix = name[:3].upper() if name else "ORG"
        
        while True:
            # Generate 6 random digits
            random_digits = ''.join([str(random.randint(0, 9)) for _ in range(6)])
            generated_reg_num = f"RREBP-{random_digits}-{name_prefix}"
            
            # Ensure 100% uniqueness in the database
            if not Organization.query.filter_by(registration_number=generated_reg_num).first():
                break

        new_org = Organization(
            name=name,
            registration_number=generated_reg_num, # Injected securely here
            email=email,
            phone=phone,
            address=address,
            created_by=session['superadmin_id']
        )
        db.session.add(new_org)
        db.session.commit()
        flash(f"Organization registered! Official ID: {generated_reg_num}", "success")
        return redirect(url_for('superadmin.organizations'))
        
    return render_template("sp_org_form.html", org=None)

@superadmin.route('/spdash/organizations/<org_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_organization(org_id):
    org = Organization.query.get_or_404(org_id)
    
    if request.method == 'POST':
        org.name = request.form.get('name')
        # We DO NOT update org.registration_number here. It is permanently locked.
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