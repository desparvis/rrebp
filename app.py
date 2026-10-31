from flask import Flask, render_template, redirect, url_for, session, flash, request
from landing import landing
from superadmin import superadmin
from association import association
from broker import broker_bp
from models import db
import os
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader
import cloudinary.api

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
app.config["SQLALCHEMY_DATABASE_URI"] = 'sqlite:///rrebp.db'
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

cloudinary.config(
    cloud_name = os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key = os.getenv('CLOUDINARY_API_KEY'),
    api_secret = os.getenv('CLOUDINARY_API_SECRET'),
    secure = True
)

# Initializing the database
db.init_app(app)

# Blueprint registration
app.register_blueprint(landing)
app.register_blueprint(superadmin)
app.register_blueprint(association)
app.register_blueprint(broker_bp)

# ==========================================
# GLOBAL ERROR HANDLERS
# ==========================================
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True)