from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterator, Sequence
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from types import TracebackType
from typing import Any

from langchain_core.runnables import RunnableConfig
from firebase_admin import firestore

from langgraph.checkpoint.base import (
    WRITES_IDX_MAP,
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    SerializerProtocol,
    get_checkpoint_id,
    get_checkpoint_metadata,
)

from .datacontroller import db

logger = logging.getLogger(__name__)


class FirebaseSaver(
    BaseCheckpointSaver[str], AbstractContextManager, AbstractAsyncContextManager
):
    """A Firebase Firestore checkpoint saver.

    This checkpoint saver stores checkpoints in Firebase Firestore instead of memory.

    Args:
        serde: The serializer to use for serializing and deserializing checkpoints.

    Examples:
        from langgraph.graph import StateGraph
        from db.firebase_checkpoint_saver import FirebaseSaver
        
        memory = FirebaseSaver()
        
        builder = StateGraph(int)
        builder.add_node("add_one", lambda x: x + 1)
        builder.set_entry_point("add_one")
        builder.set_finish_point("add_one")
        
        graph = builder.compile(checkpointer=memory)
        result = graph.invoke(1, {"configurable": {"thread_id": "thread-1"}})
    """

    def __init__(
        self,
        *,
        serde: SerializerProtocol | None = None,
    ) -> None:
        super().__init__(serde=serde)
        self.client = db.client

    def __enter__(self) -> FirebaseSaver:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        return None

    async def __aenter__(self) -> FirebaseSaver:
        return self

    async def __aexit__(
        self,
        __exc_type: type[BaseException] | None,
        __exc_value: BaseException | None,
        __traceback: TracebackType | None,
    ) -> bool | None:
        return None

    def _get_checkpoint_ref(self, thread_id: str, checkpoint_ns: str, checkpoint_id: str):
        """Get reference to a checkpoint document."""
        return (
            self.client.collection("checkpoints")
            .document(thread_id)
            .collection("checkpoint_namespaces")
            .document(checkpoint_ns or "default")
            .collection("checkpoints")
            .document(checkpoint_id)
        )

    def _get_writes_ref(self, thread_id: str, checkpoint_ns: str, checkpoint_id: str):
        """Get reference to writes collection."""
        return (
            self.client.collection("checkpoints")
            .document(thread_id)
            .collection("checkpoint_namespaces")
            .document(checkpoint_ns or "default")
            .collection("writes")
            .document(checkpoint_id)
            .collection("items")
        )

    def _get_blobs_ref(self, thread_id: str, checkpoint_ns: str):
        """Get reference to blobs collection."""
        return (
            self.client.collection("checkpoints")
            .document(thread_id)
            .collection("checkpoint_namespaces")
            .document(checkpoint_ns or "default")
            .collection("blobs")
        )

    def _load_blobs(
        self, thread_id: str, checkpoint_ns: str, versions: ChannelVersions
    ) -> dict[str, Any]:
        """Load blob data from Firebase."""
        channel_values: dict[str, Any] = {}
        blobs_ref = self._get_blobs_ref(thread_id, checkpoint_ns)
        
        for k, v in versions.items():
            blob_id = f"{k}_{v}"
            blob_doc = blobs_ref.document(blob_id).get()
            
            if blob_doc.exists:
                blob_data = blob_doc.to_dict()
                if blob_data and blob_data.get("type") != "empty":
                    channel_values[k] = self.serde.loads_typed(
                        (blob_data["type"], blob_data["data"])
                    )
        
        return channel_values

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        """Get a checkpoint tuple from Firebase storage.

        This method retrieves a checkpoint tuple from Firebase based on the
        provided config. If the config contains a `checkpoint_id` key, the checkpoint with
        the matching thread ID and timestamp is retrieved. Otherwise, the latest checkpoint
        for the given thread ID is retrieved.

        Args:
            config: The config to use for retrieving the checkpoint.

        Returns:
            The retrieved checkpoint tuple, or None if no matching checkpoint was found.
        """
        thread_id: str = config["configurable"]["thread_id"]
        checkpoint_ns: str = config["configurable"].get("checkpoint_ns", "")
        
        if checkpoint_id := get_checkpoint_id(config):
            # Get specific checkpoint
            checkpoint_ref = self._get_checkpoint_ref(thread_id, checkpoint_ns, checkpoint_id)
            checkpoint_doc = checkpoint_ref.get()
            
            if not checkpoint_doc.exists:
                return None
            
            checkpoint_data = checkpoint_doc.to_dict()
            checkpoint = self.serde.loads_typed(
                (checkpoint_data["checkpoint_type"], checkpoint_data["checkpoint_data"])
            )
            metadata = self.serde.loads_typed(
                (checkpoint_data["metadata_type"], checkpoint_data["metadata_data"])
            )
            parent_checkpoint_id = checkpoint_data.get("parent_checkpoint_id")
            
            # Get writes
            writes_ref = self._get_writes_ref(thread_id, checkpoint_ns, checkpoint_id)
            writes_docs = writes_ref.stream()
            writes = [
                (
                    write_doc.to_dict()["task_id"],
                    write_doc.to_dict()["channel"],
                    self.serde.loads_typed(
                        (write_doc.to_dict()["value_type"], write_doc.to_dict()["value_data"])
                    ),
                )
                for write_doc in writes_docs
            ]
            
            return CheckpointTuple(
                config=config,
                checkpoint={
                    **checkpoint,
                    "channel_values": self._load_blobs(
                        thread_id, checkpoint_ns, checkpoint["channel_versions"]
                    ),
                },
                metadata=metadata,
                pending_writes=writes,
                parent_config=(
                    {
                        "configurable": {
                            "thread_id": thread_id,
                            "checkpoint_ns": checkpoint_ns,
                            "checkpoint_id": parent_checkpoint_id,
                        }
                    }
                    if parent_checkpoint_id
                    else None
                ),
            )
        else:
            # Get latest checkpoint
            checkpoints_ref = (
                self.client.collection("checkpoints")
                .document(thread_id)
                .collection("checkpoint_namespaces")
                .document(checkpoint_ns or "default")
                .collection("checkpoints")
                .order_by("checkpoint_id", direction=firestore.Query.DESCENDING)
                .limit(1)
            )
            
            checkpoints = list(checkpoints_ref.stream())
            if not checkpoints:
                return None
            
            checkpoint_doc = checkpoints[0]
            checkpoint_id = checkpoint_doc.id
            checkpoint_data = checkpoint_doc.to_dict()
            
            checkpoint = self.serde.loads_typed(
                (checkpoint_data["checkpoint_type"], checkpoint_data["checkpoint_data"])
            )
            metadata = self.serde.loads_typed(
                (checkpoint_data["metadata_type"], checkpoint_data["metadata_data"])
            )
            parent_checkpoint_id = checkpoint_data.get("parent_checkpoint_id")
            
            # Get writes
            writes_ref = self._get_writes_ref(thread_id, checkpoint_ns, checkpoint_id)
            writes_docs = writes_ref.stream()
            writes = [
                (
                    write_doc.to_dict()["task_id"],
                    write_doc.to_dict()["channel"],
                    self.serde.loads_typed(
                        (write_doc.to_dict()["value_type"], write_doc.to_dict()["value_data"])
                    ),
                )
                for write_doc in writes_docs
            ]
            
            return CheckpointTuple(
                config={
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": checkpoint_id,
                    }
                },
                checkpoint={
                    **checkpoint,
                    "channel_values": self._load_blobs(
                        thread_id, checkpoint_ns, checkpoint["channel_versions"]
                    ),
                },
                metadata=metadata,
                pending_writes=writes,
                parent_config=(
                    {
                        "configurable": {
                            "thread_id": thread_id,
                            "checkpoint_ns": checkpoint_ns,
                            "checkpoint_id": parent_checkpoint_id,
                        }
                    }
                    if parent_checkpoint_id
                    else None
                ),
            )

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        """List checkpoints from Firebase storage.

        This method retrieves a list of checkpoint tuples from Firebase based
        on the provided criteria.

        Args:
            config: Base configuration for filtering checkpoints.
            filter: Additional filtering criteria for metadata.
            before: List checkpoints created before this configuration.
            limit: Maximum number of checkpoints to return.

        Yields:
            An iterator of matching checkpoint tuples.
        """
        if config:
            thread_id = config["configurable"]["thread_id"]
            checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
            config_checkpoint_id = get_checkpoint_id(config)
            
            # Query specific thread and namespace
            checkpoints_ref = (
                self.client.collection("checkpoints")
                .document(thread_id)
                .collection("checkpoint_namespaces")
                .document(checkpoint_ns or "default")
                .collection("checkpoints")
                .order_by("checkpoint_id", direction=firestore.Query.DESCENDING)
            )
        else:
            # Query all threads - this is inefficient in Firebase, but keeping for API compatibility
            # In production, you'd want to require a thread_id
            logger.warning("Listing checkpoints without thread_id is inefficient in Firebase")
            return
        
        if limit:
            checkpoints_ref = checkpoints_ref.limit(limit)
        
        before_checkpoint_id = get_checkpoint_id(before) if before else None
        
        count = 0
        for checkpoint_doc in checkpoints_ref.stream():
            checkpoint_id = checkpoint_doc.id
            checkpoint_data = checkpoint_doc.to_dict()
            
            # Filter by checkpoint ID from config
            if config_checkpoint_id and checkpoint_id != config_checkpoint_id:
                continue
            
            # Filter by before checkpoint ID
            if before_checkpoint_id and checkpoint_id >= before_checkpoint_id:
                continue
            
            # Deserialize metadata for filtering
            metadata = self.serde.loads_typed(
                (checkpoint_data["metadata_type"], checkpoint_data["metadata_data"])
            )
            
            # Filter by metadata
            if filter and not all(
                query_value == metadata.get(query_key)
                for query_key, query_value in filter.items()
            ):
                continue
            
            # Limit check
            if limit is not None and count >= limit:
                break
            count += 1
            
            # Deserialize checkpoint
            checkpoint = self.serde.loads_typed(
                (checkpoint_data["checkpoint_type"], checkpoint_data["checkpoint_data"])
            )
            parent_checkpoint_id = checkpoint_data.get("parent_checkpoint_id")
            
            # Get writes
            writes_ref = self._get_writes_ref(thread_id, checkpoint_ns, checkpoint_id)
            writes_docs = writes_ref.stream()
            writes = [
                (
                    write_doc.to_dict()["task_id"],
                    write_doc.to_dict()["channel"],
                    self.serde.loads_typed(
                        (write_doc.to_dict()["value_type"], write_doc.to_dict()["value_data"])
                    ),
                )
                for write_doc in writes_docs
            ]
            
            yield CheckpointTuple(
                config={
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": checkpoint_id,
                    }
                },
                checkpoint={
                    **checkpoint,
                    "channel_values": self._load_blobs(
                        thread_id, checkpoint_ns, checkpoint["channel_versions"]
                    ),
                },
                metadata=metadata,
                parent_config=(
                    {
                        "configurable": {
                            "thread_id": thread_id,
                            "checkpoint_ns": checkpoint_ns,
                            "checkpoint_id": parent_checkpoint_id,
                        }
                    }
                    if parent_checkpoint_id
                    else None
                ),
                pending_writes=writes,
            )

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        """Save a checkpoint to Firebase storage.

        This method saves a checkpoint to Firebase. The checkpoint is associated
        with the provided config.

        Args:
            config: The config to associate with the checkpoint.
            checkpoint: The checkpoint to save.
            metadata: Additional metadata to save with the checkpoint.
            new_versions: New versions as of this write

        Returns:
            RunnableConfig: The updated config containing the saved checkpoint's timestamp.
        """
        c = checkpoint.copy()
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"]["checkpoint_ns"]
        checkpoint_id = checkpoint["id"]
        
        # Save blobs
        values: dict[str, Any] = c.pop("channel_values")  # type: ignore[misc]
        blobs_ref = self._get_blobs_ref(thread_id, checkpoint_ns)
        
        for k, v in new_versions.items():
            blob_id = f"{k}_{v}"
            if k in values:
                value_type, value_data = self.serde.dumps_typed(values[k])
                blobs_ref.document(blob_id).set({
                    "type": value_type,
                    "data": value_data,
                    "channel": k,
                    "version": v,
                })
            else:
                blobs_ref.document(blob_id).set({
                    "type": "empty",
                    "data": b"",
                    "channel": k,
                    "version": v,
                })
        
        # Save checkpoint
        checkpoint_type, checkpoint_data = self.serde.dumps_typed(c)
        metadata_type, metadata_data = self.serde.dumps_typed(
            get_checkpoint_metadata(config, metadata)
        )
        
        checkpoint_ref = self._get_checkpoint_ref(thread_id, checkpoint_ns, checkpoint_id)
        checkpoint_ref.set({
            "checkpoint_type": checkpoint_type,
            "checkpoint_data": checkpoint_data,
            "metadata_type": metadata_type,
            "metadata_data": metadata_data,
            "parent_checkpoint_id": config["configurable"].get("checkpoint_id"),
            "checkpoint_id": checkpoint_id,
        })
        
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Save a list of writes to Firebase storage.

        This method saves a list of writes to Firebase. The writes are associated
        with the provided config.

        Args:
            config: The config to associate with the writes.
            writes: The writes to save.
            task_id: Identifier for the task creating the writes.
            task_path: Path of the task creating the writes.

        Returns:
            None
        """
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = config["configurable"]["checkpoint_id"]
        
        writes_ref = self._get_writes_ref(thread_id, checkpoint_ns, checkpoint_id)
        
        for idx, (c, v) in enumerate(writes):
            write_idx = WRITES_IDX_MAP.get(c, idx)
            write_id = f"{task_id}_{write_idx}"
            
            # Check if write already exists (for idempotency)
            if write_idx >= 0:
                existing = writes_ref.document(write_id).get()
                if existing.exists:
                    continue
            
            value_type, value_data = self.serde.dumps_typed(v)
            writes_ref.document(write_id).set({
                "task_id": task_id,
                "channel": c,
                "value_type": value_type,
                "value_data": value_data,
                "task_path": task_path,
                "write_idx": write_idx,
            })

    def delete_thread(self, thread_id: str) -> None:
        """Delete all checkpoints and writes associated with a thread ID.

        Args:
            thread_id: The thread ID to delete.

        Returns:
            None
        """
        thread_ref = self.client.collection("checkpoints").document(thread_id)
        self._recursive_delete(thread_ref)

    def _recursive_delete(self, ref):
        """Recursively delete a document and its subcollections."""
        # Delete all subcollections
        collections = ref.collections()
        for collection in collections:
            for doc in collection.stream():
                self._recursive_delete(doc.reference)
        
        # Delete the document itself
        ref.delete()

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        """Asynchronous version of `get_tuple`.

        Args:
            config: The config to use for retrieving the checkpoint.

        Returns:
            The retrieved checkpoint tuple, or None if no matching checkpoint was found.
        """
        return self.get_tuple(config)

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        """Asynchronous version of `list`.

        Args:
            config: The config to use for listing the checkpoints.

        Yields:
            An asynchronous iterator of checkpoint tuples.
        """
        for item in self.list(config, filter=filter, before=before, limit=limit):
            yield item

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        """Asynchronous version of `put`.

        Args:
            config: The config to associate with the checkpoint.
            checkpoint: The checkpoint to save.
            metadata: Additional metadata to save with the checkpoint.
            new_versions: New versions as of this write

        Returns:
            RunnableConfig: The updated config containing the saved checkpoint's timestamp.
        """
        return self.put(config, checkpoint, metadata, new_versions)

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Asynchronous version of `put_writes`.

        Args:
            config: The config to associate with the writes.
            writes: The writes to save, each as a (channel, value) pair.
            task_id: Identifier for the task creating the writes.
            task_path: Path of the task creating the writes.

        Returns:
            None
        """
        return self.put_writes(config, writes, task_id, task_path)

    async def adelete_thread(self, thread_id: str) -> None:
        """Delete all checkpoints and writes associated with a thread ID.

        Args:
            thread_id: The thread ID to delete.

        Returns:
            None
        """
        return self.delete_thread(thread_id)

    def get_next_version(self, current: str | None, channel: None) -> str:
        """Generate next version string for channel versioning."""
        import random
        
        if current is None:
            current_v = 0
        elif isinstance(current, int):
            current_v = current
        else:
            current_v = int(current.split(".")[0])
        next_v = current_v + 1
        next_h = random.random()
        return f"{next_v:032}.{next_h:016}"
