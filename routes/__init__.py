from .generation import generation_bp
from .chats import chats_bp
from .health import health_bp
from .connected_apps import connected_apps_bp

def register_blueprints(app):
    app.register_blueprint(generation_bp)
    app.register_blueprint(chats_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(connected_apps_bp)
