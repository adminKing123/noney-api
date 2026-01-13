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


db = DB()