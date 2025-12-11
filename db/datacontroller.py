import firebase_admin
from firebase_admin import credentials, firestore, auth
import json
import os

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
        chat_ref = self.client.collection("users").document(userId).collection("chats").document(chatId)
        self.client.recursive_delete(chat_ref)

        chat_ref = self.client.collection("users").document(userId).collection("drafts").document(chatId)
        self.client.recursive_delete(chat_ref)

class DB:
    def __init__(self):
        cred = credentials.Certificate(json.loads(os.getenv("FIREBASE_CREDENTIALS")))
        firebase_admin.initialize_app(cred)
        self.client = firestore.client()

        self.chat = Chat(self.client)
        self.user = User(self.client)


db = DB()