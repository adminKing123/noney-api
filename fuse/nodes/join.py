from .base import NodeHandler
from fuse.executor import ExecutionContext

class JoinHandler(NodeHandler):
    def execute(self, config: dict, ctx: ExecutionContext) -> dict:
        return {"success": True, "message": "Join executed"}
