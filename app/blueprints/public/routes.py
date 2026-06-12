from __future__ import annotations

from flask import render_template

from app.blueprints.public import bp


@bp.get("/")
def home():
    return render_template("public/home.html")
