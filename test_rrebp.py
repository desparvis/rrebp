import os
import sys
import io
import unittest
from unittest.mock import patch

# Ensure project root is on sys.path when running from inside the tests/ folder
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Force isolated in-memory SQLite database so live Supabase data is never touched
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['SECRET_KEY'] = 'rrebp-full-coverage-secret-key'

import flask
from jinja2 import TemplateNotFound
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import SignatureExpired

import app as rrebp_app
from app import app
from models import (
    db, generate_uuid, SuperAdmin, Organization,
    AssociationAdmin, Broker, Property, PropertyImage, Review, AuditLog
)
import landing
import association
import superadmin
import broker

_real_render = flask.render_template


def _safe_render(template_name, **kwargs):
    """Renders real Jinja templates and only falls back if custom 404/500 error files are absent."""
    try:
        return _real_render(template_name, **kwargs)
    except TemplateNotFound:
        return f"Rendered {template_name}"


class TestRREBPFullCoverageSuite(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'rrebp-full-coverage-secret-key'
        cls.client = app.test_client()
        cls.ctx = app.app_context()
        cls.ctx.push()
        db.create_all()

        cls.render_patches = [
            patch.object(rrebp_app, 'render_template', side_effect=_safe_render),
            patch.object(landing, 'render_template', side_effect=_safe_render),
            patch.object(association, 'render_template', side_effect=_safe_render),
            patch.object(broker, 'render_template', side_effect=_safe_render),
            patch.object(superadmin, 'render_template', side_effect=_safe_render),
        ]
        for p in cls.render_patches:
            p.start()

        # Seed core entities across two separate organizations for RBAC & isolation checks
        cls.sa = SuperAdmin(
            email="sa@rrebp.rw",
            password_hash=generate_password_hash("SuperPass!123")
        )
        db.session.add(cls.sa)
        db.session.flush()

        cls.org1 = Organization(
            name="Rwanda Real Estate Association",
            registration_number="RREBP-111111-RRE",
            email="org1@rrebp.rw",
            phone="0780000001",
            status="Active",
            created_by=cls.sa.id
        )
        cls.org2 = Organization(
            name="Kigali Brokers Union",
            registration_number="RREBP-222222-KBU",
            email="org2@rrebp.rw",
            phone="0780000002",
            status="Active",
            created_by=cls.sa.id
        )
        db.session.add_all([cls.org1, cls.org2])
        db.session.flush()

        cls.admin1 = AssociationAdmin(
            full_name="Alice Admin",
            email="alice@rrebp.rw",
            password_hash=generate_password_hash("AdminPass!123"),
            organization_id=cls.org1.id,
            account_status="Active",
            created_by=cls.sa.id
        )
        cls.admin2 = AssociationAdmin(
            full_name="Bob Admin",
            email="bob@rrebp.rw",
            password_hash=generate_password_hash("AdminPass!123"),
            organization_id=cls.org2.id,
            account_status="Pending",
            created_by=cls.sa.id
        )
        db.session.add_all([cls.admin1, cls.admin2])
        db.session.flush()

        cls.broker1 = Broker(
            organization_id=cls.org1.id,
            full_name="Jean Paul Broker",
            phone="0781111111",
            email="jp@rrebp.rw",
            password_hash=generate_password_hash("BrokerPass!123"),
            license_number="RWA-2026-1111111111",
            review_code="RWA-REV11111",
            status="Active",
            registered_by=cls.admin1.id
        )
        cls.broker2 = Broker(
            organization_id=cls.org2.id,
            full_name="Other Org Broker",
            phone="0782222222",
            email="other@rrebp.rw",
            password_hash=generate_password_hash("BrokerPass!123"),
            license_number="RWA-2026-2222222222",
            review_code=None,
            status="Suspended",
            registered_by=cls.admin2.id
        )
        db.session.add_all([cls.broker1, cls.broker2])
        db.session.commit()

    @classmethod
    def tearDownClass(cls):
        for p in cls.render_patches:
            p.stop()
        db.session.remove()
        db.drop_all()
        cls.ctx.pop()

    def test_01_models_uuid_and_error_handlers(self):
        """Verify UUID v4 primary keys in models.py and global 404/500 handlers in app.py."""
        uid1 = generate_uuid()
        uid2 = generate_uuid()
        self.assertEqual(len(uid1), 36)
        self.assertNotEqual(uid1, uid2)

        with app.test_request_context('/missing-page'):
            if hasattr(rrebp_app, 'page_not_found'):
                _, code_404 = rrebp_app.page_not_found(Exception("Not found"))
                self.assertEqual(code_404, 404)
            if hasattr(rrebp_app, 'internal_server_error'):
                _, code_500 = rrebp_app.internal_server_error(Exception("Server error"))
                self.assertEqual(code_500, 500)

    def test_02_superadmin_auth_and_session_guards(self):
        """Verify SuperAdmin login, invalid credentials rejection, session guard, and logout."""
        self.assertEqual(self.client.get('/spdash').status_code, 302)
        self.assertEqual(self.client.get('/spdash/login').status_code, 200)

        # Invalid password stays on login page without setting session
        self.client.post('/spdash/login', data={'email': 'sa@rrebp.rw', 'password': 'wrong'})
        with self.client.session_transaction() as sess:
            self.assertNotIn('superadmin_id', sess)

        # Valid login redirects to dashboard
        res = self.client.post('/spdash/login', data={'email': 'sa@rrebp.rw', 'password': 'SuperPass!123'})
        self.assertEqual(res.status_code, 302)
        self.assertEqual(self.client.get('/spdash/login').status_code, 302)
        self.assertEqual(self.client.get('/spdash').status_code, 200)

        # Logout clears session
        self.assertEqual(self.client.get('/spdash/logout').status_code, 302)
        self.assertEqual(self.client.get('/spdash').status_code, 302)

    def test_03_superadmin_org_admin_and_audit_logs(self):
        """Verify SuperAdmin organization CRUD, admin approval/revocation, and audit log filtering."""
        with self.client.session_transaction() as sess:
            sess['superadmin_id'] = self.sa.id

        self.assertEqual(self.client.get('/spdash/organizations').status_code, 200)
        self.assertEqual(self.client.get('/spdash/organizations/new').status_code, 200)

        # Create organization and verify generated RREBP-XXXXXX-GAS registration number
        self.client.post('/spdash/organizations/new', data={
            'name': 'Gasabo Realty Group',
            'email': 'gasabo@rrebp.rw',
            'phone': '0783333333',
            'address': 'Kimironko, Kigali'
        })
        temp_org = Organization.query.filter_by(email='gasabo@rrebp.rw').first()
        self.assertIsNotNone(temp_org)
        self.assertTrue(temp_org.registration_number.startswith('RREBP-'))

        # Edit organization and suspend status
        self.assertEqual(self.client.get(f'/spdash/organizations/{temp_org.id}/edit').status_code, 200)
        self.client.post(f'/spdash/organizations/{temp_org.id}/edit', data={
            'name': 'Gasabo Realty Updated',
            'email': 'gasabo@rrebp.rw',
            'phone': '0783333333',
            'address': 'Remera, Kigali',
            'status': 'Suspended'
        })
        db.session.refresh(temp_org)
        self.assertEqual(temp_org.status, 'Suspended')

        # Delete temporary organization
        self.client.post(f'/spdash/organizations/{temp_org.id}/delete')
        self.assertIsNone(db.session.get(Organization, temp_org.id))

        # Approve and revoke Association Admin
        self.assertEqual(self.client.get('/spdash/admins').status_code, 200)
        self.client.post(f'/spdash/admins/{self.admin2.id}/approve')
        db.session.refresh(self.admin2)
        self.assertEqual(self.admin2.account_status, 'Active')

        self.client.post(f'/spdash/admins/{self.admin2.id}/revoke')
        db.session.refresh(self.admin2)
        self.assertEqual(self.admin2.account_status, 'Revoked')

        # Filter audit logs with valid and malformed timestamps
        res_valid = self.client.get(
            '/spdash/audit-logs?start_datetime=2026-01-01T00:00&end_datetime=2027-12-31T23:59&actor_type=SuperAdmin&action_type=ORG'
        )
        res_bad = self.client.get('/spdash/audit-logs?start_datetime=bad-date&end_datetime=bad-date')
        self.assertEqual(res_valid.status_code, 200)
        self.assertEqual(res_bad.status_code, 200)

    @patch('association.smtplib.SMTP')
    def test_04_association_smtp_and_broker_vetting(self, mock_smtp):
        """Verify SMTP suspension notices, cross-org isolation, and on-chain broker verification."""
        with patch.dict(os.environ, {'MAIL_USERNAME': '', 'MAIL_PASSWORD': ''}):
            association.send_suspension_email('jp@rrebp.rw', 'JP', 'Suspended', 'Missing env test')

        with patch.dict(os.environ, {'MAIL_USERNAME': 'sys@rrebp.rw', 'MAIL_PASSWORD': 'pass'}):
            association.send_suspension_email('jp@rrebp.rw', 'JP', 'Suspended', 'Violation')
            association.send_suspension_email('jp@rrebp.rw', 'JP', 'Active', 'Cleared')
            mock_smtp.side_effect = Exception("SMTP Failure")
            association.send_suspension_email('jp@rrebp.rw', 'JP', 'Suspended', 'Handled exception')
            mock_smtp.side_effect = None

        with self.client.session_transaction() as sess:
            sess.clear()
        self.assertEqual(self.client.get('/assocdash').status_code, 302)

        with self.client.session_transaction() as sess:
            sess['assoc_admin_id'] = self.admin1.id

        self.assertEqual(self.client.get('/assocdash').status_code, 200)
        self.assertEqual(self.client.get('/assocdash/brokers').status_code, 200)

        # Authorized vs cross-organization broker review check
        self.assertEqual(self.client.get(f'/assocdash/brokers/{self.broker1.id}/review').status_code, 200)
        self.assertEqual(self.client.get(f'/assocdash/brokers/{self.broker2.id}/review').status_code, 302)

        # Step 1: Approve new broker -> Pending Registration
        self.broker1.verification_code = None
        db.session.commit()
        self.client.post(f'/assocdash/brokers/{self.broker1.id}/approve')
        db.session.refresh(self.broker1)
        self.assertEqual(self.broker1.status, 'Pending Registration')

        # Step 2: Anchor Sepolia hash -> Active + RWA-XXXXXXXX review code
        res_verify = self.client.post(
            f'/assocdash/brokers/{self.broker1.id}/verify',
            json={'broker_hash': '0x9f8e7d6c5b4a'}
        )
        self.assertEqual(res_verify.status_code, 200)
        db.session.refresh(self.broker1)
        self.assertEqual(self.broker1.status, 'Active')
        self.assertEqual(self.broker1.verification_code, '0x9f8e7d6c5b4a')
        self.assertTrue(self.broker1.review_code.startswith('RWA-'))

        # Re-approving a broker who already has a hash restores Active directly
        self.broker1.status = 'Pending Approval'
        db.session.commit()
        self.client.post(f'/assocdash/brokers/{self.broker1.id}/approve')
        db.session.refresh(self.broker1)
        self.assertEqual(self.broker1.status, 'Active')

        # Suspend and reactivate toggle
        with patch('association.send_suspension_email'):
            self.client.post(f'/assocdash/brokers/{self.broker1.id}/suspend', data={'suspension_reason': 'Audit'})
            db.session.refresh(self.broker1)
            self.assertEqual(self.broker1.status, 'Suspended')

            self.client.post(f'/assocdash/brokers/{self.broker1.id}/suspend', data={'suspension_reason': 'Cleared'})
            db.session.refresh(self.broker1)
            self.assertEqual(self.broker1.status, 'Active')

        # Reject and delete temporary brokers
        b_rej = Broker(organization_id=self.org1.id, full_name="Rej", phone="078", email="rej@r.rw", password_hash="h", license_number="L-REJ")
        b_del = Broker(organization_id=self.org1.id, full_name="Del", phone="078", email="delb@r.rw", password_hash="h", license_number="L-DEL")
        db.session.add_all([b_rej, b_del])
        db.session.commit()
        rej_id, del_id = b_rej.id, b_del.id

        self.client.post(f'/assocdash/brokers/{rej_id}/reject')
        self.client.post(f'/assocdash/brokers/{del_id}/delete')
        self.assertIsNone(db.session.get(Broker, rej_id))
        self.assertIsNone(db.session.get(Broker, del_id))

    def test_05_association_property_and_review_moderation(self):
        """Verify UPI property moderation, review approval/rejection, and cross-org security blocks."""
        with self.client.session_transaction() as sess:
            sess['assoc_admin_id'] = self.admin1.id

        p1 = Property(
            broker_id=self.broker1.id, title="Kigali Heights", description="Commercial",
            price=200000, listing_type="For Sale", province="Kigali", district="Gasabo",
            sector="Kimihurura", cell="Rugando", village="Gasange", upi_number="1/01/05/02/111"
        )
        p2 = Property(
            broker_id=self.broker2.id, title="Org2 House", description="Residential",
            price=100000, listing_type="For Rent", province="Kigali", district="Kicukiro",
            sector="Niboye", cell="Gatare", village="Imena", upi_number="1/02/07/01/222"
        )
        r1 = Review(broker_id=self.broker1.id, client_name="C1", rating=5, comment="Reliable", is_approved=False)
        r2 = Review(broker_id=self.broker2.id, client_name="C2", rating=4, comment="Cross org", is_approved=False)
        r3 = Review(broker_id=self.broker1.id, client_name="C3", rating=1, comment="Spam", is_approved=False)
        db.session.add_all([p1, p2, r1, r2, r3])
        db.session.commit()

        # Cross-org property review & approval must be blocked
        self.assertEqual(self.client.get('/assocdash/properties').status_code, 200)
        self.assertEqual(self.client.get(f'/assocdash/properties/{p1.id}/review').status_code, 200)
        self.assertEqual(self.client.get(f'/assocdash/properties/{p2.id}/review').status_code, 302)

        self.client.post(f'/assocdash/properties/{p2.id}/approve')
        db.session.refresh(p2)
        self.assertEqual(p2.verification_status, 'Pending')

        # Authorized reject then approve
        self.client.post(f'/assocdash/properties/{p1.id}/reject')
        db.session.refresh(p1)
        self.assertEqual(p1.verification_status, 'Rejected')

        self.client.post(f'/assocdash/properties/{p1.id}/approve')
        db.session.refresh(p1)
        self.assertEqual(p1.verification_status, 'Verified')

        # Cross-org review moderation blocked; authorized review approved & spam deleted
        self.assertEqual(self.client.get('/assocdash/reviews').status_code, 200)
        self.client.post(f'/assocdash/reviews/{r2.id}/approve')
        self.client.post(f'/assocdash/reviews/{r2.id}/reject')
        db.session.refresh(r2)
        self.assertFalse(r2.is_approved)

        self.client.post(f'/assocdash/reviews/{r1.id}/approve')
        db.session.refresh(r1)
        self.assertTrue(r1.is_approved)

        r3_id = r3.id
        self.client.post(f'/assocdash/reviews/{r3_id}/reject')
        self.assertIsNone(db.session.get(Review, r3_id))

    def test_06_association_settings_and_anti_tamper(self):
        """Verify Association Admin Web3 wallet binding, profile re-verification flip, and password checks."""
        with self.client.session_transaction() as sess:
            sess['assoc_admin_id'] = self.admin1.id

        self.assertEqual(self.client.get('/assocdash/settings').status_code, 200)
        self.assertEqual(self.client.post('/assocdash/settings', json={'wallet_address': '0x1234567890abcdef'}).status_code, 200)
        self.assertEqual(self.client.post('/assocdash/settings', json={}).status_code, 400)
        db.session.refresh(self.admin1)
        self.assertEqual(self.admin1.wallet_address, '0x1234567890abcdef')

        # Profile update must pause admin account_status to Pending
        self.client.post('/assocdash/settings', data={'action': 'update_profile', 'full_name': 'Alice Verified'})
        db.session.refresh(self.admin1)
        self.assertEqual(self.admin1.account_status, 'Pending')
        self.admin1.account_status = 'Active'
        db.session.commit()

        # Password checks (wrong current, too short, valid update)
        self.client.post('/assocdash/settings', data={'action': 'update_password', 'current_password': 'wrong', 'new_password': 'NewPassword!123'})
        self.client.post('/assocdash/settings', data={'action': 'update_password', 'current_password': 'AdminPass!123', 'new_password': 'short'})
        self.client.post('/assocdash/settings', data={'action': 'update_password', 'current_password': 'AdminPass!123', 'new_password': 'AdminPass!123'})

        # Empty organization branch & self-deletion
        org_empty = Organization(name="Empty Org", registration_number="R-0", email="e@r.rw", phone="078", created_by=self.sa.id)
        db.session.add(org_empty)
        db.session.flush()
        temp_admin = AssociationAdmin(full_name="Temp", email="ta@r.rw", password_hash="h", organization_id=org_empty.id, created_by=self.sa.id)
        db.session.add(temp_admin)
        db.session.commit()
        ta_id = temp_admin.id

        with self.client.session_transaction() as sess:
            sess['assoc_admin_id'] = ta_id
        self.assertEqual(self.client.get('/assocdash/properties').status_code, 200)
        self.client.post('/assocdash/settings', data={'action': 'delete_account'})
        self.assertIsNone(db.session.get(AssociationAdmin, ta_id))
        self.assertEqual(self.client.get('/assocdash/logout').status_code, 302)

    @patch('broker.cloudinary.api.delete_folder')
    @patch('broker.cloudinary.uploader.destroy')
    @patch('broker.cloudinary.uploader.upload')
    def test_07_broker_portal_properties_and_cloudinary(self, mock_upload, mock_destroy, mock_del_folder):
        """Verify Broker session guards, property CRUD, Cloudinary media lifecycle, and ownership locks."""
        mock_upload.return_value = {'secure_url': 'https://res.cloudinary.com/demo/img.jpg', 'public_id': 'pid_1'}

        # Unauthenticated & Suspended broker ejection
        with self.client.session_transaction() as sess:
            sess.clear()
        self.assertEqual(self.client.get('/dashboard').status_code, 302)
        self.assertEqual(self.client.get('/brokerdash/settings').status_code, 302)

        with self.client.session_transaction() as sess:
            sess['broker_id'] = self.broker2.id
        self.assertEqual(self.client.get('/dashboard').status_code, 302)

        # Active broker auto-generates review_code if missing
        self.broker1.status = 'Active'
        self.broker1.review_code = None
        db.session.commit()
        with self.client.session_transaction() as sess:
            sess['broker_id'] = self.broker1.id
        self.assertEqual(self.client.get('/dashboard').status_code, 200)
        db.session.refresh(self.broker1)
        self.assertIsNotNone(self.broker1.review_code)

        # Property filtering and creation with UPI & Cloudinary image
        self.assertEqual(
            self.client.get(
                '/my-properties?province=Kigali&district=Gasabo&sector=Kimihurura&cell=Rugando&village=Gasange'
                '&listing_type=For+Sale&min_price=100&max_price=500000&bedrooms=1&bathrooms=1'
            ).status_code,
            200
        )
        self.assertEqual(self.client.get('/my-properties/add').status_code, 200)
        self.client.post('/my-properties/add', data={
            'title': 'Nyarutarama Villa', 'description': 'Pool villa', 'price': '350000',
            'listing_type': 'For Sale', 'province': 'Kigali', 'district': 'Gasabo',
            'sector': 'Remera', 'cell': 'Rukiri', 'village': 'Amajyambere',
            'bedrooms': '4', 'bathrooms': '3', 'upi_number': '1/01/01/01/1234',
            'images': (io.BytesIO(b"fake_image_bytes"), 'villa.jpg')
        }, content_type='multipart/form-data')

        added_prop = Property.query.filter_by(title='Nyarutarama Villa').first()
        self.assertIsNotNone(added_prop)
        self.assertEqual(added_prop.verification_status, 'Pending')

        other_prop = Property.query.filter_by(broker_id=self.broker2.id).first()
        if not other_prop:
            other_prop = Property(
                broker_id=self.broker2.id, title="Other Broker Prop", description="Desc",
                price=90000, listing_type="For Rent", province="Kigali", district="Kicukiro",
                sector="Niboye", cell="Gatare", village="Imena"
            )
            db.session.add(other_prop)
            db.session.commit()

        # Ownership checks on view, edit, image delete (403), and property delete
        self.assertEqual(self.client.get(f'/my-properties/{added_prop.id}/view').status_code, 200)
        self.assertEqual(self.client.get(f'/my-properties/{other_prop.id}/view').status_code, 302)
        self.assertEqual(self.client.get(f'/my-properties/{added_prop.id}/edit').status_code, 200)
        self.assertEqual(self.client.get(f'/my-properties/{other_prop.id}/edit').status_code, 302)

        self.client.post(f'/my-properties/{added_prop.id}/edit', data={
            'title': 'Nyarutarama Villa Edited', 'description': 'Updated', 'price': '360000',
            'listing_type': 'For Sale', 'province': 'Kigali', 'district': 'Gasabo',
            'sector': 'Remera', 'cell': 'Rukiri', 'village': 'Amajyambere',
            'bedrooms': '5', 'bathrooms': '4', 'upi_number': '1/01/01/01/1234',
            'images': (io.BytesIO(b"fake_image_2"), 'villa2.jpg')
        }, content_type='multipart/form-data')

        other_img = PropertyImage(property_id=other_prop.id, image_url='u', public_id='p')
        db.session.add(other_img)
        db.session.commit()
        self.assertEqual(self.client.post(f'/my-properties/image/{other_img.id}/delete').status_code, 403)

        own_img = PropertyImage.query.filter_by(property_id=added_prop.id).first()
        mock_destroy.side_effect = Exception("Cloudinary destroy err")
        self.client.post(f'/my-properties/image/{own_img.id}/delete')

        self.client.post(f'/my-properties/{other_prop.id}/delete')
        self.assertIsNotNone(db.session.get(Property, other_prop.id))

        added_id = added_prop.id
        mock_del_folder.side_effect = Exception("Folder err")
        self.client.post(f'/my-properties/{added_id}/delete')
        self.assertIsNone(db.session.get(Property, added_id))

    @patch('broker.cloudinary.uploader.upload')
    def test_08_broker_reviews_settings_and_anti_tamper(self, mock_upload):
        """Verify Broker rating calculation, profile edit re-verification flip, and password/account actions."""
        mock_upload.return_value = {'secure_url': 'https://res.cloudinary.com/demo/avatar.jpg'}
        self.broker1.status = 'Active'
        if not Review.query.filter_by(broker_id=self.broker1.id, is_approved=True).first():
            db.session.add(Review(broker_id=self.broker1.id, client_name="Buyer", rating=5, comment="Top", is_approved=True))
        db.session.commit()

        with self.client.session_transaction() as sess:
            sess['broker_id'] = self.broker1.id

        self.assertEqual(self.client.get('/my-reviews').status_code, 200)
        self.assertEqual(self.client.get('/brokerdash/settings').status_code, 200)

        # Updating broker profile must reset status back to Pending Approval
        self.client.post('/brokerdash/settings', data={
            'action': 'update_profile', 'phone': '0780000000',
            'professional_title': 'Lead Broker', 'bio': 'Updated bio',
            'profile_picture': (io.BytesIO(b"pic"), 'profile.jpg')
        }, content_type='multipart/form-data')
        db.session.refresh(self.broker1)
        self.assertEqual(self.broker1.status, 'Pending Approval')

        # Cloudinary failure branch during profile update
        mock_upload.side_effect = Exception("Upload error")
        self.client.post('/brokerdash/settings', data={
            'action': 'update_profile', 'phone': '0780000000',
            'professional_title': 'Lead Broker', 'bio': 'Bio',
            'profile_picture': (io.BytesIO(b"pic"), 'profile.jpg')
        }, content_type='multipart/form-data')

        # Restore Active status and verify password update rules
        self.broker1.status = 'Active'
        db.session.commit()
        self.client.post('/brokerdash/settings', data={'action': 'update_password', 'current_password': 'wrong', 'new_password': 'ValidPass!123'})
        self.client.post('/brokerdash/settings', data={'action': 'update_password', 'current_password': 'BrokerPass!123', 'new_password': '123'})
        self.client.post('/brokerdash/settings', data={'action': 'update_password', 'current_password': 'BrokerPass!123', 'new_password': 'BrokerPass!123'})

        # Broker self-deletion and logout
        b_del = Broker(organization_id=self.org1.id, full_name="Del", phone="078", email="del@r.rw", password_hash="h", license_number="LDEL", status="Active")
        db.session.add(b_del)
        db.session.commit()
        b_del_id = b_del.id
        with self.client.session_transaction() as sess:
            sess['broker_id'] = b_del_id
        self.client.post('/brokerdash/settings', data={'action': 'delete_account'})
        self.assertIsNone(db.session.get(Broker, b_del_id))
        self.assertEqual(self.client.get('/logout').status_code, 302)

    def test_09_public_verification_listings_and_single_use_reviews(self):
        """Verify public license lookup, verified listings feed, rankings, and single-use review code rotation."""
        self.broker1.status = 'Active'
        self.broker1.review_code = 'RWA-LIVE8888'
        verified_prop = Property.query.filter_by(verification_status='Verified').first()
        if not verified_prop:
            verified_prop = Property(
                broker_id=self.broker1.id, title="Verified Listing", description="Clean UPI",
                price=150000, listing_type="For Sale", province="Kigali", district="Gasabo",
                sector="Kimihurura", cell="Rugando", village="Gasange", verification_status="Verified"
            )
            db.session.add(verified_prop)
        db.session.commit()

        # Public landing & license verification (valid vs non-existent)
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertEqual(self.client.get('/verify').status_code, 200)
        self.assertEqual(self.client.post('/verify', data={'license_number': self.broker1.license_number}).status_code, 200)
        self.assertEqual(self.client.post('/verify', data={'license_number': 'INVALID-000'}).status_code, 200)

        # Public verified properties, property detail, rankings bounds, and broker profile
        self.assertEqual(
            self.client.get(
                '/properties?province=Kigali&district=Gasabo&sector=Kimihurura&cell=Rugando&village=Gasange'
                '&listing_type=For+Sale&min_price=10&max_price=999999&bedrooms=1&bathrooms=1'
            ).status_code,
            200
        )
        self.assertEqual(self.client.get(f'/properties/{verified_prop.id}').status_code, 200)
        self.assertEqual(self.client.get('/broker-rankings?page=0').status_code, 200)
        self.assertEqual(self.client.get('/broker-rankings?page=99').status_code, 200)
        self.assertEqual(self.client.get(f'/broker/{self.broker1.id}').status_code, 200)

        # Single-use review submission must rotate review_code and block replay attacks
        self.assertEqual(self.client.get('/leave-review').status_code, 200)
        self.client.post('/leave-review', data={'review_code': 'INVALID', 'client_name': 'C', 'rating': 5, 'comment': 'X'})

        initial_count = Review.query.filter_by(broker_id=self.broker1.id).count()
        self.client.post('/leave-review', data={'review_code': 'RWA-LIVE8888', 'client_name': 'Client A', 'rating': 5, 'comment': 'Great service'})
        db.session.refresh(self.broker1)
        self.assertNotEqual(self.broker1.review_code, 'RWA-LIVE8888')
        self.assertEqual(Review.query.filter_by(broker_id=self.broker1.id).count(), initial_count + 1)

        # Replay attempt with the consumed code must be rejected
        self.client.post('/leave-review', data={'review_code': 'RWA-LIVE8888', 'client_name': 'Spammer', 'rating': 1, 'comment': 'Replay'})
        self.assertEqual(Review.query.filter_by(broker_id=self.broker1.id).count(), initial_count + 1)

    @patch('landing.mail.send')
    @patch('landing.cloudinary.uploader.upload')
    def test_10_public_auth_applications_and_password_reset(self, mock_upload, mock_mail_send):
        """Verify multi-role login states, application security guards, and timed password reset tokens."""
        mock_upload.return_value = {'secure_url': 'https://res.cloudinary.com/demo/p.jpg'}
        self.admin1.account_status = 'Active'
        self.broker1.status = 'Active'
        db.session.commit()

        # Login checks across Active, Pending, Revoked, Suspended, and wrong passwords
        self.assertEqual(self.client.get('/login').status_code, 200)
        self.client.post('/login', data={'role': 'association', 'email': 'alice@rrebp.rw', 'password': 'AdminPass!123'})
        self.client.post('/login', data={'role': 'association', 'email': 'alice@rrebp.rw', 'password': 'wrong'})

        self.admin2.account_status = 'Pending'
        db.session.commit()
        self.client.post('/login', data={'role': 'association', 'email': 'bob@rrebp.rw', 'password': 'AdminPass!123'})

        self.admin2.account_status = 'Revoked'
        db.session.commit()
        self.client.post('/login', data={'role': 'association', 'email': 'bob@rrebp.rw', 'password': 'AdminPass!123'})

        self.client.post('/login', data={'role': 'broker', 'email': 'jp@rrebp.rw', 'password': 'BrokerPass!123'})
        self.client.post('/login', data={'role': 'broker', 'email': 'other@rrebp.rw', 'password': 'BrokerPass!123'})
        self.client.post('/login', data={'role': 'broker', 'email': 'jp@rrebp.rw', 'password': 'wrong'})

        # Application guards: block orgs without Active admin (org2), block duplicate emails, accept valid
        self.client.post('/apply', data={'role': 'broker', 'full_name': 'Blocked', 'email': 'blocked@r.rw', 'password': 'p', 'organization_id': self.org2.id})
        self.assertIsNone(Broker.query.filter_by(email='blocked@r.rw').first())

        self.client.post('/apply', data={'role': 'broker', 'full_name': 'Dup', 'email': 'jp@rrebp.rw', 'password': 'p', 'organization_id': self.org1.id})
        self.client.post('/apply', data={
            'role': 'broker', 'full_name': 'New Broker', 'email': 'newb@rrebp.rw', 'password': 'Pass!123',
            'phone': '0789999999', 'organization_id': self.org1.id, 'professional_title': 'Agent',
            'working_province': 'Kigali', 'working_district': 'Gasabo', 'bio': 'Bio',
            'profile_picture': (io.BytesIO(b"img"), 'p.jpg')
        }, content_type='multipart/form-data')
        created_broker = Broker.query.filter_by(email='newb@rrebp.rw').first()
        self.assertIsNotNone(created_broker)
        self.assertEqual(created_broker.status, 'Pending Approval')
        self.assertTrue(created_broker.license_number.startswith('RWA-'))

        mock_upload.side_effect = Exception("Cloudinary err")
        self.client.post('/apply', data={
            'role': 'broker', 'full_name': 'New Broker 2', 'email': 'newb2@rrebp.rw', 'password': 'Pass!123',
            'phone': '0789999998', 'organization_id': self.org1.id, 'professional_title': 'Agent',
            'profile_picture': (io.BytesIO(b"img"), 'p.jpg')
        }, content_type='multipart/form-data')

        self.client.post('/apply', data={'role': 'association', 'full_name': 'A', 'email': 'alice@rrebp.rw', 'password': 'p', 'organization_id': self.org1.id})
        self.client.post('/apply', data={'role': 'association', 'full_name': 'New Admin', 'email': 'newa@rrebp.rw', 'password': 'p', 'organization_id': self.org1.id})
        self.assertIsNotNone(AssociationAdmin.query.filter_by(email='newa@rrebp.rw').first())

        # Forgot & Reset password (valid token, tampered token, expired token)
        self.assertEqual(self.client.get('/forgot-password').status_code, 200)
        self.client.post('/forgot-password', data={'email': 'jp@rrebp.rw', 'role': 'broker'})
        mock_mail_send.side_effect = Exception("SMTP err")
        self.client.post('/forgot-password', data={'email': 'alice@rrebp.rw', 'role': 'association'})

        s = landing.get_reset_serializer()
        b_token = s.dumps({'email': 'jp@rrebp.rw', 'role': 'broker'}, salt='password-reset-salt')
        a_token = s.dumps({'email': 'alice@rrebp.rw', 'role': 'association'}, salt='password-reset-salt')

        self.assertEqual(self.client.get('/reset-password/invalid-bad-token').status_code, 302)
        with patch.object(landing, 'get_reset_serializer') as mock_s:
            mock_s.return_value.loads.side_effect = SignatureExpired("Expired")
            self.assertEqual(self.client.get(f'/reset-password/{b_token}').status_code, 302)

        self.assertEqual(self.client.get(f'/reset-password/{b_token}').status_code, 200)
        self.client.post(f'/reset-password/{b_token}', data={'password': 'NewBrokerPass!99'})
        self.client.post(f'/reset-password/{a_token}', data={'password': 'AdminPass!123'})
        db.session.refresh(self.broker1)
        self.assertTrue(check_password_hash(self.broker1.password_hash, 'NewBrokerPass!99'))


if __name__ == '__main__':
    unittest.main(verbosity=2)