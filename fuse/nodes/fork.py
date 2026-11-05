from .base import NodeHandler
from fuse.executor import ExecutionContext

NODE_ROLE = "action"

NODE_DEFINITION = {
    "type": "fork",
    "label": "Fork (Parallel)",
    "icon": "TbGitFork",
    "section": "Logic",
    "description": "Run multiple branches in parallel. Connect multiple action nodes to this node's output.",
    "config_form": {
        "sections": [
            {
                "fields": [
                    {
                        "key": "info",
                        "label": "Info",
                        "type": "text",
                        "hint": "Connect multiple nodes to the output of this node. They will be executed in parallel.",
                        "disabled": True,
                    }
                ]
            }
        ]
    },
}


class ForkHandler(NodeHandler):
    def execute(self, config: dict, ctx: ExecutionContext) -> dict:
        return {"success": True, "message": "Fork executed"}