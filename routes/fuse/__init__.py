from flask import Blueprint

# This will be the main blueprint that aggregates all the smaller ones
fuse_bp = Blueprint("fuse", __name__, url_prefix="/fuse")

# Import and register the individual feature blueprints
from . import workflows, nodes, integrations, push, runs, versions

fuse_bp.register_blueprint(workflows.bp)
fuse_bp.register_blueprint(nodes.bp)
fuse_bp.register_blueprint(integrations.bp)
fuse_bp.register_blueprint(push.bp)
fuse_bp.register_blueprint(runs.bp)
fuse_bp.register_blueprint(versions.bp)
