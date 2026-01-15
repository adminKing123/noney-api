import firebase_admin
from firebase_admin import credentials, firestore, auth
import json
from config import CONFIG

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


class Msg:
    def __init__(self, client):
        self.client = client

    def get_new_msg(self, id):
        data = {
            "id": id
        }
        return MsgEntity(data)

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

    def get_messages(self, userId, chatId, limit=CONFIG.GEMINI_MESSAGE_LIMIT, should_yeild=False):
        messages_ref = self.client.collection("chats").document(chatId).collection("messages").order_by("created_at", direction=firestore.Query.ASCENDING).limit(limit)
        if should_yeild:
            messages_docs = messages_ref.stream()
            for msg in messages_docs:
                yield msg.to_dict()
        else:
            messages_docs = messages_ref.stream()
            return [msg.to_dict() for msg in messages_docs]

class DB:
    def __init__(self):
        cred = credentials.Certificate(json.loads(CONFIG.FIREBASE_CREDENTIALS))
        firebase_admin.initialize_app(cred)
        self.client = firestore.client()

        self.chat = Chat(self.client)
        self.user = User(self.client)
        self.msg = Msg(self.client)


db = DB()