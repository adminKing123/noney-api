from .generation import generation_bp
from .chats import chats_bp
from .health import health_bp
from .files import files_bp
from .comet_rj import comet_rj_bp
from .get_config import get_config_bp
from .hrms import hrms_bp
from .tts import tts_bp
from .stt import stt_bp
from .fuse import fuse_bp

def register_blueprints(app):
    app.register_blueprint(generation_bp)
    app.register_blueprint(chats_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(comet_rj_bp)
    app.register_blueprint(get_config_bp)
    app.register_blueprint(hrms_bp)
    app.register_blueprint(tts_bp)
    app.register_blueprint(stt_bp)
    app.register_blueprint(fuse_bp)
