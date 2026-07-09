from __future__ import annotations

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.blueprints.auth import bp
from app.forms import LoginForm
from app.services.auth import authenticate_user
from app.services.audit import record_audit_event
from app.utils.rate_limit import client_key, is_limited
from app.utils.urls import is_safe_local_url


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    form = LoginForm()
    next_url = request.args.get("next")

    if form.validate_on_submit():
        if is_limited(
            client_key("login", form.email.data),
            limit=current_app.config.get("LOGIN_RATE_LIMIT_ATTEMPTS", 5),
            window_seconds=current_app.config.get("LOGIN_RATE_LIMIT_WINDOW_SECONDS", 60),
        ):
            record_audit_event(
                action="user.login_rate_limited",
                entity_type="user",
                entity_id=form.email.data,
                metadata={"email": form.email.data},
                source_module=__name__,
                actor_type="anonymous",
            )
            return "Too many login attempts. Try again shortly.", 429
        user = authenticate_user(form.email.data, form.password.data)
        if user:
            login_user(user, remember=form.remember_me.data)
            record_audit_event(
                action="user.logged_in",
                entity_type="user",
                entity_id=user.id,
                after_state={"email": user.email},
                source_module=__name__,
                actor_id=user.id,
            )
            flash("Welcome back. You’re signed in.", "success")
            if is_safe_local_url(next_url):
                return redirect(next_url)
            return redirect(url_for("dashboard.index"))

        record_audit_event(
            action="user.login_failed",
            entity_type="user",
            entity_id=form.email.data,
            metadata={"email": form.email.data},
            source_module=__name__,
            actor_type="anonymous",
        )
        flash("That email or password didn’t match our records.", "danger")

    return render_template("auth/login.html", form=form, next_url=next_url)


@bp.post("/logout")
@login_required
def logout():
    user_id = current_user.id
    email = current_user.email
    logout_user()
    record_audit_event(
        action="user.logged_out",
        entity_type="user",
        entity_id=user_id,
        after_state={"email": email},
        source_module=__name__,
        actor_id=user_id,
    )
    flash("You’ve been signed out.", "success")
    return redirect(url_for("public.home"))
