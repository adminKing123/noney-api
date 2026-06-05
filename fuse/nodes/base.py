"""fuse/nodes/base.py — Abstract base class for all Fuse node handlers."""


class NodeHandler:
    """
    Base class for every Fuse node type.

    Subclasses must implement ``execute()``, which receives the node's saved
    configuration dict and the current ``ExecutionContext``, and must return a
    plain dict that becomes the node's output (stored in
    ``context.node_outputs[node_id]``).
    """

    def execute(self, config: dict, context) -> dict:
        """
        Execute this node and return its output dict.

        Args:
            config:  Saved node configuration (already variable-resolved where
                     the handler decides to resolve).
            context: ``ExecutionContext`` — gives access to trigger data and
                     every prior node's output for variable resolution.

        Returns:
            A plain dict stored in ``context.node_outputs``.  Downstream nodes
            can reference these values via ``{{node_id.key}}`` tokens.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__}.execute() is not implemented."
        )
