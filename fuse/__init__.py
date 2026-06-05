"""
Fuse — Workflow Execution Engine
=================================
This package implements the compile-and-execute model for Fuse workflows.

Sub-modules
-----------
compiler          : Pure-function graph compiler and validator.
variable_resolver : Token-based variable interpolation ({{node_id.body.field}}).
executor          : DAG traversal and per-run execution context.
runtime           : Singleton RuntimeManager that manages active workflow executions.
nodes/            : Per-node-type execution handlers.
"""
