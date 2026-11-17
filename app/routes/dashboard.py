from functools import wraps
from flask import Blueprint, flash, redirect, session, url_for
from flask import render_template
from ..extensions import db
from ..models import User

dashboard_bp = Blueprint("dashboard", __name__)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user_id = session.get("user_id")
        user = db.session.get(User, user_id) if user_id is not None else None
        if not user or not user.is_active:
            session.clear()
            flash("Please sign in to continue.", "error")
            return redirect(url_for("auth.login"))
        return view(user, *args, **kwargs)
    return wrapped


@dashboard_bp.route("/dashboard")
@login_required
def index(user):
    return render_template("dashboard.html", user=user)
