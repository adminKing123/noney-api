import firebase_admin
from firebase_admin import credentials, firestore, auth
import json
from config import CONFIG
from datetime import datetime

class User:
    def __init__(self, client):
        self.client = client
    
    def authenticate(self, token):
        decoded = auth.verify_id_token(token)
        return decoded

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
      usage/                                ← collection
        {chat_id}                           ← document  (chat-level aggregate)
          chat_id      : str
          model        : str                (AURA model ID of last generation)
          total_tokens : { input, output, total }
          total_cost_usd : float
          generation_count : int
          created_at   : ISO-8601 str       (first generation timestamp)
          updated_at   : ISO-8601 str       (latest generation timestamp)

          messages/                         ← sub-collection
            {message_id}                    ← document  (per-message record)
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
           — safe to re-run on retry because it uses set(), not add()).
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

            # ── 1. Per-message usage document ──────────────────────────────────
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

            # ── 2. Chat-level aggregate document (atomic dot-notation increments) ──
            # Dots in model IDs (e.g. noney-1.0-fast-20241001) are replaced with
            # underscores so they are safe to use as Firestore map keys via
            # dot-notation. The original model ID is stored in model_id alongside.
            safe = model.replace(".", "_")

            chat_ref = user_usage_col.document(chat_id)
            increment_data = {
                # ── Chat-level totals (universal across all model types) ──────
                "total_tokens.input":      firestore.Increment(inp),
                "total_tokens.output":     firestore.Increment(out),
                "total_tokens.total":      firestore.Increment(total),
                "total_images_generated":  firestore.Increment(images_generated),
                "total_cost_usd":          firestore.Increment(cost),
                "generation_count":        firestore.Increment(1),
                "updated_at":              now_iso,
                # ── Per-model breakdown within this chat ──────────────────────
                # Multiple models can be used in a single chat; each gets its
                # own sub-map. generation_type is a plain string assignment
                # (not an Increment) — it is idempotent for the same model.
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
                # Document does not exist yet — initialise it, then apply increments.
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


class DB:
    def __init__(self):
        cred = credentials.Certificate(json.loads(CONFIG.FIREBASE_CREDENTIALS))
        firebase_admin.initialize_app(cred)
        self.client = firestore.client()

        self.chat = Chat(self.client)
        self.user = User(self.client)
        self.msg = Msg(self.client)
        self.file = File(self.client)
        self.analytics = Analytics(self.client)

db = DB()