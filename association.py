from flask import Blueprint, render_template, redirect, url_for, session, request, flash
from functools import wraps
from models import db, AssociationAdmin, Organization, Broker
from datetime import datetime, timezone

association = Blueprint('association', __name__, template_folder="templates", static_folder="static")

# Authentication Check
def assoc_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'assoc_admin_id' not in session:
            return redirect(url_for('landing.login_portal'))
        return f(*args, **kwargs)
    return decorated_function

# Globally inject the current admin into all Association templates
@association.context_processor
def inject_admin():
    if 'assoc_admin_id' in session:
        admin = AssociationAdmin.query.get(session['assoc_admin_id'])
        return dict(current_admin=admin)
    return dict(current_admin=None)

# Dashboard And Core Views
@association.route('/assocdash')
@assoc_login_required
def dashboard():
    admin = AssociationAdmin.query.get(session['assoc_admin_id'])
    total_brokers = Broker.query.filter_by(organization_id=admin.organization_id).count()
    return render_template("assoc_dashboard.html", admin=admin, total_brokers=total_brokers)

@association.route('/assocdash/brokers')
@assoc_login_required
def brokers():
    admin = AssociationAdmin.query.get(session['assoc_admin_id'])
    org_brokers = Broker.query.filter_by(organization_id=admin.organization_id).order_by(Broker.created_at.desc()).all()
    return render_template("assoc_brokers.html", brokers=org_brokers)

@association.route('/assocdash/logout')
def logout():
    session.pop('assoc_admin_id', None)
    return redirect(url_for('landing.login_portal'))

# Application Review Logic
@association.route('/assocdash/brokers/<broker_id>/review')
@assoc_login_required
def review_broker(broker_id):
    broker = Broker.query.get_or_404(broker_id)
    admin = AssociationAdmin.query.get(session['assoc_admin_id'])
    
    # Security Check: Ensure admin is only reviewing their own brokers
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
    
    flash(f"Broker {broker.full_name} approved. They are now ready for on-chain deployment.", "success")
    return redirect(url_for('association.brokers'))

@association.route('/assocdash/brokers/<broker_id>/reject', methods=['POST'])
@assoc_login_required
def reject_broker(broker_id):
    broker = Broker.query.get_or_404(broker_id)
    
    db.session.delete(broker)
    db.session.commit()
    
    flash("Broker application rejected and data securely deleted.", "error")
    return redirect(url_for('association.brokers'))

# Blockchain And Status Management
@association.route('/assocdash/brokers/<broker_id>/verify', methods=['POST'])
@assoc_login_required
def verify_broker(broker_id):
    broker = Broker.query.get_or_404(broker_id)
    data = request.get_json()
    
    broker.verification_code = data.get('broker_hash')
    broker.status = 'Active'
    broker.verified_at = datetime.now(timezone.utc)
    
    db.session.commit()
    return {"status": "success"}, 200

@association.route('/assocdash/brokers/<broker_id>/suspend', methods=['POST'])
@assoc_login_required
def suspend_broker(broker_id):
    broker = Broker.query.get_or_404(broker_id)
    broker.status = 'Suspended' if broker.status == 'Active' else 'Active'
    db.session.commit()
    
    flash(f"Broker status updated to {broker.status}.", "info")
    return redirect(url_for('association.brokers'))

@association.route('/assocdash/brokers/<broker_id>/delete', methods=['POST'])
@assoc_login_required
def delete_broker(broker_id):
    broker = Broker.query.get_or_404(broker_id)
    
    db.session.delete(broker)
    db.session.commit()
    
    flash("Broker removed from system.", "error")
    return redirect(url_for('association.brokers'))

# Wallet Settings Page
@association.route('/assocdash/settings', methods=['GET', 'POST'])
@assoc_login_required
def settings():
    admin = AssociationAdmin.query.get(session['assoc_admin_id'])
    
    # If they submit a new wallet via MetaMask
    if request.method == 'POST':
        data = request.get_json()
        wallet = data.get('wallet_address')
        if wallet:
            admin.wallet_address = wallet
            db.session.commit()
            flash("Wallet address connected successfully!", "success")
            return {"status": "success"}, 200
        return {"status": "error"}, 400
        
    return render_template("assoc_settings.html")