from flask import Blueprint, render_template, redirect, url_for, session, request, flash
from functools import wraps
from models import db, AssociationAdmin, Organization, Broker, Property, Review, AuditLog
from datetime import datetime, timezone

association = Blueprint('association', __name__, template_folder="templates", static_folder="static")

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

@association.route('/assocdash/brokers/<broker_id>/approve', methods=['POST'])
@assoc_login_required 
def approve_broker(broker_id):
    broker = Broker.query.get_or_404(broker_id)
    broker.status = 'Pending Registration'
    db.session.commit()
    
    # AUDIT LOG
    log_audit_action(session['assoc_admin_id'], 'APPROVE_BROKER', 'Broker', broker.id, f"Approved broker application: {broker.full_name}")
    
    flash(f"Broker {broker.full_name} approved. They are now ready for on-chain deployment.", "success")
    return redirect(url_for('association.brokers'))

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
    broker.verified_at = datetime.now(timezone.utc)
    db.session.commit()
    
    # AUDIT LOG
    log_audit_action(session['assoc_admin_id'], 'DEPLOY_BROKER', 'Broker', broker.id, f"Deployed broker {broker.full_name} to blockchain")
    
    return {"status": "success"}, 200

@association.route('/assocdash/brokers/<broker_id>/suspend', methods=['POST'])
@assoc_login_required
def suspend_broker(broker_id):
    broker = Broker.query.get_or_404(broker_id)
    broker.status = 'Suspended' if broker.status == 'Active' else 'Active'
    db.session.commit()
    
    # AUDIT LOG
    action_type = 'SUSPEND_BROKER' if broker.status == 'Suspended' else 'ACTIVATE_BROKER'
    log_audit_action(session['assoc_admin_id'], action_type, 'Broker', broker.id, f"Changed broker status to: {broker.status}")
    
    flash(f"Broker status updated to {broker.status}.", "info")
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

@association.route('/assocdash/settings', methods=['GET', 'POST'])
@assoc_login_required
def settings():
    admin = AssociationAdmin.query.get(session['assoc_admin_id'])
    
    if request.method == 'POST':
        data = request.get_json()
        wallet = data.get('wallet_address')
        if wallet:
            admin.wallet_address = wallet
            db.session.commit()
            
            # AUDIT LOG
            log_audit_action(session['assoc_admin_id'], 'UPDATE_WALLET', 'AssociationAdmin', admin.id, f"Connected new Web3 Wallet: {wallet[:6]}...{wallet[-4:]}")
            
            flash("Wallet address connected successfully!", "success")
            return {"status": "success"}, 200
        return {"status": "error"}, 400
        
    return render_template("assoc_settings.html")

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

@association.route('/assocdash/properties/<property_id>/approve', methods=['POST'])
@assoc_login_required
def approve_property(property_id):
    property_obj = Property.query.get_or_404(property_id)
    property_obj.verification_status = 'Verified'
    db.session.commit()
    
    # AUDIT LOG
    log_audit_action(session['assoc_admin_id'], 'APPROVE_PROPERTY', 'Property', property_obj.id, f"Verified property listing: {property_obj.title}")
    
    flash(f"Property '{property_obj.title}' has been officially verified.", "success")
    return redirect(url_for('association.manage_properties'))

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