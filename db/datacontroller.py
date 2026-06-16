import firebase_admin
from firebase_admin import credentials, firestore, auth
import json
from config import CONFIG
from datetime import datetime

class User:
    def __init__(self, client):
        self.client = client

    def authenticate(self, token):
        decoded = auth.verify_id_token(token, clock_skew_seconds=60)
        return decoded

    # ── Web Push subscription ─────────────────────────────────────────────────

    def _push_col(self, uid: str):
        """Firestore subcollection: users/{uid}/push_subscriptions"""
        return self.client.collection("users").document(uid).collection("push_subscriptions")

    def save_push_subscription(self, uid: str, subscription: dict) -> None:
        """
        Upsert the user's browser push subscription under a fixed document ID
        derived from the subscription endpoint so duplicate registrations are
        de-duped automatically.
        """
        import hashlib
        endpoint = subscription.get("endpoint", "")
        if not endpoint:
            return

        # Remove this endpoint from any other user to prevent cross-account notifications
        # if the device is shared or a user switches accounts.
        try:
            query = self.client.collection_group("push_subscriptions").where("endpoint", "==", endpoint)
            for doc in query.stream():
                if doc.to_dict().get("uid") != uid:
                    doc.reference.delete()
        except Exception:
            pass

        doc_id   = hashlib.sha256(endpoint.encode()).hexdigest()[:32]
        self._push_col(uid).document(doc_id).set({
            **subscription,
            "uid":        uid,
            "updated_at": datetime.utcnow().isoformat() + "Z",
        })

    def get_push_subscriptions(self, uid: str) -> list[dict]:
        """Return all stored push subscriptions for a user."""
        return [d.to_dict() for d in self._push_col(uid).stream()]

    def delete_push_subscription(self, uid: str, endpoint: str) -> None:
        """Remove a subscription by its endpoint URL."""
        import hashlib
        doc_id = hashlib.sha256(endpoint.encode()).hexdigest()[:32]
        self._push_col(uid).document(doc_id).delete()

class MsgEntity:
    def __init__(self, data):
        self.id = data.get("id")
        self.chat_id = data.get("chat_id")

        self.prompt = data.get("prompt")
        self.answer = data.get("answer", [])
        self.sources = data.get("sources", [])
        self.answer_files = data.get("answer_files", [])
        self.steps = data.get("steps", [])

        self.model = data.get("model")
        self.google_search = data.get("google_search", False)
        self.generate_image = data.get("generate_image", False)

        self.created_at = data.get("created_at")
        self.updated_at = data.get("updated_at")

        self.interrupt = data.get("interrupt", None)
        self.files = data.get("files", [])
        
        self.descisions = data.get("descisions", None)
        self.deep_research = data.get("deep_research", False)
        self.action_type = data.get("action_type", None)

        self.duration = data.get("duration", None)

        # Token usage and cost tracking (populated after generation completes)
        self.tokens = data.get("tokens", {"input": 0, "output": 0, "total": 0})
        self.cost_usd = data.get("cost_usd", None)
        self.images_generated = data.get("images_generated", 0)

    def get_dict(self):
        payload = {}
        payload["id"] = self.id
        payload["prompt"] = self.prompt
        payload["answer"] = self.answer
        payload["sources"] = self.sources
        payload["answer_files"] = self.answer_files
        payload["steps"] = self.steps
        payload["model"] = self.model
        payload["google_search"] = self.google_search
        payload["generate_image"] = self.generate_image
        payload["created_at"] = self.created_at
        payload["updated_at"] = self.updated_at
        payload["interrupt"] = self.interrupt
        payload["files"] = self.files
        payload["deep_research"] = self.deep_research
        payload["duration"] = self.duration
        payload["tokens"] = self.tokens
        payload["cost_usd"] = self.cost_usd
        payload["images_generated"] = self.images_generated
        return payload

class Msg:
    def __init__(self, client):
        self.client = client

    def get_new_msg(self, id, default_data=None):
        if default_data is None:
            default_data = {}

        data = {
            "id": id,
            **default_data
        }
        return MsgEntity(data)
    
    def get_msg_by_id(self, chatId, msgId):
        messages_ref = self.client.collection("chats").document(chatId).collection("messages").document(msgId)
        msg_doc = messages_ref.get()
        if msg_doc.exists:
            return MsgEntity(msg_doc.to_dict())
        return None


    def save_message(self, chatId, msg_dict):
        messages_ref = self.client.collection("chats").document(chatId).collection("messages")
        msg_id = msg_dict.get("id")
        if msg_id:
            messages_ref.document(msg_id).set(msg_dict)
        return msg_id

class Chat:
    def __init__(self, client):
        self.client = client

    def delete_chat(self, userId, chatId):
        chat_ref = self.client.collection("chats").document(chatId)
        self.client.recursive_delete(chat_ref)

        chat_ref = self.client.collection("users").document(userId).collection("drafts").document(chatId)
        self.client.recursive_delete(chat_ref)

    def rename_chat(self, userId, chatId, new_title):
        chat_ref = self.client.collection("chats").document(chatId)
        chat_ref.update({
            "title": new_title,
            # "updated_at": firestore.SERVER_TIMESTAMP
        })

    def update_usage(self, chat_id: str, tokens: dict, cost_usd: float, model: str = None):
        """
        Atomically increment the chat document's aggregate token counters
        and total cost. Optionally records the AURA model ID used so that
        the analytics dashboard can group usage by model.

        Args:
            chat_id:  Firestore chat document ID.
            tokens:   dict with keys 'input', 'output', 'total' (int counts).
            cost_usd: Cost in USD for this generation call (float).
            model:    AURA model ID string (e.g. 'noney-1.0-fast-20241001').
        """
        try:
            chat_ref = self.client.collection("chats").document(chat_id)
            update_data = {
                "total_tokens.input": firestore.Increment(tokens.get("input", 0)),
                "total_tokens.output": firestore.Increment(tokens.get("output", 0)),
                "total_tokens.total": firestore.Increment(tokens.get("total", 0)),
                "total_cost_usd": firestore.Increment(cost_usd or 0.0),
            }
            # Record the primary model so analytics can group by it.
            # Only set once; subsequent messages in the same chat do not overwrite.
            if model:
                update_data["model"] = model
            chat_ref.update(update_data)
        except Exception as e:
            print(f"[DB] Failed to update chat usage for {chat_id}: {e}")

    def get_messages(self, userId, chatId, limit=CONFIG.GEMINI_MESSAGE_LIMIT, should_yeild=False):
        messages_ref = self.client.collection("chats").document(chatId).collection("messages").order_by("created_at", direction=firestore.Query.ASCENDING).limit(limit)
        if should_yeild:
            messages_docs = messages_ref.stream()
            for msg in messages_docs:
                yield msg.to_dict()
        else:
            messages_docs = messages_ref.stream()
            return [msg.to_dict() for msg in messages_docs]

class File:
    def __init__(self, client):
        self.client = client
    
    def add_file(self, user_id, file_data, chat_id="", parent_id="root"):
        try:
            file_id = file_data.get("file_id")
            if not file_id:
                raise ValueError("file_data must contain 'file_id'")
            data = {
                "id": file_id,
                "type": "file",
                "meta_data": file_data,
                "parent_id": parent_id,
                "owner_id": user_id,
                "created_at": datetime.utcnow().isoformat() + "Z",
                "chat_id": chat_id
            }
            
            doc_ref = self.client.collection("files").document(data["id"])
            doc_ref.set(data)
            return doc_ref.id
        except Exception as e:
            print(f"Error adding file: {e}")
    
    def get_file(self, file_id):
        """
        Get file metadata from Firebase
        
        Args:
            file_id: The file ID to retrieve
            
        Returns:
            File data dictionary or None if not found
        """
        try:
            file_ref = self.client.collection("files").document(file_id)
            file_doc = file_ref.get()
            if file_doc.exists:
                return file_doc.to_dict()
            return None
        except Exception as e:
            print(f"Error getting file: {e}")
            return None
    
    def remove_file(self, file_id):
        """
        Remove file metadata from Firebase
        
        Args:
            file_id: The file ID to remove
            
        Returns:
            True if successful, False otherwise
        """
        try:
            file_ref = self.client.collection("files").document(file_id)
            file_ref.delete()
            return True
        except Exception as e:
            print(f"Error removing file: {e}")
            return False

class Analytics:
    """
    Persists per-generation token and cost usage under the requesting user's
    own Firestore sub-tree, mirroring the structure of the main chats /
    messages collections so that usage data is never lost when a chat is deleted.

    Firestore layout
    ----------------
    users/{user_id}/
      usage/                                â† collection
        {chat_id}                           â† document  (chat-level aggregate)
          chat_id      : str
          model        : str                (AURA model ID of last generation)
          total_tokens : { input, output, total }
          total_cost_usd : float
          generation_count : int
          created_at   : ISO-8601 str       (first generation timestamp)
          updated_at   : ISO-8601 str       (latest generation timestamp)

          messages/                         â† sub-collection
            {message_id}                    â† document  (per-message record)
              message_id  : str
              chat_id     : str
              model       : str
              tokens      : { input, output, total }
              cost_usd    : float
              created_at  : ISO-8601 str
    """

    def __init__(self, client):
        self.client = client

    def record_generation(
        self,
        user_id: str,
        chat_id: str,
        message_id: str,
        tokens: dict,
        cost_usd: float,
        model_id: str,
        now_iso: str,
        images_generated: int = 0,
        generation_type: str = "text",
    ) -> None:
        """
        Persist one generation's usage data with two atomic Firestore operations.

        1. Creates / overwrites the per-message usage document (idempotent
           â€” safe to re-run on retry because it uses set(), not add()).
        2. Atomically increments the parent chat-level usage document.
           If the chat usage document does not exist yet it is initialised
           first, then the increments are applied.

        Supports both text/token-based models and image generation models
        (e.g. Imagen 4) which have zero tokens but non-zero per-image cost.
        ``generation_type`` is stored on each per-message doc and also
        written (not incremented) on each per-model entry so the analytics
        dashboard can distinguish token-priced vs image-priced vs future
        video/audio models.

        Args:
            user_id:          Firebase UID of the requesting user.
            chat_id:          Firestore chat document ID.
            message_id:       Firestore message document ID.
            tokens:           dict with keys 'input', 'output', 'total' (int).
            cost_usd:         Estimated USD cost for this generation call.
            model_id:         AURA model ID string (e.g. 'noney-1.0-fast-20241001').
            now_iso:          UTC ISO-8601 timestamp string.
            images_generated: Number of images produced (0 for text models).
            generation_type:  'text' | 'image'  (default 'text').
        """
        try:
            inp   = tokens.get("input",  0)
            out   = tokens.get("output", 0)
            total = tokens.get("total",  0)
            cost  = cost_usd or 0.0
            model = model_id or "unknown"

            user_usage_col = (
                self.client
                .collection("users")
                .document(user_id)
                .collection("usage")
            )

            # â”€â”€ 1. Per-message usage document â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            # Use set() so repeated calls with the same message_id are idempotent.
            msg_ref = (
                user_usage_col
                .document(chat_id)
                .collection("messages")
                .document(message_id)
            )
            msg_ref.set({
                "message_id":       message_id,
                "chat_id":          chat_id,
                "model":            model,
                # 'generation_type' lets analytics distinguish image models
                # (cost-per-image, zero tokens) from text models (token-priced).
                # Extend with 'video' / 'audio' when those routes are added.
                "generation_type":  generation_type,
                "tokens": {
                    "input":  inp,
                    "output": out,
                    "total":  total,
                },
                "images_generated": images_generated,
                "cost_usd":         cost,
                "created_at":       now_iso,
            })

            # â”€â”€ 2. Chat-level aggregate document (atomic dot-notation increments) â”€â”€
            # Dots in model IDs (e.g. noney-1.0-fast-20241001) are replaced with
            # underscores so they are safe to use as Firestore map keys via
            # dot-notation. The original model ID is stored in model_id alongside.
            safe = model.replace(".", "_")

            chat_ref = user_usage_col.document(chat_id)
            increment_data = {
                # â”€â”€ Chat-level totals (universal across all model types) â”€â”€â”€â”€â”€â”€
                "total_tokens.input":      firestore.Increment(inp),
                "total_tokens.output":     firestore.Increment(out),
                "total_tokens.total":      firestore.Increment(total),
                "total_images_generated":  firestore.Increment(images_generated),
                "total_cost_usd":          firestore.Increment(cost),
                "generation_count":        firestore.Increment(1),
                "updated_at":              now_iso,
                # â”€â”€ Per-model breakdown within this chat â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                # Multiple models can be used in a single chat; each gets its
                # own sub-map. generation_type is a plain string assignment
                # (not an Increment) â€” it is idempotent for the same model.
                f"by_model.{safe}.model_id":         model,
                f"by_model.{safe}.generation_type":  generation_type,
                f"by_model.{safe}.count":            firestore.Increment(1),
                f"by_model.{safe}.input_tokens":     firestore.Increment(inp),
                f"by_model.{safe}.output_tokens":    firestore.Increment(out),
                f"by_model.{safe}.total_tokens":     firestore.Increment(total),
                f"by_model.{safe}.images_generated": firestore.Increment(images_generated),
                f"by_model.{safe}.cost_usd":         firestore.Increment(cost),
            }
            try:
                chat_ref.update(increment_data)
            except Exception:
                # Document does not exist yet â€” initialise it, then apply increments.
                chat_ref.set({
                    "chat_id":               chat_id,
                    "total_tokens":          {"input": 0, "output": 0, "total": 0},
                    "total_images_generated": 0,
                    "total_cost_usd":        0.0,
                    "generation_count":      0,
                    "by_model":              {},
                    "created_at":            now_iso,
                    "updated_at":            now_iso,
                })
                chat_ref.update(increment_data)

        except Exception as e:
            # Analytics failures must never surface to the generation response.
            print(f"[Analytics] record_generation failed "
                  f"(user={user_id}, chat={chat_id}, msg={message_id}): {e}")


class Workflow:
    """
    CRUD operations for Fuse workflows.

    Firestore layout
    ----------------
    fuse/{workflow_id}          <- document
        id           : str
        owner_id     : str      Firebase UID of the creator
        name         : str
        status       : "active" | "inactive"
        nodes        : list     React Flow node list
        edges        : list     React Flow edge list
        created_at   : ISO-8601 str
        updated_at   : ISO-8601 str
    """

    COLLECTION = "fuse"

    def __init__(self, client):
        self.client = client

    def _col(self):
        return self.client.collection(self.COLLECTION)

    def create(self, owner_id: str, name: str) -> dict:
        """Create a new workflow document and return the full doc."""
        now = datetime.utcnow().isoformat() + "Z"
        doc_ref = self._col().document()
        data = {
            "id":             doc_ref.id,
            "owner_id":       owner_id,
            "name":           name,
            "status":         "inactive",
            "nodes":          [],
            "edges":          [],
            # Compilation state — populated on first activation.
            "compiled_at":    None,
            "graph_hash":     None,
            "compiled_graph": None,
            "created_at":     now,
            "updated_at":     now,
        }
        doc_ref.set(data)
        return data

    def list_for_owner(self, owner_id: str, limit: int = 20, after_created_at: str | None = None, after_id: str | None = None) -> dict:
        """
        Return workflows owned by owner_id, newest first.

        Cursor pagination: pass after_created_at + after_id (values from the
        last document of the previous page) to fetch the next page.

        Returns:
            { "items": [...], "next_cursor": { "after_created_at": ..., "after_id": ... } | None }
        """
        q = (
            self._col()
            .where("owner_id", "==", owner_id)
            .order_by("created_at", direction=firestore.Query.DESCENDING)
        )

        if after_created_at and after_id:
            # Fetch the cursor document to use as the start_after reference
            cursor_doc = self._col().document(after_id).get()
            if cursor_doc.exists:
                q = q.start_after(cursor_doc)

        docs = list(q.limit(limit + 1).stream())
        has_more = len(docs) > limit
        items = [d.to_dict() for d in docs[:limit]]

        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = {"after_created_at": last["created_at"], "after_id": last["id"]}

        return {"items": items, "next_cursor": next_cursor}

    def get(self, workflow_id: str, owner_id: str):
        """Fetch a single workflow, returning None if not found or not owned."""
        doc = self._col().document(workflow_id).get()
        if not doc.exists:
            return None
        data = doc.to_dict()
        if data.get("owner_id") != owner_id:
            return None
        return data

    def update_name(self, workflow_id: str, owner_id: str, name: str):
        """Rename a workflow. Returns updated doc or None if not authorised."""
        existing = self.get(workflow_id, owner_id)
        if existing is None:
            return None
        now = datetime.utcnow().isoformat() + "Z"
        self._col().document(workflow_id).update({"name": name, "updated_at": now})
        return {**existing, "name": name, "updated_at": now}

    def update_graph(self, workflow_id: str, owner_id: str, nodes: list, edges: list):
        """Persist the React Flow node/edge graph. Returns updated doc or None."""
        existing = self.get(workflow_id, owner_id)
        if existing is None:
            return None
        now = datetime.utcnow().isoformat() + "Z"
        self._col().document(workflow_id).update({
            "nodes":      nodes,
            "edges":      edges,
            "updated_at": now,
        })
        return {**existing, "nodes": nodes, "edges": edges, "updated_at": now}

    def update_status(self, workflow_id: str, owner_id: str, status: str):
        """Toggle workflow active / inactive. Returns updated doc or None."""
        existing = self.get(workflow_id, owner_id)
        if existing is None:
            return None
        now = datetime.utcnow().isoformat() + "Z"
        self._col().document(workflow_id).update({"status": status, "updated_at": now})
        return {**existing, "status": status, "updated_at": now}

    def save_compilation(
        self,
        workflow_id: str,
        owner_id: str,
        compiled_graph: dict,
        graph_hash: str,
        compiled_at: str,
    ) -> dict | None:
        """
        Persist the compiled execution plan and set status to 'active'.

        Returns the updated workflow dict, or None if not found / not authorised.
        """
        existing = self.get(workflow_id, owner_id)
        if existing is None:
            return None
        now = datetime.utcnow().isoformat() + "Z"
        update = {
            "compiled_graph": compiled_graph,
            "graph_hash":     graph_hash,
            "compiled_at":    compiled_at,
            "status":         "active",
            "updated_at":     now,
        }
        self._col().document(workflow_id).update(update)
        return {**existing, **update}

    def list_active(self) -> list:
        """
        Return every active workflow document (any owner).

        Used by the RuntimeManager to restore running executions after a server
        restart.  No owner-scoping — this is an internal server operation.
        """
        docs = self._col().where("status", "==", "active").stream()
        return [d.to_dict() for d in docs]

    def delete(self, workflow_id: str, owner_id: str) -> bool:
        """Delete a workflow. Returns True on success, False if not authorised."""
        existing = self.get(workflow_id, owner_id)
        if existing is None:
            return False
        self._col().document(workflow_id).delete()
        return True


class WorkflowVersion:
    """
    Immutable compiled-graph versions for Fuse workflows.

    Each call to activate_workflow compiles the graph and saves a new version
    document here.  Version documents are NEVER deleted so that historical runs
    can always be linked back to the exact graph that executed them.

    Firestore layout
    ----------------
    fuse_versions/{version_id}
        version_id    : str   — Firestore document ID
        workflow_id   : str
        owner_id      : str   — Firebase UID (for ownership checks / queries)
        graph_hash    : str   — SHA-256 of the compiled graph
        compiled_graph: dict  — full compiled graph dict
        created_at    : ISO-8601 str
    """

    COLLECTION = "fuse_versions"

    def __init__(self, client):
        self.client = client

    def _col(self):
        return self.client.collection(self.COLLECTION)

    def save(
        self,
        workflow_id: str,
        owner_id: str,
        graph_hash: str,
        compiled_graph: dict,
    ) -> dict:
        """
        Persist a new compiled graph version and return the saved document.

        If an identical graph_hash already exists for this workflow, the
        existing version document is returned without creating a duplicate.
        """
        # Deduplicate: if the same graph_hash already exists, reuse it.
        existing = (
            self._col()
            .where("workflow_id", "==", workflow_id)
            .where("graph_hash", "==", graph_hash)
            .limit(1)
            .stream()
        )
        for doc in existing:
            return doc.to_dict()

        now = datetime.utcnow().isoformat() + "Z"
        doc_ref = self._col().document()
        data = {
            "version_id":     doc_ref.id,
            "workflow_id":    workflow_id,
            "owner_id":       owner_id,
            "graph_hash":     graph_hash,
            "compiled_graph": compiled_graph,
            "created_at":     now,
        }
        doc_ref.set(data)
        return data

    def get(self, version_id: str) -> dict | None:
        """Fetch a version document by ID."""
        doc = self._col().document(version_id).get()
        return doc.to_dict() if doc.exists else None

    def list_for_workflow(self, workflow_id: str, owner_id: str) -> list[dict]:
        """Return all versions for a workflow, newest first."""
        docs = (
            self._col()
            .where("workflow_id", "==", workflow_id)
            .where("owner_id", "==", owner_id)
            .order_by("created_at", direction=firestore.Query.DESCENDING)
            .stream()
        )
        return [d.to_dict() for d in docs]


class WorkflowRun:
    """
    Execution run records and per-node logs for Fuse workflows.

    Run documents and log documents are NEVER deleted — they serve as an
    immutable audit trail and will be used for future pricing calculations.

    Firestore layout
    ----------------
    fuse_runs/{run_id}                       ← one doc per trigger
        run_id          : str
        workflow_id     : str
        owner_id        : str
        version_id      : str | None         ← links to fuse_versions
        trigger_type    : "webhook" | "schedule" | "manual"
        status          : "running" | "success" | "failed"
        started_at      : ISO-8601 str
        finished_at     : ISO-8601 str | None
        duration_ms     : int | None
        trigger_data    : dict
        node_count      : int
        nodes_succeeded : int
        nodes_failed    : int
        error           : str | None         ← top-level error (before any node ran)

    fuse_run_logs/{log_id}                   ← one doc per node execution
        log_id          : str
        run_id          : str
        workflow_id     : str
        owner_id        : str
        node_id         : str
        node_type       : str
        node_label      : str
        status          : "success" | "error" | "skipped"
        started_at      : ISO-8601 str
        finished_at     : ISO-8601 str
        duration_ms     : int
        output          : dict | None
        error           : str | None         ← exception message (if status == "error")
        error_type      : str | None         ← exception class name
    """

    RUNS_COLLECTION = "fuse_runs"
    LOGS_COLLECTION = "fuse_run_logs"

    def __init__(self, client):
        self.client = client

    def _runs(self):
        return self.client.collection(self.RUNS_COLLECTION)

    def _logs(self):
        return self.client.collection(self.LOGS_COLLECTION)

    # ── Run lifecycle ──────────────────────────────────────────────────────────

    def create_run(
        self,
        run_id: str,
        workflow_id: str,
        owner_id: str,
        version_id: str | None,
        trigger_type: str,
        trigger_data: dict,
    ) -> dict:
        """
        Write a new run document with status='running'.
        Returns the created document dict.
        """
        now = datetime.utcnow().isoformat() + "Z"
        data = {
            "run_id":          run_id,
            "workflow_id":     workflow_id,
            "owner_id":        owner_id,
            "version_id":      version_id,
            "trigger_type":    trigger_type,
            "status":          "running",
            "started_at":      now,
            "finished_at":     None,
            "duration_ms":     None,
            "trigger_data":    trigger_data,
            "node_count":      0,
            "nodes_succeeded": 0,
            "nodes_failed":    0,
            "error":           None,
        }
        self._runs().document(run_id).set(data)
        return data

    def finish_run(
        self,
        run_id: str,
        status: str,
        node_count: int,
        nodes_succeeded: int,
        nodes_failed: int,
        started_at: str,
        error: str | None = None,
    ) -> None:
        """
        Mark a run as finished.  Computes duration from started_at → now.
        """
        from datetime import timezone
        now_dt = datetime.now(timezone.utc)
        finished_at = now_dt.isoformat().replace("+00:00", "Z")

        # Compute duration in milliseconds
        try:
            start_dt = datetime.fromisoformat(started_at.rstrip("Z")).replace(
                tzinfo=timezone.utc
            )
            duration_ms = int((now_dt - start_dt).total_seconds() * 1000)
        except Exception:
            duration_ms = None

        self._runs().document(run_id).update({
            "status":          status,
            "finished_at":     finished_at,
            "duration_ms":     duration_ms,
            "node_count":      node_count,
            "nodes_succeeded": nodes_succeeded,
            "nodes_failed":    nodes_failed,
            "error":           error,
        })

    def write_node_log(
        self,
        run_id: str,
        workflow_id: str,
        owner_id: str,
        node_id: str,
        node_type: str,
        node_label: str,
        status: str,
        started_at: str,
        finished_at: str,
        duration_ms: int,
        output: dict | None = None,
        error: str | None = None,
        error_type: str | None = None,
    ) -> str:
        """
        Write a node execution log document.  Returns the generated log_id.
        """
        doc_ref = self._logs().document()
        data = {
            "log_id":      doc_ref.id,
            "run_id":      run_id,
            "workflow_id": workflow_id,
            "owner_id":    owner_id,
            "node_id":     node_id,
            "node_type":   node_type,
            "node_label":  node_label,
            "status":      status,
            "started_at":  started_at,
            "finished_at": finished_at,
            "duration_ms": duration_ms,
            "output":      output,
            "error":       error,
            "error_type":  error_type,
        }
        doc_ref.set(data)
        return doc_ref.id

    # ── Queries ────────────────────────────────────────────────────────────────

    def list_runs_for_workflow(
        self,
        workflow_id: str,
        owner_id: str,
        limit: int = 20,
        after_started_at: str | None = None,
        after_run_id: str | None = None,
    ) -> dict:
        """
        Return the most recent runs for a workflow, newest first.

        Cursor pagination: pass after_started_at + after_run_id (values from
        the last document of the previous page) to fetch the next page.

        Returns:
            { "items": [...], "next_cursor": { "after_started_at": ..., "after_run_id": ... } | None }
        """
        q = (
            self._runs()
            .where("workflow_id", "==", workflow_id)
            .where("owner_id", "==", owner_id)
            .order_by("started_at", direction=firestore.Query.DESCENDING)
        )

        if after_started_at and after_run_id:
            cursor_doc = self._runs().document(after_run_id).get()
            if cursor_doc.exists:
                q = q.start_after(cursor_doc)

        docs = list(q.limit(limit + 1).stream())
        has_more = len(docs) > limit
        items = [d.to_dict() for d in docs[:limit]]

        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = {"after_started_at": last["started_at"], "after_run_id": last["run_id"]}

        return {"items": items, "next_cursor": next_cursor}

    def get_run(self, run_id: str, owner_id: str) -> dict | None:
        """
        Fetch a single run document.
        Returns None if not found or the owner_id does not match.
        """
        doc = self._runs().document(run_id).get()
        if not doc.exists:
            return None
        data = doc.to_dict()
        if data.get("owner_id") != owner_id:
            return None
        return data

    def list_logs_for_run(
        self,
        run_id: str,
        owner_id: str,
        limit: int = 25,
        after_started_at: str | None = None,
        after_log_id: str | None = None,
    ) -> dict:
        """
        Return node execution logs for a run, ordered by started_at ascending.

        Cursor pagination: pass after_started_at + after_log_id (values from
        the last document of the previous page) to fetch the next page.

        Returns:
            { "items": [...], "next_cursor": { "after_started_at": ..., "after_log_id": ... } | None }
        """
        q = (
            self._logs()
            .where("run_id", "==", run_id)
            .where("owner_id", "==", owner_id)
            .order_by("started_at", direction=firestore.Query.ASCENDING)
        )

        if after_started_at and after_log_id:
            cursor_doc = self._logs().document(after_log_id).get()
            if cursor_doc.exists:
                q = q.start_after(cursor_doc)

        docs = list(q.limit(limit + 1).stream())
        has_more = len(docs) > limit
        items = [d.to_dict() for d in docs[:limit]]

        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = {"after_started_at": last["started_at"], "after_log_id": last["log_id"]}

        return {"items": items, "next_cursor": next_cursor}


class DB:
    def __init__(self):
        cred = credentials.Certificate(json.loads(CONFIG.FIREBASE_CREDENTIALS))
        firebase_admin.initialize_app(cred)
        self.client = firestore.client()

        self.chat     = Chat(self.client)
        self.user     = User(self.client)
        self.msg      = Msg(self.client)
        self.file     = File(self.client)
        self.analytics = Analytics(self.client)
        self.workflow  = Workflow(self.client)
        self.workflow_version = WorkflowVersion(self.client)
        self.workflow_run     = WorkflowRun(self.client)

db = DB()