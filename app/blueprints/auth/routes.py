from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.blueprints.auth import bp
from app.forms import LoginForm
from app.services.auth import authenticate_user
from app.utils.urls import is_safe_local_url


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    form = LoginForm()
    next_url = request.args.get("next")

    if form.validate_on_submit():
        user = authenticate_user(form.email.data, form.password.data)
        if user:
            login_user(user, remember=form.remember_me.data)
            flash("Welcome back. You’re signed in.", "success")
            if is_safe_local_url(next_url):
                return redirect(next_url)
            return redirect(url_for("dashboard.index"))

        flash("That email or password didn’t match our records.", "danger")

    return render_template("auth/login.html", form=form, next_url=next_url)


@bp.post("/logout")
@login_required
def logout():
    logout_user()
    flash("You’ve been signed out.", "success")
    return redirect(url_for("public.home"))
