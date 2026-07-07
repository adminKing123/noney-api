"""
fuse/nodes/set_variables.py
===========================
Set Variables action node handler.

Resolves all visually-built variables and exposes them directly into its output
for downstream nodes to reference.
"""

import logging
from .base import NodeHandler
from .http_request import _resolve_field_config

logger = logging.getLogger(__name__)

class SetVariablesHandler(NodeHandler):
    node_type = "set_variables"

    def execute(self, config: dict, context) -> dict:
        outputs = context.node_outputs
        
        # Resolves dynamic variables from the json_value_builder
        # flat=False ensures that we build a fully typed nested JSON dictionary.
        variables_dict = _resolve_field_config(
            config.get("variables"), outputs, flat=False
        )

        logger.info(
            "[FUSE] set_variables executed — workflow=%s run=%s  vars_set=%d",
            context.workflow_id, context.run_id, len(variables_dict)
        )
        
        return variables_dict
