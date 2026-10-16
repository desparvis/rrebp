from flask import Blueprint, render_template, redirect, url_for, session, request, flash
from functools import wraps
from models import db, AssociationAdmin, Organization, Broker
from datetime import datetime, timezone

association = Blueprint('association', __name__, template_folder="templates", static_folder="static")

def assoc_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'assoc_admin_id' not in session:
            return redirect(url_for('landing.login_portal'))
        return f(*args, **kwargs)
    return decorated_function

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
    # Only show brokers belonging to THIS admin's organization
    org_brokers = Broker.query.filter_by(organization_id=admin.organization_id).order_by(Broker.created_at.desc()).all()
    return render_template("assoc_brokers.html", brokers=org_brokers)

@association.route('/assocdash/brokers/new', methods=['GET', 'POST'])
@assoc_login_required
def new_broker():
    admin = AssociationAdmin.query.get(session['assoc_admin_id'])
    
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        title = request.form.get('professional_title')
        license_num = request.form.get('license_number')
        bio = request.form.get('bio')
        
        new_broker = Broker(
            organization_id=admin.organization_id,
            full_name=full_name,
            email=email,
            phone=phone,
            professional_title=title,
            license_number=license_num,
            bio=bio,
            registered_by=admin.id
        )
        db.session.add(new_broker)
        db.session.commit()
        
        flash("Broker saved locally. Ready for blockchain verification.", "success")
        return redirect(url_for('association.brokers'))
        
    return render_template("assoc_broker_form.html")

@association.route('/assocdash/logout')
def logout():
    session.pop('assoc_admin_id', None)
    return redirect(url_for('landing.login_portal'))

@association.route('/assocdash/brokers/<broker_id>/verify', methods=['POST'])
@assoc_login_required
def verify_broker(broker_id):
    broker = Broker.query.get_or_404(broker_id)
    data = request.get_json()
    
    # Save the blockchain hash and update status
    broker.verification_code = data.get('broker_hash')
    broker.status = 'Active'
    broker.verified_at = datetime.now(timezone.utc)
    
    db.session.commit()
    return {"status": "success"}, 200

@association.route('/assocdash/brokers/<broker_id>/suspend', methods=['POST'])
@assoc_login_required
def suspend_broker(broker_id):
    broker = Broker.query.get_or_404(broker_id)
    # Toggle between suspended and active
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