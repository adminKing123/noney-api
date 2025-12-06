import firebase_admin
from firebase_admin import credentials, firestore, db

# Path to your downloaded JSON key
cred = credentials.Certificate("firebase_key.json")

# Initialize app (Firestore example)
firebase_admin.initialize_app(cred)
db = firestore.client()