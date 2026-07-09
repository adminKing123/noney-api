"""
fuse/node_definitions.py
========================
Static Fuse node type definitions (starter + action nodes).

Single source of truth used by:
  - routes/fuse/nodes.py  (API endpoints)
  - fuse/node_catalog.py  (AI workflow generation)

To add a new node type, append its definition here and register a handler in
fuse/nodes/__init__.py.
"""

STARTER_NODES = [
    {
        "type": "schedule",
        "label": "On a Schedule",
        "icon": "TbCalendarTime",
        "section": "General",
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
                                {"label": "Weekdays (Mon - Fri)", "value": "weekdays"},
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
        "type": "webex_message",
        "label": "On Message",
        "icon": "SiWebex",
        "section": "Webex",
        "required_integration": "webex",
        "description": "Start the workflow when a new Webex message is received in a space or direct chat.",
        "defaults": {
            "filter_type": "all",
        },
        "config_form": {
            "sections": [
                {
                    "title": "Message source",
                    "fields": [
                        {
                            "key": "filter_type",
                            "label": "Listen to",
                            "type": "select",
                            "required": True,
                            "options": [
                                {"label": "All spaces & direct messages", "value": "all"},
                                {"label": "A specific space (room)",       "value": "room"},
                                {"label": "Direct messages only",           "value": "direct"},
                            ],
                            "hint": "Choose which Webex conversations should trigger this workflow",
                        },
                        {
                            "key": "room_id",
                            "label": "Space / Room",
                            "type": "webex_room_select",
                            "required": True,
                            "visibleWhen": {"key": "filter_type", "value": "room"},
                            "hint": "Select the Webex space to listen to. Spaces are loaded from your connected account.",
                        },
                    ],
                },
                {
                    "title": "Filters",
                    "fields": [
                        {
                            "key": "mentions_only",
                            "label": "Mentions only",
                            "type": "checkbox",
                            "hint": "Only trigger when your Webex account or bot is @mentioned in the message",
                        },
                        {
                            "key": "ignore_own_messages",
                            "label": "Ignore own messages",
                            "type": "checkbox",
                            "hint": "Skip messages sent by the connected Webex account (recommended)",
                        },
                        {
                            "key": "include_message_body",
                            "label": "Include message body",
                            "type": "checkbox",
                            "hint": "When enabled, the full message text is included in trigger data. When off, only sender and room details are provided (Webex webhooks do not include the message text itself).",
                        },
                    ],
                },
            ],
        },
    },
    {
        "type": "webhook",
        "label": "On Webhook",
        "icon": "TbWebhook",
        "section": "General",
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
                                {"label": "No dismiss automatically", "value": "false"},
                                {"label": "Yes stay until dismissed",  "value": "true"},
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
        "type": "send_webex_message",
        "label": "Send Message",
        "icon": "SiWebex",
        "section": "Webex",
        "required_integration": "webex",
        "description": "Send a message to a Webex space or person using your connected Webex account.",
        "defaults": {
            "send_to": "room",
            "destination_source": "pick",
        },
        "config_form": {
            "sections": [
                {
                    "title": "Destination",
                    "fields": [
                        {
                            "key": "send_to",
                            "label": "Send to",
                            "type": "select",
                            "required": True,
                            "options": [
                                {"label": "Space / Room",   "value": "room"},
                                {"label": "Person email",   "value": "person_email"},
                                {"label": "Person ID",      "value": "person_id"},
                            ],
                            "hint": "How to identify the recipient",
                        },
                        {
                            "key": "destination_source",
                            "label": "Destination source",
                            "type": "select",
                            "required": True,
                            "options": [
                                {"label": "Pick from Webex",  "value": "pick"},
                                {"label": "Enter manually",   "value": "manual"},
                            ],
                            "hint": "Choose from your Webex account or type a value (supports @ variables when manual)",
                        },
                        {
                            "key": "destination_pick",
                            "label": "Space",
                            "type": "webex_room_select",
                            "required": True,
                            "visibleWhen": [
                                {"key": "send_to", "value": "room"},
                                {"key": "destination_source", "value": "pick"},
                            ],
                            "hint": "Select a Webex space or direct chat",
                        },
                        {
                            "key": "destination_pick",
                            "label": "Person",
                            "type": "webex_person_select",
                            "personValue": "email",
                            "required": True,
                            "visibleWhen": [
                                {"key": "send_to", "value": "person_email"},
                                {"key": "destination_source", "value": "pick"},
                            ],
                            "hint": "Select a person by email",
                        },
                        {
                            "key": "destination_pick",
                            "label": "Person",
                            "type": "webex_person_select",
                            "personValue": "id",
                            "required": True,
                            "visibleWhen": [
                                {"key": "send_to", "value": "person_id"},
                                {"key": "destination_source", "value": "pick"},
                            ],
                            "hint": "Select a person by ID",
                        },
                        {
                            "key": "destination",
                            "label": "Space / Room ID",
                            "type": "variable_text",
                            "placeholder": "Room ID or {{starter.room_id}}",
                            "required": True,
                            "visibleWhen": [
                                {"key": "send_to", "value": "room"},
                                {"key": "destination_source", "value": "manual"},
                            ],
                            "hint": "Webex room ID. Use @ to insert a variable.",
                        },
                        {
                            "key": "destination",
                            "label": "Person email",
                            "type": "variable_text",
                            "placeholder": "name@company.com",
                            "required": True,
                            "visibleWhen": [
                                {"key": "send_to", "value": "person_email"},
                                {"key": "destination_source", "value": "manual"},
                            ],
                            "hint": "Email address to message. Use @ to insert a variable.",
                        },
                        {
                            "key": "destination",
                            "label": "Person ID",
                            "type": "variable_text",
                            "placeholder": "Y2lzY29zcGFyazovL3VzL1BFUlNPTi9...",
                            "required": True,
                            "visibleWhen": [
                                {"key": "send_to", "value": "person_id"},
                                {"key": "destination_source", "value": "manual"},
                            ],
                            "hint": "Webex person ID. Use @ to insert a variable.",
                        },
                    ],
                },
                {
                    "title": "Message",
                    "fields": [
                        {
                            "key": "message",
                            "label": "Message",
                            "type": "variable_textarea",
                            "placeholder": "Hello from Fuse!",
                            "required": True,
                            "hint": "Message text to send. Use @ to insert a variable.",
                        },
                        {
                            "key": "use_markdown",
                            "label": "Use Markdown",
                            "type": "checkbox",
                            "hint": "Format the message using Webex Markdown (bold, links, etc.)",
                        },
                    ],
                },
            ],
        },
    },
    {
        "type": "send_gmail",
        "label": "Send Gmail",
        "icon": "SiGmail",
        "section": "Google",
        "required_integration": "gmail",
        "description": "Send an email using your configured Gmail integration.",
        "config_form": {
            "sections": [
                {
                    "title": "Email Details",
                    "fields": [
                        {"key": "to", "label": "To", "type": "variable_text", "placeholder": "recipient@example.com", "required": True, "hint": "Email address to send to. Use @ to insert a variable."},
                        {"key": "cc", "label": "CC", "type": "variable_text", "placeholder": "cc@example.com", "hint": "Carbon copy. Use @ to insert a variable."},
                        {"key": "bcc", "label": "BCC", "type": "variable_text", "placeholder": "bcc@example.com", "hint": "Blind carbon copy. Use @ to insert a variable."},
                        {"key": "subject", "label": "Subject", "type": "variable_text", "placeholder": "Email subject", "required": True, "hint": "Subject of the email. Use @ to insert a variable."},
                        {
                            "key": "sub_type", "label": "Content Type", "type": "select", "required": True,
                            "options": [
                                {"label": "Plain Text", "value": "text/plain"},
                                {"label": "HTML", "value": "text/html"},
                            ],
                            "hint": "The format of the email body"
                        },
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
        "branch_handles": ["true", "false"],
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
        "type": "ai_generate_text",
        "label": "Ask Aura",
        "icon": "RiAiGenerate",
        "section": "AI",
        "description": "Generate AI text from a prompt. Optionally enable web search to ground the response in current information.",
        "config_form": {
            "sections": [
                {
                    "title": "Prompt",
                    "fields": [
                        {
                            "key": "prompt",
                            "label": "Prompt",
                            "type": "variable_textarea",
                            "placeholder": "Write a summary of the following data...",
                            "required": True,
                            "hint": "Instructions for the AI. Use @ to insert variables.",
                        },
                    ],
                },
                {
                    "title": "Tools",
                    "fields": [
                        {
                            "key": "web_search",
                            "label": "Web Search",
                            "type": "checkbox",
                            "hint": "When enabled, the AI searches the web for up-to-date information before generating text.",
                        },
                    ],
                },
            ],
        },
    },
    {
        "type": "ai_structured_output",
        "label": "Structured Output",
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
                    "title": "Tools",
                    "fields": [
                        {
                            "key": "web_search",
                            "label": "Web Search",
                            "type": "checkbox",
                            "hint": "When enabled, the AI searches the web for up-to-date information before generating structured output.",
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
                            "type": "key_value_builder",
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
                            "hint": "Define the JSON body to send (POST, PUT, PATCH). Set key, type and value for each field use @ to insert variables.",
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
                            "hint": "Declare the fields you expect in the JSON response. Each field becomes a variable: {{node_id.body.fieldName}}.",
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
    {
        "type": "fork",
        "label": "Fork (Parallel)",
        "icon": "TbGitFork",
        "section": "Logic",
        "description": "Run multiple branches in parallel. Connect multiple action nodes to this node's output.",
        "config_form": {
            "sections": [
                {
                    "fields": [
                        {"key": "info", "label": "Info", "type": "text", "hint": "Connect multiple nodes to the output of this node. They will be executed in parallel.", "disabled": True}
                    ]
                }
            ]
        }
    },
    {
        "type": "join",
        "label": "Wait (Join)",
        "icon": "TbGitMerge",
        "section": "Logic",
        "description": "Wait until all incoming parallel branches have completed before proceeding.",
        "config_form": {
            "sections": [
                {
                    "fields": [
                        {"key": "info", "label": "Info", "type": "text", "hint": "Connect multiple parallel branches to this node. It will wait for all of them to finish.", "disabled": True}
                    ]
                }
            ]
        }
    },
    {
        "type": "set_variables",
        "label": "Set Variables",
        "icon": "VscVariableGroup",
        "section": "Logic",
        "description": "Define custom variables (strings, numbers, booleans, objects, arrays) to use in downstream steps. You can combine existing variables here to simplify logic later.",
        "config_form": {
            "sections": [
                {
                    "title": "Variables",
                    "fields": [
                        {
                            "key": "variables",
                            "label": "Variables",
                            "type": "json_value_builder",
                            "hint": "Set key, type, and value for each variable. Use @ to insert data from previous steps. Remove unwanted variables by clicking the × button.",
                        },
                    ],
                },
            ],
        },
    },
]


