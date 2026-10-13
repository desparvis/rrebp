from flask import Flask, redirect, url_for, render_template, session, flash, request, Blueprint

landing = Blueprint('landing', __name__, template_folder="templates", static_folder="static")

@landing.route('/')
def home():
    return render_template("index.html")

@landing.route('/verify')
def verify():
    return render_template("verify.html")