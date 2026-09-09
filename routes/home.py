"""
Page routes (HTML) for YT Downloader X Pro.

Renders the main SPA-style pages plus the static info pages
(About, Contact, DMCA). The sidebar / nav highlights the current
page through the `active_page` template variable.
"""
from flask import Blueprint, render_template

home_bp = Blueprint("home", __name__)


@home_bp.route("/")
def dashboard():
    return render_template("dashboard.html", active_page="dashboard")


@home_bp.route("/downloads")
def downloads():
    return render_template("downloads.html", active_page="downloads")


@home_bp.route("/history")
def history():
    return render_template("history.html", active_page="history")


@home_bp.route("/settings")
def settings():
    return render_template("settings.html", active_page="settings")


@home_bp.route("/about")
def about():
    return render_template("about.html", active_page="about")


@home_bp.route("/contact")
def contact():
    return render_template("contact.html", active_page="contact")


@home_bp.route("/dmca")
def dmca():
    return render_template("dmca.html", active_page="dmca")
