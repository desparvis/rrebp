from flask import Flask, redirect, url_for, render_template, session, flash, request, Blueprint

superadmin = Blueprint('superadmin', __name__, template_folder="templates", static_folder="static")

@superadmin.route('/spdash')
def spdash():
    return redirect()