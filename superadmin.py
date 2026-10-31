from flask import Blueprint, redirect, url_for, render_template, session, flash, request
from werkzeug.security import check_password_hash
from functools import wraps
from models import db, SuperAdmin, Organization, AssociationAdmin, AuditLog
from datetime import datetime, timezone
import random

superadmin = Blueprint('superadmin', __name__, template_folder="templates", static_folder="static")

# ==========================================
# AUDIT LOG HELPER
# ==========================================
def log_audit_action(actor_id, action, target_type, target_id, description):
    """Silently records critical actions to the database."""
    log = AuditLog(
        actor_type='SuperAdmin',
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        description=description
    )
    db.session.add(log)
    db.session.commit()

# ==========================================
# AUTH & CONTEXT
# ==========================================
@superadmin.context_processor
def inject_pending_counts():
    if 'superadmin_id' in session:
        pending_admins_count = AssociationAdmin.query.filter_by(account_status='Pending').count()
        return dict(pending_admins_count=pending_admins_count)
    return dict(pending_admins_count=0)

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
    
    pending_admins = AssociationAdmin.query.filter_by(account_status='Pending').order_by(AssociationAdmin.created_at.desc()).limit(5).all()
    
    # NEW: Fetch the 8 most recent audit logs for the dashboard feed
    recent_logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(8).all()
    
    return render_template("sp_dashboard.html", 
                           active_orgs=active_orgs, 
                           total_admins=total_admins, 
                           suspended_orgs=suspended_orgs,
                           pending_admins=pending_admins,
                           recent_logs=recent_logs)

# ==========================================
# ORGANIZATION MANAGEMENT
# ==========================================
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
        
        name_prefix = name[:3].upper() if name else "ORG"
        
        while True:
            random_digits = ''.join([str(random.randint(0, 9)) for _ in range(6)])
            generated_reg_num = f"RREBP-{random_digits}-{name_prefix}"
            if not Organization.query.filter_by(registration_number=generated_reg_num).first():
                break

        new_org = Organization(
            name=name,
            registration_number=generated_reg_num,
            email=email,
            phone=phone,
            address=address,
            created_by=session['superadmin_id']
        )
        db.session.add(new_org)
        db.session.commit()
        
        # AUDIT LOG
        log_audit_action(session['superadmin_id'], 'CREATE_ORG', 'Organization', new_org.id, f"Registered new organization: {name}")
        
        flash(f"Organization registered! Official ID: {generated_reg_num}", "success")
        return redirect(url_for('superadmin.organizations'))
        
    return render_template("sp_org_form.html", org=None)

@superadmin.route('/spdash/organizations/<org_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_organization(org_id):
    org = Organization.query.get_or_404(org_id)
    
    if request.method == 'POST':
        org.name = request.form.get('name')
        org.email = request.form.get('email')
        org.phone = request.form.get('phone')
        org.address = request.form.get('address')
        old_status = org.status
        org.status = request.form.get('status')
        
        db.session.commit()
        
        # AUDIT LOG
        action_msg = f"Updated organization details: {org.name}"
        if old_status != org.status:
            action_msg += f" (Status changed to {org.status})"
        log_audit_action(session['superadmin_id'], 'UPDATE_ORG', 'Organization', org.id, action_msg)
        
        flash("Organization updated successfully.", "success")
        return redirect(url_for('superadmin.organizations'))
        
    return render_template("sp_org_form.html", org=org)

@superadmin.route('/spdash/organizations/<org_id>/delete', methods=['POST'])
@login_required
def delete_organization(org_id):
    org = Organization.query.get_or_404(org_id)
    org_name = org.name
    
    db.session.delete(org)
    db.session.commit()
    
    # AUDIT LOG
    log_audit_action(session['superadmin_id'], 'DELETE_ORG', 'Organization', org_id, f"Deleted organization: {org_name}")
    
    flash("Organization deleted.", "info")
    return redirect(url_for('superadmin.organizations'))

# ==========================================
# ADMIN MANAGEMENT
# ==========================================
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
    
    # AUDIT LOG
    log_audit_action(session['superadmin_id'], 'APPROVE_ADMIN', 'AssociationAdmin', admin.id, f"Granted database access to {admin.full_name}")
    
    flash(f"Admin {admin.full_name} approved.", "success")
    return redirect(url_for('superadmin.manage_admins'))

@superadmin.route('/spdash/admins/<admin_id>/revoke', methods=['POST'])
@login_required
def revoke_admin(admin_id):
    admin = AssociationAdmin.query.get_or_404(admin_id)
    admin.account_status = 'Revoked'
    db.session.commit()
    
    # AUDIT LOG
    log_audit_action(session['superadmin_id'], 'REVOKE_ADMIN', 'AssociationAdmin', admin.id, f"Revoked database access for {admin.full_name}")
    
    flash(f"Admin {admin.full_name}'s access has been revoked.", "error")
    return redirect(url_for('superadmin.manage_admins'))

# ==========================================
# SYSTEM AUDIT LOGS (WITH FILTERING)
# ==========================================
@superadmin.route('/spdash/audit-logs')
@login_required
def audit_logs():
    query = AuditLog.query

    # 1. Grab filters from the URL parameters
    start_datetime = request.args.get('start_datetime')
    end_datetime = request.args.get('end_datetime')
    actor_type = request.args.get('actor_type')
    action_type = request.args.get('action_type')

    # 2. Apply precise Date & Time filtering
    if start_datetime:
        try:
            # HTML datetime-local format: 'YYYY-MM-DDTHH:MM'
            start_dt = datetime.strptime(start_datetime, '%Y-%m-%dT%H:%M')
            query = query.filter(AuditLog.timestamp >= start_dt)
        except ValueError:
            pass # Ignore malformed dates

    if end_datetime:
        try:
            end_dt = datetime.strptime(end_datetime, '%Y-%m-%dT%H:%M')
            query = query.filter(AuditLog.timestamp <= end_dt)
        except ValueError:
            pass

    # 3. Apply Actor and Action filtering
    if actor_type:
        query = query.filter_by(actor_type=actor_type)
        
    if action_type:
        # Using .contains() so searching "APPROVE" catches "APPROVE_BROKER" and "APPROVE_PROPERTY"
        query = query.filter(AuditLog.action.contains(action_type))

    # 4. Execute the query, newest first
    # We limit to 500 here to prevent server crashing on massive datasets (we'll add pagination later)
    logs = query.order_by(AuditLog.timestamp.desc()).limit(500).all()
    
    return render_template("sp_audit_logs.html", logs=logs)