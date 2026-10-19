from flask import Blueprint

comet_rj_bp = Blueprint("comet_rj", __name__, url_prefix="/comet-rj")

from . import utils, config, routes
