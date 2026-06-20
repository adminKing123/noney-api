from flask import Blueprint

aura_rj_bp = Blueprint("aura_rj", __name__, url_prefix="/aura-rj")

# Import all sub-modules to register endpoints and logic under aura_rj_bp
from . import utils, config, routes
