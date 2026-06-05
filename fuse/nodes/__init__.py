"""
fuse/nodes/__init__.py
======================
Central registry that maps ``node_type`` strings (as stored in the compiled
graph) to their handler instances.

To add a new node type:
  1. Create ``fuse/nodes/my_type.py`` with a class that inherits NodeHandler.
  2. Import it here and add an entry to ``HANDLERS``.
"""

from .webhook      import WebhookHandler
from .schedule     import ScheduleHandler
from .if_else      import IfElseHandler
from .get_notified import GetNotifiedHandler

# Maps the node_type string (from compiled_graph["nodes"][id]["node_type"])
# to the singleton handler that executes it.
HANDLERS: dict = {
    "webhook":      WebhookHandler(),
    "schedule":     ScheduleHandler(),
    "if_else":      IfElseHandler(),
    "get_notified": GetNotifiedHandler(),
}
