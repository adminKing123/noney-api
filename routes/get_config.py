from flask import Blueprint, jsonify, request
from middleware.auth import require_auth

get_config_bp = Blueprint('get_config', __name__)

all_models_data = {
    "AI_TYPES": [
        {
            "id": "TEXT",
            "name": "Conversa",
            "description": "Best for general-purpose use"
        },
        {
            "id": "CODE",
            "name": "Coder",
            "description": "Best for coding tasks"
        },
        {
            "id": "MEDIA_GENERATOR",
            "name": "Media Generator",
            "description": "Generate media content"
        },
        {
            "id": "HRMS_ASSISTANT_1_0",
            "name": "HRMS Assistant 1.0",
            "description": "@Synapses XTL"
        }
    ],
    "AI_DEFAULT_TYPE": {
        "id": "TEXT",
        "name": "Conversa",
        "description": "Best for general-purpose use"
    },
    "AI_MODELS": {
        "TEXT": {
            "models": [
                {
                    "id": "noney-1.0-twinkle-20241001",
                    "name": "AURA 1.0 Twinkle",
                    "google_search": False,
                    "active": "True",
                    "from": "NONEY",
                    "description": "High-end and smart."
                },
                {
                    "id": "noney-2.0-twinkle-20241001",
                    "name": "AURA 2.0 Twinkle",
                    "google_search": False,
                    "active": "True",
                    "from": "NONEY",
                    "description": "Next-gen improved."
                }
            ],
            "default_model": {
                "id": "noney-1.0-twinkle-20241001",
                "name": "AURA 1.0 Twinkle",
                "google_search": False,
                "active": "True",
                "from": "NONEY",
                "description": "High-end and smart."
            }
        },
        "CODE": {
            "models": [
                {
                    "id": "noney-code-gen-20241001",
                    "name": "AURA Code Gen1.0",
                    "google_search": False,
                    "active": "True",
                    "from": "NONEY",
                    "description": "Powerful code generation model."
                },
                {
                    "id": "noney-code-gen-pro-20241001",
                    "name": "AURA Code Gen Pro",
                    "google_search": False,
                    "active": "True",
                    "from": "NONEY",
                    "description": "Advanced code generation."
                }
            ],
            "default_model": {
                "id": "noney-code-gen-20241001",
                "name": "AURA Code Gen1.0",
                "google_search": False,
                "active": "True",
                "from": "NONEY",
                "description": "Powerful code generation model."
            }
        },
        "MEDIA_GENERATOR": {
            "models": [
                {
                    "id": "noney-image-gen-20241001",
                    "name": "AURA Image Gen1.0",
                    "google_search": False,
                    "active": "True",
                    "from": "NONEY",
                    "description": "Best for Image Generation."
                }
            ],
            "default_model": {
                "id": "noney-image-gen-20241001",
                "name": "AURA Image Gen1.0",
                "google_search": False,
                "active": "True",
                "from": "NONEY",
                "description": "Best for Image Generation."
            }
        },
        "HRMS_ASSISTANT_1_0": {
            "models": [
                {
                    "id": "noney-hrms-assistant-20241001",
                    "name": "HRMS Assistant 1.0",
                    "google_search": False,
                    "active": "True",
                    "from": "NONEY",
                    "description": "Easy-going and quick.",
                },
                {
                    "id": "noney-hrms-assistant-pro-20241001",
                    "name": "HRMS Assistant Pro",
                    "google_search": False,
                    "active": "True",
                    "from": "NONEY",
                    "description": "Heavy-duty but accurate.",
                },
            ],
            "default_model": {
                "id": "noney-hrms-assistant-20241001",
                "name": "HRMS Assistant 1.0",
                "google_search": False,
                "active": "True",
                "from": "NONEY",
                "description": "Easy-going and quick.",
            },
        },
    }
}

data = {
    "AI_TYPES": [
        {
            "id": "TEXT",
            "name": "Conversa",
            "description": "Best for general-purpose use"
        },
        {
            "id": "CODE",
            "name": "Coder",
            "description": "Best for coding tasks"
        },
        {
            "id": "MEDIA_GENERATOR",
            "name": "Media Generator",
            "description": "Generate media content"
        }
    ],
    "AI_DEFAULT_TYPE": {
        "id": "TEXT",
        "name": "Conversa",
        "description": "Best for general-purpose use"
    },
    "AI_MODELS": {
        "TEXT": {
            "models": [
                {
                    "id": "noney-1.0-twinkle-20241001",
                    "name": "AURA 1.0 Twinkle",
                    "google_search": False,
                    "active": "True",
                    "from": "NONEY",
                    "description": "High-end and smart."
                },
                {
                    "id": "noney-2.0-twinkle-20241001",
                    "name": "AURA 2.0 Twinkle",
                    "google_search": False,
                    "active": "True",
                    "from": "NONEY",
                    "description": "Next-gen improved."
                }
            ],
            "default_model": {
                "id": "noney-1.0-twinkle-20241001",
                "name": "AURA 1.0 Twinkle",
                "google_search": False,
                "active": "True",
                "from": "NONEY",
                "description": "High-end and smart."
            }
        },
        "CODE": {
            "models": [
                {
                    "id": "noney-code-gen-20241001",
                    "name": "AURA Code Gen1.0",
                    "google_search": False,
                    "active": "True",
                    "from": "NONEY",
                    "description": "Powerful code generation model."
                },
                {
                    "id": "noney-code-gen-pro-20241001",
                    "name": "AURA Code Gen Pro",
                    "google_search": False,
                    "active": "True",
                    "from": "NONEY",
                    "description": "Advanced code generation."
                }
            ],
            "default_model": {
                "id": "noney-code-gen-20241001",
                "name": "AURA Code Gen1.0",
                "google_search": False,
                "active": "True",
                "from": "NONEY",
                "description": "Powerful code generation model."
            }
        },
        "MEDIA_GENERATOR": {
            "models": [
                {
                    "id": "noney-image-gen-20241001",
                    "name": "AURA Image Gen1.0",
                    "google_search": False,
                    "active": "True",
                    "from": "NONEY",
                    "description": "Best for Image Generation."
                }
            ],
            "default_model": {
                "id": "noney-image-gen-20241001",
                "name": "AURA Image Gen1.0",
                "google_search": False,
                "active": "True",
                "from": "NONEY",
                "description": "Best for Image Generation."
            }
        },
    }
}

@get_config_bp.route("/get-config", methods=["GET"])
@require_auth
def get_config():
    if getattr(request, "user", {}).get("email") == "h.narwariya@thesynapses.com":
        return jsonify(all_models_data), 200
    return jsonify(data), 200
