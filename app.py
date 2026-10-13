from flask import Flask, render_template, redirect, url_for, session, flash, request
from landing import landing
from superadmin import superadmin
from models import db

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = 'sqlite:///rrebp.db'
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

app.register_blueprint(landing)
app.register_blueprint(superadmin)

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True)