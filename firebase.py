import firebase_admin
from firebase_admin import credentials, firestore, db
import json
import os

# Path to your downloaded JSON key
cred = credentials.Certificate(json.loads(os.getenv("FIREBASE_CREDENTIALS")))

# Initialize app (Firestore example)
firebase_admin.initialize_app(cred)
db = firestore.client()