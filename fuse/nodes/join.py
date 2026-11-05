from .base import NodeHandler
from fuse.executor import ExecutionContext

NODE_ROLE = "action"

NODE_DEFINITION = {
    "type": "join",
    "label": "Wait (Join)",
    "icon": "TbGitMerge",
    "section": "Logic",
    "description": "Wait until all incoming parallel branches have completed before proceeding.",
    "config_form": {
        "sections": [
            {
                "fields": [
                    {
                        "key": "info",
                        "label": "Info",
                        "type": "text",
                        "hint": "Connect multiple parallel branches to this node. It will wait for all of them to finish.",
                        "disabled": True,
                    }
                ]
            }
        ]
    },
}


class JoinHandler(NodeHandler):
    def execute(self, config: dict, ctx: ExecutionContext) -> dict:
        return {"success": True, "message": "Join executed"}