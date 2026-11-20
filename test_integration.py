import os
import smtplib
import unittest
from sqlalchemy import event, text

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from app import app
from models import (
    db, SuperAdmin, Organization, AssociationAdmin,
    Broker, Property, PropertyImage, Review, AuditLog
)
import cloudinary.api

WRITE_SQL_PREFIXES = (
    'INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER', 'TRUNCATE', 'CREATE', 'REPLACE'
)


def _enforce_readonly_sql(conn, cursor, statement, parameters, context, executemany):
    """Hard safety guard: immediately aborts if any SQL write statement is attempted."""
    cleaned = statement.lstrip()
    first_keyword = cleaned.split(None, 1)[0].upper() if cleaned else ''
    if first_keyword in WRITE_SQL_PREFIXES:
        raise RuntimeError(f"Blocked non-read SQL statement: {first_keyword}")


class TestRREBPLiveReadOnlyIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        cls.client = app.test_client()
        cls.ctx = app.app_context()
        cls.ctx.push()

        # Attach hard SQL write-blocker before running any test queries
        event.listen(db.engine, 'before_cursor_execute', _enforce_readonly_sql)

    @classmethod
    def tearDownClass(cls):
        event.remove(db.engine, 'before_cursor_execute', _enforce_readonly_sql)
        db.session.rollback()
        db.session.remove()
        cls.ctx.pop()

    def test_IT01_live_supabase_postgresql_and_orm_schema(self):
        """IT-01: Verify read-only connection and ORM schema queries on live Supabase PostgreSQL."""
        self.assertIn('postgresql', db.engine.dialect.name)
        ping_val = db.session.execute(text('SELECT 1')).scalar()
        self.assertEqual(ping_val, 1)

        for model in (SuperAdmin, Organization, AssociationAdmin, Broker, Property, PropertyImage, Review, AuditLog):
            count = model.query.count()
            self.assertGreaterEqual(count, 0)

    def test_IT02_flask_to_supabase_readonly_http_pipelines(self):
        """IT-02: Verify live HTTP read-only data flow from Flask routes to Supabase."""
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertEqual(self.client.get('/login').status_code, 200)
        self.assertEqual(
            self.client.get('/properties?province=Kigali&listing_type=For+Sale').status_code,
            200
        )
        self.assertEqual(self.client.get('/broker-rankings').status_code, 200)

        existing_broker = Broker.query.first()
        license_to_check = existing_broker.license_number if existing_broker else 'RWA-READONLY-CHECK'
        res_verify = self.client.post('/verify', data={'license_number': license_to_check})
        self.assertEqual(res_verify.status_code, 200)

    def test_IT03_live_cloudinary_media_api_ping(self):
        """IT-03: Verify live read-only authentication and reachability with Cloudinary REST API."""
        ping_response = cloudinary.api.ping()
        self.assertEqual(ping_response.get('status'), 'ok')

    def test_IT04_live_gmail_smtp_tls_handshake(self):
        """IT-04: Verify live Gmail SMTP STARTTLS encryption and credential login without sending mail."""
        mail_user = os.getenv('MAIL_USERNAME') or app.config.get('MAIL_USERNAME')
        mail_pass = os.getenv('MAIL_PASSWORD') or app.config.get('MAIL_PASSWORD')
        self.assertTrue(mail_user and mail_pass, "SMTP credentials missing in .env")

        server = smtplib.SMTP('smtp.gmail.com', 587, timeout=15)
        try:
            ehlo_code, _ = server.ehlo()
            self.assertEqual(ehlo_code, 250)
            tls_code, _ = server.starttls()
            self.assertEqual(tls_code, 220)
            auth_code, _ = server.login(mail_user, mail_pass)
            self.assertEqual(auth_code, 235)
        finally:
            server.quit()


if __name__ == '__main__':
    unittest.main(verbosity=2)