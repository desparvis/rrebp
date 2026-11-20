import os
import unittest
from unittest.mock import patch

os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['SECRET_KEY'] = 'rrebp-validation-secret-key'

import flask
from jinja2 import TemplateNotFound
from werkzeug.security import generate_password_hash

import app as rrebp_app
from app import app
from models import db, SuperAdmin, Organization, AssociationAdmin, Broker, Property, Review
import landing
import association
import superadmin
import broker

_real_render = flask.render_template


def _safe_render(template_name, **kwargs):
    try:
        return _real_render(template_name, **kwargs)
    except TemplateNotFound:
        return f"Rendered {template_name}"


class TestRREBPValidation(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'rrebp-validation-secret-key'
        cls.client = app.test_client()
        cls.ctx = app.app_context()
        cls.ctx.push()
        db.create_all()

        cls.patches = [
            patch.object(rrebp_app, 'render_template', side_effect=_safe_render),
            patch.object(landing, 'render_template', side_effect=_safe_render),
            patch.object(association, 'render_template', side_effect=_safe_render),
            patch.object(broker, 'render_template', side_effect=_safe_render),
            patch.object(superadmin, 'render_template', side_effect=_safe_render),
        ]
        for p in cls.patches:
            p.start()

        cls.sa = SuperAdmin(
            email="superadmin@rrebp.rw",
            password_hash=generate_password_hash("SuperPass!123")
        )
        db.session.add(cls.sa)
        db.session.commit()

    @classmethod
    def tearDownClass(cls):
        for p in cls.patches:
            p.stop()
        db.session.remove()
        db.drop_all()
        cls.ctx.pop()

    def test_VT01_org_and_admin_onboarding(self):
        """VT-01 (RO2): Super Admin registers organization and activates Association Admin."""
        with self.client.session_transaction() as sess:
            sess['superadmin_id'] = self.sa.id

        self.client.post('/spdash/organizations/new', data={
            'name': 'Rwanda Real Estate Association',
            'email': 'info@rwareb.rw',
            'phone': '0788000001',
            'address': 'Kigali'
        })
        org = Organization.query.filter_by(email='info@rwareb.rw').first()
        self.assertIsNotNone(org)
        self.assertEqual(org.status, 'Active')

        self.client.post('/apply', data={
            'role': 'association',
            'full_name': 'Alice Umutoni',
            'email': 'alice@rwareb.rw',
            'password': 'AdminPass!123',
            'organization_id': org.id
        })
        admin = AssociationAdmin.query.filter_by(email='alice@rwareb.rw').first()
        self.assertEqual(admin.account_status, 'Pending')

        self.client.post(f'/spdash/admins/{admin.id}/approve')
        db.session.refresh(admin)
        self.assertEqual(admin.account_status, 'Active')

    def test_VT02_broker_vetting_and_hash_anchoring(self):
        """VT-02 (RO2): Broker applies, Association Admin vets and anchors Sepolia hash."""
        org = Organization.query.filter_by(email='info@rwareb.rw').first()
        admin = AssociationAdmin.query.filter_by(email='alice@rwareb.rw').first()

        self.client.post('/apply', data={
            'role': 'broker',
            'full_name': 'Jean Paul Habimana',
            'email': 'jp@broker.rw',
            'password': 'BrokerPass!123',
            'phone': '0788111222',
            'organization_id': org.id,
            'professional_title': 'Licensed Property Broker',
            'working_province': 'Kigali',
            'working_district': 'Gasabo',
            'bio': 'Residential broker'
        })
        brk = Broker.query.filter_by(email='jp@broker.rw').first()
        self.assertEqual(brk.status, 'Pending Approval')

        with self.client.session_transaction() as sess:
            sess['assoc_admin_id'] = admin.id

        self.client.post(f'/assocdash/brokers/{brk.id}/approve')
        db.session.refresh(brk)
        self.assertEqual(brk.status, 'Pending Registration')

        self.client.post(
            f'/assocdash/brokers/{brk.id}/verify',
            json={'broker_hash': '0x7c9fa12b88d4e001'}
        )
        db.session.refresh(brk)
        self.assertEqual(brk.status, 'Active')
        self.assertIsNotNone(brk.review_code)

    def test_VT03_public_license_verification(self):
        """VT-03 (RO3): Public lookup returns verified broker and rejects fake license."""
        brk = Broker.query.filter_by(email='jp@broker.rw').first()

        with patch.object(landing, 'render_template', wraps=_safe_render) as mock_render, \
             patch.object(landing, 'flash', wraps=landing.flash) as mock_flash:
            res_valid = self.client.post('/verify', data={'license_number': brk.license_number})
            self.assertEqual(res_valid.status_code, 200)
            self.assertEqual(mock_render.call_args.kwargs.get('broker').id, brk.id)

            res_fake = self.client.post('/verify', data={'license_number': 'RWA-2026-0000000000'})
            self.assertEqual(res_fake.status_code, 200)
            self.assertIsNone(mock_render.call_args.kwargs.get('broker'))
            mock_flash.assert_called_with("No broker found matching this license number.", "error")

    def test_VT04_upi_property_moderation_gate(self):
        """VT-04 (RO3): UPI property stays hidden as Pending until Association Admin approves."""
        brk = Broker.query.filter_by(email='jp@broker.rw').first()
        admin = AssociationAdmin.query.filter_by(email='alice@rwareb.rw').first()

        with self.client.session_transaction() as sess:
            sess['broker_id'] = brk.id

        self.client.post('/my-properties/add', data={
            'title': 'Kimihurura Apartment',
            'description': '3-bedroom unit',
            'price': '180000',
            'listing_type': 'For Sale',
            'province': 'Kigali',
            'district': 'Gasabo',
            'sector': 'Kimihurura',
            'cell': 'Rugando',
            'village': 'Gasange',
            'bedrooms': '3',
            'bathrooms': '2',
            'upi_number': '1/01/05/02/4091'
        })
        prop = Property.query.filter_by(upi_number='1/01/05/02/4091').first()
        self.assertEqual(prop.verification_status, 'Pending')
        self.assertEqual(self.client.get(f'/properties/{prop.id}').status_code, 404)

        with self.client.session_transaction() as sess:
            sess['assoc_admin_id'] = admin.id
        self.client.post(f'/assocdash/properties/{prop.id}/approve')
        db.session.refresh(prop)
        self.assertEqual(prop.verification_status, 'Verified')
        self.assertEqual(self.client.get(f'/properties/{prop.id}').status_code, 200)

    def test_VT05_single_use_review_code_rotation(self):
        """VT-05 (RO3): Review submission rotates single-use code and blocks replay spam."""
        brk = Broker.query.filter_by(email='jp@broker.rw').first()
        initial_code = brk.review_code

        self.client.post('/leave-review', data={
            'review_code': initial_code,
            'client_name': 'Eric Mugisha',
            'rating': 5,
            'comment': 'Verified license and smooth transaction.'
        })
        db.session.refresh(brk)
        self.assertNotEqual(brk.review_code, initial_code)
        self.assertEqual(Review.query.filter_by(broker_id=brk.id).count(), 1)

        self.client.post('/leave-review', data={
            'review_code': initial_code,
            'client_name': 'Spam Bot',
            'rating': 1,
            'comment': 'Duplicate replay attempt'
        })
        self.assertEqual(Review.query.filter_by(broker_id=brk.id).count(), 1)

    def test_VT06_anti_tamper_profile_status_reset(self):
        """VT-06 (RO2): Editing an Active broker profile resets status to Pending Approval."""
        brk = Broker.query.filter_by(email='jp@broker.rw').first()
        self.assertEqual(brk.status, 'Active')

        with self.client.session_transaction() as sess:
            sess['broker_id'] = brk.id

        self.client.post('/brokerdash/settings', data={
            'action': 'update_profile',
            'phone': '0788999000',
            'professional_title': 'Senior Broker',
            'bio': 'Updated profile details'
        })
        db.session.refresh(brk)
        self.assertEqual(brk.status, 'Pending Approval')


if __name__ == '__main__':
    unittest.main(verbosity=2)