from . import db
from flask_login import UserMixin


class User:
    def __init__(self):
        self.cameras = []

    @staticmethod
    def create(email, username, name, password):
        _, doc_ref = db.collection('users').add({
            'email': email,
            'username': username,
            'name': name,
            'password': password
        })
        # After adding, get the newly created user and return it
        return db.collection('users').document(doc_ref.id).get()

    @staticmethod
    def get_by_email(email):
        return db.collection('users').where('email', '==', email).get()

    @staticmethod
    def get_by_id(user_id):
        return db.collection('users').document(user_id).get()

    @staticmethod
    def get_by_username(username):
        return db.collection('users').where('username', '==', username).get()

    @staticmethod
    def add_camera(user_id, camera_id, location, nickname):
        user_camera_ref = db.collection('user_cameras').add({
            'user_id': user_id,
            'camera_id': camera_id,
            'location': location,
            'nickname': nickname
        })

    @staticmethod
    def get_cameras(user_id):
        camera_refs = db.collection('user_cameras').where('user_id', '==', user_id).stream()
        cameras = [db.collection('cameras').document(ref.get('camera_id')).get() for ref in camera_refs]
        return cameras

    @property
    def cameras(self):
        return self._cameras  # or some other internal attribute

    @cameras.setter
    def cameras(self, value):
        self._cameras = value


class Camera:
    @staticmethod
    def create(camera_url):
        _, doc_ref = db.collection('cameras').add({
            'camera_url': camera_url,
        })
        # After adding, get the newly created user and return it
        return db.collection('cameras').document(doc_ref.id).get()

    @staticmethod
    def get_by_url(camera_url):
        return db.collection('cameras').where('camera_url', '==', camera_url).get()

    @staticmethod
    def get_by_id(camera_id):
        return db.collection('cameras').document(camera_id).get()


class UserWrapper(UserMixin):
    def __init__(self, user_doc):
        self._user_doc = user_doc

    @property
    def user_doc(self):
        return self._user_doc

    def get_inner_user(self):
        return self._user

    @property
    def id(self):
        return self.user_doc.id

    @property
    def email(self):
        return self.user_doc.get('email')

    @property
    def password(self):
        return self.user_doc.get('password')

    @property
    def is_active(self):
        return True

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    @property
    def cameras(self):
        return User.get_cameras(self.id)

    def get_id(self):
        return self.user_doc.id
