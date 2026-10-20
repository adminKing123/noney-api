"""
fuse/nodes/__init__.py
======================
Central registry that maps ``node_type`` strings (as stored in the compiled
graph) to their handler instances.

To add a new node type:
  1. Create ``fuse/nodes/my_type.py`` with a class that inherits NodeHandler.
  2. Import it here and add an entry to ``HANDLERS``.
"""

from .webhook                  import WebhookHandler
from .schedule                 import ScheduleHandler
from .if_else                  import IfElseHandler
from .switch                   import SwitchHandler
from .get_notified             import GetNotifiedHandler
from .get_notified_email       import GetNotifiedEmailHandler
from .ai_structured_output     import AIStructuredOutputHandler
from .ai_generate_text         import AIGenerateTextHandler
from .http_request             import HttpRequestHandler
from .send_gmail               import SendGmailHandler
from .webex_message            import WebexMessageHandler
from .send_webex_message       import SendWebexMessageHandler
from .github_pull_request      import GithubPullRequestHandler
from .set_variables            import SetVariablesHandler
from .for_each                 import ForEachHandler
from .fork                     import ForkHandler
from .join                     import JoinHandler
from .google_sheets_add_row    import GoogleSheetsAddRowHandler
from .create_json_file         import CreateJsonFileHandler

# Maps the node_type string (from compiled_graph["nodes"][id]["node_type"])
# to the singleton handler that executes it.
HANDLERS: dict = {
    "webhook":                  WebhookHandler(),
    "schedule":                 ScheduleHandler(),
    "if_else":                  IfElseHandler(),
    "switch":                   SwitchHandler(),
    "get_notified":             GetNotifiedHandler(),
    "get_notified_email":       GetNotifiedEmailHandler(),
    "ai_structured_output":     AIStructuredOutputHandler(),
    "ai_generate_text":         AIGenerateTextHandler(),
    "http_request":             HttpRequestHandler(),
    "send_gmail":               SendGmailHandler(),
    "webex_message":            WebexMessageHandler(),
    "send_webex_message":       SendWebexMessageHandler(),
    "github_pull_request":      GithubPullRequestHandler(),
    "set_variables":            SetVariablesHandler(),
    "for_each":                 ForEachHandler(),
    "fork":                     ForkHandler(),
    "join":                     JoinHandler(),
    "google_sheets_add_row":    GoogleSheetsAddRowHandler(),
    "create_json_file":         CreateJsonFileHandler(),
}