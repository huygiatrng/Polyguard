from flask import Flask
from os import path
from flask_login import LoginManager
import firebase_admin
from firebase_admin import credentials, firestore

# Initialize Firebase
cred = credentials.Certificate('FirestoreDB/DB.json')
firebase_admin.initialize_app(cred)
db = firestore.client()

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'hjshjhdjah kjshkjdhjs'
    app.config["ALLOWED_IMAGE_EXTENSIONS"] = ["PNG", "JPG", "JPEG", "GIF"]

    from .views import views
    from .auth import auth

    app.register_blueprint(views, url_prefix='/')
    app.register_blueprint(auth, url_prefix='/')

    # No need to import models for Firestore like in SQLAlchemy
    from .models import User, Camera, UserWrapper

    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(id):
        user_doc = User.get_by_id(id)
        if user_doc.exists:  # Check if the document exists
            return UserWrapper(user_doc)
        return None

    return app
