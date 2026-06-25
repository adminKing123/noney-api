from flask import Blueprint, jsonify, request
from middleware.auth import require_auth

bp = Blueprint("fuse_nodes", __name__)

# ─── Node definitions (static, no DB needed) ─────────────────────────────────

STARTER_NODES = [
    {
        "type": "schedule",
        "label": "On a Schedule",
        "icon": "TbCalendarTime",
        "description": "Start at a set date and time. Have it run once or repeat on a schedule.",
        "config_form": {
            "presets": [
                {"label": "Monday at 8 AM",  "values": {"date": "next-monday", "time": "08:00", "repeat": "weekly_monday", "ends": "1y"}},
                {"label": "Weekdays at 8 AM", "values": {"date": "today",       "time": "08:00", "repeat": "weekdays",      "ends": "1y"}},
                {"label": "In 5 minutes",     "values": {"date": "today",       "time": "+5min", "repeat": "none",          "ends": "1y"}},
            ],
            "sections": [
                {
                    "title": "Start date and time",
                    "layout": "grid-2",
                    "fields": [
                        {"key": "date", "label": "Date", "type": "date", "required": True, "hint": "MM/DD/YYYY"},
                        {"key": "time", "label": "Time", "type": "time", "required": True},
                    ],
                },
                {
                    "fields": [
                        {
                            "key": "repeat", "label": "Repeat", "type": "select", "required": True,
                            "options": [
                                {"label": "Does not repeat",       "value": "none"},
                                {"label": "Hourly",                "value": "hourly"},
                                {"label": "Daily",                 "value": "daily"},
                                {"label": "Weekly on Monday",      "value": "weekly_monday"},
                                {"label": "Weekdays (Mon–Fri)", "value": "weekdays"},
                                {"label": "Monthly",               "value": "monthly"},
                                {"label": "Annually",              "value": "annually"},
                            ],
                            "after_hint": "For daily and less frequent repeats, runs start within 3 minutes of the set time",
                        },
                        {
                            "key": "ends", "label": "Ends", "type": "select",
                            "options": [
                                {"label": "1 year",  "value": "1y"},
                                {"label": "6 months","value": "6m"},
                                {"label": "3 months","value": "3m"},
                                {"label": "1 month", "value": "1m"},
                                {"label": "Never",   "value": "never"},
                            ],
                        },
                        {"key": "timezone", "label": "Time zone", "type": "timezone_select", "required": True},
                    ],
                },
            ],
        },
    },
    {
        "type": "webhook",
        "label": "On Webhook",
        "icon": "TbWebhook",
        "description": "Start the workflow whenever an HTTP request hits the generated webhook URL.",
        "config_form": {
            "sections": [
                {
                    "title": "Endpoint",
                    "fields": [
                        {
                            "key": "method", "label": "HTTP Method", "type": "select", "required": True,
                            "options": [
                                {"label": "POST",  "value": "POST"},
                                {"label": "GET",   "value": "GET"},
                                {"label": "PUT",   "value": "PUT"},
                                {"label": "PATCH", "value": "PATCH"},
                            ],
                            "hint": "Only requests matching this method will trigger the workflow",
                        },
                    ],
                },
                {
                    "title": "Security",
                    "fields": [
                        {
                            "key": "auth_type", "label": "Authentication", "type": "select",
                            "options": [
                                {"label": "None",             "value": "none"},
                                {"label": "Bearer token",     "value": "bearer"},
                                {"label": "Basic auth",       "value": "basic"},
                                {"label": "HMAC signature",   "value": "hmac"},
                            ],
                            "hint": "How the webhook verifies that the request is from a trusted sender",
                        },
                        {"key": "secret", "label": "Secret / Token", "type": "text", "placeholder": "Paste your secret here", "hint": "Used to verify the HMAC signature or as the expected bearer token"},
                    ],
                },
                {
                    "title": "Response",
                    "fields": [
                        {"key": "response_code", "label": "Status Code", "type": "number", "placeholder": "200", "hint": "HTTP status returned immediately to the caller"},
                    ],
                },
                {
                    "title": "Body Schema",
                    "fields": [
                        {
                            "key": "body_schema", "label": "Incoming Body Fields", "type": "body_builder",
                            "hint": "Define the fields you expect in the webhook request body. These become variables you can reference in downstream nodes using {{webhook.body.fieldName}}.",
                        },
                    ],
                },
            ],
        },
    },
]

ACTION_NODES = [
    {
        "type": "get_notified",
        "label": "Get Notified",
        "icon": "TbBell",
        "section": "Notifications",
        "description": "Send a web push notification to yourself when this workflow step is reached.",
        "config_form": {
            "sections": [
                {
                    "title": "Content",
                    "fields": [
                        {"key": "title",     "label": "Title",            "type": "variable_text",     "placeholder": "e.g. Your report is ready",        "required": True, "hint": "Short headline shown in bold. Use @ to insert a variable."},
                        {"key": "body",      "label": "Body",             "type": "variable_textarea", "placeholder": "e.g. The weekly sales report has been generated.", "required": True, "hint": "Main notification text. Use @ to insert a variable."},
                        {"key": "icon_url",  "label": "Icon URL",         "type": "variable_text",     "placeholder": "https://example.com/icon-192.png",  "hint": "Square image (192x192 px recommended) shown beside the notification"},
                        {"key": "image_url", "label": "Banner Image URL", "type": "variable_text",     "placeholder": "https://example.com/banner.png",    "hint": "Large image displayed below the body on supported browsers"},
                    ],
                },
                {
                    "title": "Action",
                    "fields": [
                        {"key": "click_url", "label": "Click URL",    "type": "variable_text", "placeholder": "https://app.example.com/dashboard", "hint": "Page to open when the notification is clicked; defaults to the app URL"},
                        {"key": "cta_label", "label": "Button Label", "type": "variable_text", "placeholder": "e.g. View Report",                  "hint": "Optional action button shown inside the notification"},
                    ],
                },
                {
                    "title": "Options",
                    "layout": "grid-2",
                    "fields": [
                        {
                            "key": "require_interaction", "label": "Require Interaction", "type": "select",
                            "options": [
                                {"label": "No — dismiss automatically", "value": "false"},
                                {"label": "Yes — stay until dismissed",  "value": "true"},
                            ],
                            "hint": "Keep the notification visible until the user actively dismisses it",
                        },
                        {"key": "ttl_seconds", "label": "Time to Live (sec)", "type": "number", "placeholder": "86400", "hint": "How long the browser retries delivery if you are offline"},
                    ],
                },
            ],
        },
    },
    {
        "type": "send_gmail",
        "label": "Send Gmail",
        "icon": "SiGmail",
        "section": "Notifications",
        "required_integration": "gmail",
        "description": "Send an email using your configured Gmail integration.",
        "config_form": {
            "sections": [
                {
                    "title": "Email Details",
                    "fields": [
                        {"key": "to", "label": "To", "type": "variable_text", "placeholder": "recipient@example.com", "required": True, "hint": "Email address to send to. Use @ to insert a variable."},
                        {"key": "subject", "label": "Subject", "type": "variable_text", "placeholder": "Email subject", "required": True, "hint": "Subject of the email. Use @ to insert a variable."},
                        {"key": "body", "label": "Body", "type": "variable_textarea", "placeholder": "Email body content", "required": True, "hint": "Main body of the email. Use @ to insert a variable."},
                    ],
                },
            ],
        },
    },
    {
        "type": "if_else",
        "label": "Check If",
        "icon": "TbGitBranch",
        "section": "Logic",
        "description": "Branch the workflow based on a condition. The True path runs when the condition passes; the False path runs otherwise.",
        "config_form": {
            "sections": [
                {
                    "title": "Condition",
                    "fields": [
                        {
                            "key": "condition", "label": "Condition", "type": "condition_builder",
                            "hint": "Add one or more conditions. Use the AND / OR toggle between rows to control how they combine. Connect the True and False handles on the node to route each branch.",
                        },
                    ],
                },
            ],
        },
    },
    {
        "type": "ai_structured_output",
        "label": "AI Structured Output",
        "icon": "TbSparkles",
        "section": "AI",
        "description": "Generate structured output from a prompt using AI. Define the expected JSON schema with descriptions for the AI to follow.",
        "config_form": {
            "sections": [
                {
                    "title": "Prompt",
                    "fields": [
                        {
                            "key": "prompt", 
                            "label": "Prompt", 
                            "type": "variable_textarea", 
                            "placeholder": "Extract information from the provided text...", 
                            "required": True,
                            "hint": "Instructions for the AI. Use @ to insert variables."
                        },
                    ],
                },
                {
                    "title": "Output Schema",
                    "fields": [
                        {
                            "key": "output_schema", 
                            "label": "JSON Schema", 
                            "type": "body_builder", 
                            "showDescription": True,
                            "showEnum": True,
                            "hint": "Define the structure and properties you expect the AI to return. Provide descriptions to help the AI understand the purpose of each field."
                        },
                    ],
                },
            ],
        },
    },
    {
        "type": "http_request",
        "label": "HTTP Request",
        "icon": "TbWorldWww",
        "section": "Network",
        "description": "Make an outbound HTTP request to any URL. Map response fields to variables for use in downstream nodes.",
        "config_form": {
            "sections": [
                {
                    "title": "Endpoint",
                    "fields": [
                        {
                            "key": "method",
                            "label": "Method",
                            "type": "select",
                            "options": [
                                {"label": "GET",    "value": "GET"},
                                {"label": "POST",   "value": "POST"},
                                {"label": "PUT",    "value": "PUT"},
                                {"label": "PATCH",  "value": "PATCH"},
                                {"label": "DELETE", "value": "DELETE"},
                            ],
                        },
                        {
                            "key": "url",
                            "label": "URL",
                            "type": "variable_text",
                            "placeholder": "https://api.example.com/endpoint",
                            "required": True,
                            "hint": "The full URL to request. Use @ to insert a variable.",
                        },
                    ],
                },
                {
                    "title": "Query Parameters",
                    "fields": [
                        {
                            "key": "query_params",
                            "label": "Parameters",
                            "type": "json_value_builder",
                            "hint": "Appended to the URL as ?key=value pairs. Use @ to insert variables into values.",
                        },
                    ],
                },
                {
                    "title": "Headers",
                    "fields": [
                        {
                            "key": "headers",
                            "label": "Headers",
                            "type": "json_value_builder",
                            "hint": "HTTP headers sent with the request (e.g. Authorization, Content-Type). Use @ to insert variables.",
                        },
                    ],
                },
                {
                    "title": "Request Body",
                    "fields": [
                        {
                            "key": "payload",
                            "label": "Body Fields",
                            "type": "json_value_builder",
                            "hint": "Define the JSON body to send (POST, PUT, PATCH). Set key, type and value for each field — use @ to insert variables.",
                        },
                    ],
                },
                {
                    "title": "Response",
                    "fields": [
                        {
                            "key": "response_schema",
                            "label": "Expected Response Fields",
                            "type": "body_builder",
                            "hint": "Declare the fields you expect in the JSON response. Each top-level field becomes a variable: {{node_id.fieldName}}.",
                        },
                        {
                            "key": "timeout",
                            "label": "Timeout (seconds)",
                            "type": "number",
                            "placeholder": "30",
                            "hint": "Maximum seconds to wait for a response before the node fails.",
                        },
                    ],
                },
            ],
        },
    },
]


@bp.route("/nodes/starter", methods=["GET"])
@require_auth
def get_starter_nodes():
    """GET /fuse/nodes/starter — returns all starter node definitions."""
    return jsonify(STARTER_NODES)


from db import db

@bp.route("/nodes/actions", methods=["GET"])
@require_auth
def get_action_nodes():
    """GET /fuse/nodes/actions — returns action node definitions. Only returns nodes requiring integrations if they are configured."""
    user_id = request.user["uid"]
    user_integrations = db.integration.get_all_integrations(user_id)
    
    filtered_nodes = []
    for node in ACTION_NODES:
        required_integration = node.get("required_integration")
        if required_integration:
            integration_data = user_integrations.get(required_integration)
            if not integration_data or not integration_data.get("configured"):
                continue
        filtered_nodes.append(node)
        
    return jsonify(filtered_nodes)
