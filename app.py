from config import CONFIG
from flask import Flask
from flask_cors import CORS
import os
from routes import register_blueprints

app = Flask(__name__)
CORS(app)

register_blueprints(app)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=CONFIG.DEBUG)

