from flask import Flask, render_template, redirect, url_for, session, flash, request
from landing import landing
from superadmin import superadmin
from association import association
from models import db
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
app.config["SQLALCHEMY_DATABASE_URI"] = 'sqlite:///rrebp.db'
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Initializing the database
db.init_app(app)

# Blueprint registration
app.register_blueprint(landing)
app.register_blueprint(superadmin)
app.register_blueprint(association)

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True)