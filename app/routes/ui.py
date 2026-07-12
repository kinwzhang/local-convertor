from flask import Blueprint

bp = Blueprint("ui", __name__)


@bp.route("/")
def index():
    from flask import render_template

    return render_template("index.html")
