from flask import Blueprint, render_template, redirect, url_for, session, request, flash
from functools import wraps
from models import db, AssociationAdmin, Organization, Broker, Property, Review, AuditLog
from datetime import datetime, timezone
import random
import string
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from werkzeug.security import generate_password_hash, check_password_hash

association = Blueprint('association', __name__, template_folder="templates", static_folder="static")

# ==========================================
# REVIEW CODE HELPER
# ==========================================
def generate_new_review_code():
    """Generates a secure 8-character uppercase code and ensures it is unique"""
    while True:
        random_chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        new_code = f"RWA-{random_chars}"
        
        # Ensure no other broker has this exact code right now
        if not Broker.query.filter_by(review_code=new_code).first():
            return new_code

# ==========================================
# AUDIT LOG HELPER
# ==========================================
def log_audit_action(actor_id, action, target_type, target_id, description):
    """Silently records critical actions to the database."""
    log = AuditLog(
        actor_type='AssociationAdmin',
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        description=description
    )
    db.session.add(log)
    db.session.commit()

# ==========================================
# EMAIL HELPER
# ==========================================
def send_suspension_email(broker_email, broker_name, status, reason):
    """Sends an email notification to the broker regarding their account status change."""
    sender_email = os.getenv("MAIL_USERNAME")
    sender_password = os.getenv("MAIL_PASSWORD")
    
    if not sender_email or not sender_password:
        print("Warning: Mail credentials not found in environment. Skipping email dispatch.")
        return

    subject = f"RREBP Account Status Update: {status}"
    
    if status == 'Suspended':
        body = f"""Dear {broker_name},

Your RREBP broker account has been suspended by your real estate association.

Reason / Details:
{reason}

If you believe this is an error, please contact your association administrator directly.

Best regards,
RREBP Administration Team"""
    else:
        body = f"""Dear {broker_name},

Good news! Your RREBP broker account has been reactivated.

Note from administration:
{reason}

You may now log back into your portal and resume operations.

Best regards,
RREBP Administration Team"""

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = broker_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, broker_email, msg.as_string())
        server.quit()
        print(f"Status update email successfully sent to {broker_email}")
    except Exception as e:
        print(f"Failed to send email: {e}")

# ==========================================
# AUTH & CONTEXT
# ==========================================
def assoc_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'assoc_admin_id' not in session:
            return redirect(url_for('landing.login_portal'))
        return f(*args, **kwargs)
    return decorated_function

# Globally inject the current admin AND pending notification counts into all Association templates
@association.context_processor
def inject_admin_and_counts():
    if 'assoc_admin_id' in session:
        admin = AssociationAdmin.query.get(session['assoc_admin_id'])
        
        if admin:
            # 1. Count Pending Brokers
            pending_brokers = Broker.query.filter_by(
                organization_id=admin.organization_id, 
                status='Pending Approval'
            ).count()
            
            # Get broker IDs for this org to calculate the next two
            org_brokers = Broker.query.filter_by(organization_id=admin.organization_id).all()
            broker_ids = [b.id for b in org_brokers]
            
            # 2. Count Pending Properties
            pending_properties = 0
            pending_reviews = 0
            
            if broker_ids:
                pending_properties = Property.query.filter(
                    Property.broker_id.in_(broker_ids), 
                    Property.verification_status == 'Pending'
                ).count()
                
                # 3. Count Pending Reviews
                pending_reviews = Review.query.filter(
                    Review.broker_id.in_(broker_ids), 
                    Review.is_approved == False
                ).count()
                
            return dict(
                current_admin=admin,
                pending_brokers_count=pending_brokers,
                pending_properties_count=pending_properties,
                pending_reviews_count=pending_reviews
            )
            
    return dict(
        current_admin=None, 
        pending_brokers_count=0, 
        pending_properties_count=0, 
        pending_reviews_count=0
    )

@association.route('/assocdash')
@assoc_login_required
def dashboard():
    admin = AssociationAdmin.query.get(session['assoc_admin_id'])
    total_brokers = Broker.query.filter_by(organization_id=admin.organization_id).count()
    return render_template("assoc_dashboard.html", admin=admin, total_brokers=total_brokers)

@association.route('/assocdash/logout')
def logout():
    session.pop('assoc_admin_id', None)
    return redirect(url_for('landing.login_portal'))

# ==========================================
# BROKER MANAGEMENT
# ==========================================
@association.route('/assocdash/brokers')
@assoc_login_required
def brokers():
    admin = AssociationAdmin.query.get(session['assoc_admin_id'])
    org_brokers = Broker.query.filter_by(organization_id=admin.organization_id).order_by(Broker.created_at.desc()).all()
    return render_template("assoc_brokers.html", brokers=org_brokers)

@association.route('/assocdash/brokers/<broker_id>/review')
@assoc_login_required
def review_broker(broker_id):
    broker = Broker.query.get_or_404(broker_id)
    admin = AssociationAdmin.query.get(session['assoc_admin_id'])
    
    if broker.organization_id != admin.organization_id:
        flash("Unauthorized access.", "error")
        return redirect(url_for('association.brokers'))
        
    return render_template("assoc_broker_review.html", broker=broker)

@association.route('/assocdash/brokers/<broker_id>/reject', methods=['POST'])
@assoc_login_required
def reject_broker(broker_id):
    broker = Broker.query.get_or_404(broker_id)
    broker_name = broker.full_name
    
    db.session.delete(broker)
    db.session.commit()
    
    # AUDIT LOG
    log_audit_action(session['assoc_admin_id'], 'REJECT_BROKER', 'Broker', broker_id, f"Rejected and deleted broker application: {broker_name}")
    
    flash("Broker application rejected and data securely deleted.", "error")
    return redirect(url_for('association.brokers'))

@association.route('/assocdash/brokers/<broker_id>/verify', methods=['POST'])
@assoc_login_required
def verify_broker(broker_id):
    broker = Broker.query.get_or_404(broker_id)
    data = request.get_json()
    
    broker.verification_code = data.get('broker_hash')
    broker.status = 'Active'
    broker.review_code = generate_new_review_code()
    broker.verified_at = datetime.now(timezone.utc)
    db.session.commit()
    
    # AUDIT LOG
    log_audit_action(session['assoc_admin_id'], 'DEPLOY_BROKER', 'Broker', broker.id, f"Deployed broker {broker.full_name} to blockchain")
    
    return {"status": "success"}, 200

@association.route('/assocdash/brokers/<broker_id>/suspend', methods=['POST'])
@assoc_login_required
def suspend_broker(broker_id):
    broker = Broker.query.get_or_404(broker_id)
    
    # Toggle status based on current state
    new_status = 'Suspended' if broker.status == 'Active' else 'Active'
    reason = request.form.get('suspension_reason', 'No specific reason provided.')
    
    broker.status = new_status
    db.session.commit()
    
    # Dispatch email notification containing the reason
    send_suspension_email(broker.email, broker.full_name, new_status, reason)
    
    # AUDIT LOG
    action_type = 'SUSPEND_BROKER' if new_status == 'Suspended' else 'ACTIVATE_BROKER'
    log_audit_action(session['assoc_admin_id'], action_type, 'Broker', broker.id, f"Changed broker status to: {new_status}. Reason: {reason}")
    
    flash(f"Broker status updated to {new_status} and notification email sent.", "info")
    return redirect(url_for('association.brokers'))

@association.route('/assocdash/brokers/<broker_id>/delete', methods=['POST'])
@assoc_login_required
def delete_broker(broker_id):
    broker = Broker.query.get_or_404(broker_id)
    broker_name = broker.full_name
    
    db.session.delete(broker)
    db.session.commit()
    
    # AUDIT LOG
    log_audit_action(session['assoc_admin_id'], 'DELETE_BROKER', 'Broker', broker_id, f"Permanently deleted broker: {broker_name}")
    
    flash("Broker removed from system.", "error")
    return redirect(url_for('association.brokers'))

# ==========================================
# PROPERTY MANAGEMENT
# ==========================================
@association.route('/assocdash/properties')
@assoc_login_required
def manage_properties():
    admin = AssociationAdmin.query.get(session['assoc_admin_id'])
    
    org_brokers = Broker.query.filter_by(organization_id=admin.organization_id).all()
    broker_ids = [broker.id for broker in org_brokers]
    
    if broker_ids:
        properties = Property.query.filter(Property.broker_id.in_(broker_ids)).order_by(Property.created_at.desc()).all()
    else:
        properties = []
        
    return render_template('assoc_properties.html', admin=admin, properties=properties)

@association.route('/assocdash/brokers/<broker_id>/approve', methods=['POST'])
@assoc_login_required 
def approve_broker(broker_id):
    broker = Broker.query.get_or_404(broker_id)
    
    if broker.verification_code:
        broker.status = 'Active'
        flash_msg = f"Profile updates for {broker.full_name} approved. Account is fully Active again."
    else:
        # No hash yet. This is a brand new application.
        broker.status = 'Pending Registration'
        flash_msg = f"Broker {broker.full_name} approved. They are now ready for on-chain deployment."
        
    db.session.commit()
    
    # AUDIT LOG
    log_audit_action(session['assoc_admin_id'], 'APPROVE_BROKER', 'Broker', broker.id, f"Approved broker application/update: {broker.full_name}")
    
    flash(flash_msg, "success")
    return redirect(url_for('association.brokers'))

@association.route('/assocdash/properties/<property_id>/reject', methods=['POST'])
@assoc_login_required
def reject_property(property_id):
    property_obj = Property.query.get_or_404(property_id)
    property_obj.verification_status = 'Rejected'
    db.session.commit()
    
    # AUDIT LOG
    log_audit_action(session['assoc_admin_id'], 'REJECT_PROPERTY', 'Property', property_obj.id, f"Rejected property listing: {property_obj.title}")
    
    flash(f"Property '{property_obj.title}' has been rejected.", "error")
    return redirect(url_for('association.manage_properties'))

@association.route('/assocdash/properties/<property_id>/approve', methods=['POST'])
@assoc_login_required
def approve_property(property_id):
    admin = AssociationAdmin.query.get(session['assoc_admin_id'])
    property_obj = Property.query.get_or_404(property_id)
    
    # Security check
    if property_obj.broker.organization_id != admin.organization_id:
        flash("Unauthorized action.", "error")
        return redirect(url_for('association.manage_properties'))
        
    property_obj.verification_status = 'Verified'
    db.session.commit()
    
    # AUDIT LOG
    log_audit_action(
        session['assoc_admin_id'], 
        'APPROVE_PROPERTY', 
        'Property', 
        property_obj.id, 
        f"Approved property listing: {property_obj.title}"
    )
    
    flash(f"Property '{property_obj.title}' has been approved and is now public.", "success")
    return redirect(url_for('association.manage_properties'))

@association.route('/assocdash/properties/<property_id>/review')
@assoc_login_required
def review_property(property_id):
    admin = AssociationAdmin.query.get(session['assoc_admin_id'])
    property_obj = Property.query.get_or_404(property_id)
    
    if property_obj.broker.organization_id != admin.organization_id:
        flash("Unauthorized access.", "error")
        return redirect(url_for('association.manage_properties'))
        
    return render_template('assoc_property_review.html', admin=admin, property=property_obj)

# ==========================================
# REVIEW MANAGEMENT
# ==========================================
@association.route('/assocdash/reviews')
@assoc_login_required
def manage_reviews():
    admin = AssociationAdmin.query.get(session['assoc_admin_id'])
    
    org_brokers = Broker.query.filter_by(organization_id=admin.organization_id).all()
    broker_ids = [b.id for b in org_brokers]
    
    pending_reviews = Review.query.filter(
        Review.broker_id.in_(broker_ids), 
        Review.is_approved == False
    ).order_by(Review.created_at.desc()).all()
    
    return render_template('assoc_reviews.html', admin=admin, pending_reviews=pending_reviews)

@association.route('/assocdash/reviews/<review_id>/approve', methods=['POST'])
@assoc_login_required
def approve_review(review_id):
    admin = AssociationAdmin.query.get(session['assoc_admin_id'])
    review = Review.query.get_or_404(review_id)
    
    if review.broker.organization_id != admin.organization_id:
        flash("Unauthorized action.", "error")
        return redirect(url_for('association.manage_reviews'))
        
    review.is_approved = True
    db.session.commit()
    
    # AUDIT LOG
    log_audit_action(session['assoc_admin_id'], 'APPROVE_REVIEW', 'Review', review.id, f"Approved client review for {review.broker.full_name}")
    
    flash("Review approved! It is now visible on the broker's public profile.", "success")
    return redirect(url_for('association.manage_reviews'))

@association.route('/assocdash/reviews/<review_id>/reject', methods=['POST'])
@assoc_login_required
def reject_review(review_id):
    admin = AssociationAdmin.query.get(session['assoc_admin_id'])
    review = Review.query.get_or_404(review_id)
    
    if review.broker.organization_id != admin.organization_id:
        flash("Unauthorized action.", "error")
        return redirect(url_for('association.manage_reviews'))
        
    broker_name = review.broker.full_name
    db.session.delete(review)
    db.session.commit()
    
    # AUDIT LOG
    log_audit_action(session['assoc_admin_id'], 'REJECT_REVIEW', 'Review', review_id, f"Rejected and deleted client review for {broker_name}")
    
    flash("Review rejected and deleted.", "info")
    return redirect(url_for('association.manage_reviews'))

@association.route('/assocdash/settings', methods=['GET', 'POST'])
@assoc_login_required
def settings():
    admin = AssociationAdmin.query.get(session['assoc_admin_id'])
    
    if request.method == 'POST':
        
        # 1. HANDLE WEB3 WALLET CONNECTION (JSON request)
        if request.is_json:
            data = request.get_json()
            wallet = data.get('wallet_address')
            if wallet:
                admin.wallet_address = wallet
                db.session.commit()
                
                log_audit_action(session['assoc_admin_id'], 'UPDATE_WALLET', 'AssociationAdmin', admin.id, f"Connected new Web3 Wallet: {wallet[:6]}...{wallet[-4:]}")
                
                flash("Wallet address connected successfully!", "success")
                return {"status": "success"}, 200
            return {"status": "error"}, 400

        # 2. HANDLE STANDARD FORM SUBMISSIONS
        action = request.form.get('action')

        # A. PROFILE UPDATE & RE-VERIFICATION
        if action == 'update_profile':
            admin.full_name = request.form.get('full_name')
            
            # THE FLIP: Revoke active status until Super Admin re-approves
            admin.account_status = 'Pending'
            db.session.commit()
            
            log_audit_action(session['assoc_admin_id'], 'UPDATE_PROFILE', 'AssociationAdmin', admin.id, "Admin updated profile identity. Triggered Super Admin re-verification.")
            
            flash("Profile updated! Your admin privileges are paused pending Super Admin re-verification.", "info")
            return redirect(url_for('association.dashboard'))

        # B. SECURE PASSWORD CHANGE
        elif action == 'update_password':
            current_password = request.form.get('current_password')
            new_password = request.form.get('new_password')

            if not check_password_hash(admin.password_hash, current_password):
                flash("Incorrect current password. Security check failed.", "error")
            elif len(new_password) < 8:
                flash("New password must be at least 8 characters long.", "error")
            else:
                admin.password_hash = generate_password_hash(new_password)
                db.session.commit()
                
                log_audit_action(session['assoc_admin_id'], 'CHANGE_PASSWORD', 'AssociationAdmin', admin.id, "Admin securely updated their password.")
                flash("Password updated successfully.", "success")
                
            return redirect(url_for('association.settings'))

        # Account deletion
        elif action == 'delete_account':
            db.session.delete(admin)
            db.session.commit()
            
            # Log it under a system ID since the admin is gone
            log_audit_action('system', 'DELETE_ACCOUNT', 'AssociationAdmin', admin.id, f"Admin deleted their own account: {admin.full_name}")
            
            session.pop('assoc_admin_id', None)
            flash("Your association admin account has been permanently deleted.", "info")
            return redirect(url_for('landing.home'))
            
    return render_template("assoc_settings.html", admin=admin)