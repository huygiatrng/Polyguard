from flask import Blueprint, render_template, jsonify, Response, request, redirect, url_for, session, flash
from flask_login import login_user, login_required, LoginManager, logout_user, current_user
from .models import Camera, User, UserWrapper
from bcrypt import hashpw, gensalt
from . import db
import requests
import types
import hashlib

views = Blueprint('views', __name__)


def check_camera_access_for_user(camera_id):
    # Fetch link data from the `user_cameras` collection
    link_ref = db.collection('user_cameras').where('user_id', '==', current_user.id).where('camera_id', '==',
                                                                                           camera_id).get()

    if not link_ref or len(link_ref) == 0:
        return False

    link_data = link_ref[0].to_dict()
    hashed_link_password = link_data.get('link_password')

    # Get the camera data
    camera_snapshot = Camera.get_by_id(camera_id)
    if not camera_snapshot or not camera_snapshot.exists:
        return False

    camera_data = camera_snapshot.to_dict()

    # Check the password from the camera with the user's hashed_link_password
    if camera_data['link_password'] != hashed_link_password:
        return False

    return True


@views.route('/proxy_camera_feed/<string:camera_id>', methods=['GET', 'POST'])
@login_required
def proxy_camera_feed(camera_id):
    link_ref = db.collection('user_cameras').where('user_id', '==', current_user.id).where('camera_id', '==',
                                                                                           camera_id).get()

    if not link_ref or len(link_ref) == 0:
        return "No linkage found between the user and camera", 403

    link_data = link_ref[0].to_dict()
    hashed_link_password = link_data.get('link_password')

    # Get the camera data
    camera_snapshot = Camera.get_by_id(camera_id)
    if not camera_snapshot or not camera_snapshot.exists:
        return "Camera not found", 404

    camera_data = camera_snapshot.to_dict()

    # Check the password from the camera with the user's hashed_link_password
    if camera_data['link_password'] != hashed_link_password:
        print("Invalid link password")
        return "Invalid link password", 403

    # # If the password is valid, store in the session that this user is authenticated for this camera
    # session[f'camera_access_{camera_id}'] = True

    # Fetch camera_data if the session already has access (i.e., the else block was not executed)
    if 'camera_data' not in locals():
        camera_snapshot = Camera.get_by_id(camera_id)
        if not camera_snapshot or not camera_snapshot.exists:
            return "Camera not found", 404
        camera_data = camera_snapshot.to_dict()

    # If the password is valid or session access is granted, continue to proxy the camera feed
    print("Correct password or valid session, start connecting")

    camera_url = camera_data.get('ngrok_url')
    if not camera_url:
        return "Camera URL not found", 404

    response = requests.get(f'{camera_url}/video_feed', stream=True)

    def generate():
        for chunk in response.iter_content(chunk_size=8192):
            yield chunk

    return Response(generate(), content_type=response.headers['Content-Type'])


def hash_password(password):
    """Hash a password using SHA-256."""
    sha_signature = hashlib.sha256(password.encode()).hexdigest()
    return sha_signature


@views.route('/add_camera', methods=['POST'])
@login_required
def add_camera():
    identifier = request.form['identifier']
    link_password = request.form['link_password']
    location = request.form['location']
    nickname = request.form.get('nickname', '')  # Optional

    # Check for duplicate camera identifier for the user
    existing_cameras = db.collection('user_cameras').where('user_id', '==', current_user.id).where('camera_id', '==',
                                                                                                   identifier).get()
    if existing_cameras:
        flash("Failed to add your new camera. Your camera exists in the list.", category='error')
        return redirect(request.referrer)  # Redirect back to the same page

    # Hash the linkage password
    hashed_password = hash_password(link_password)

    # Now, we create a linkage between the user and the camera in the `user_cameras` table (or similar).
    user_camera_data = {
        'user_id': current_user.id,
        'camera_id': identifier,
        'location': location,
        'nickname': nickname,
        'link_password': hashed_password  # Storing hashed link password
    }
    db.collection('user_cameras').add(user_camera_data)

    return redirect(url_for('views.home'))


@views.route('/delete_camera/<string:camera_id>', methods=['POST'])
@login_required
def delete_camera(camera_id):
    # Extract camera IDs from the DocumentSnapshot list
    camera_ids_for_current_user = [camera.id for camera in current_user.cameras]

    # Check if the camera_id exists in the extracted IDs
    if camera_id not in camera_ids_for_current_user:
        return "You don't have permission to delete this camera.", 403

    # Remove the camera-user association
    db.collection('user_cameras').where('user_id', '==', current_user.id).where('camera_id', '==', camera_id).get()[
        0].reference.delete()

    return redirect(url_for('views.home'))


@views.route('/api/save_polygon/<string:camera_id>', methods=['POST'])
@login_required
def save_polygon(camera_id):
    # Check the link password
    if not check_camera_access_for_user(camera_id):
        return jsonify(success=False, message="Invalid link password or no access"), 403

    camera = Camera.get_by_id(camera_id)
    if not camera:
        return jsonify(success=False, message="Unknown camera ID"), 404

    camera_data = camera.to_dict()
    camera_url = camera_data.get('ngrok_url')
    response = requests.post(f'{camera_url}/save_polygon', json=request.json)

    # Return whatever response you get from the Raspberry Pi
    return response.content, response.status_code


@views.route('/api/clear_polygon/<string:camera_id>', methods=['POST'])
@login_required
def clear_polygon(camera_id):
    # Check the link password
    if not check_camera_access_for_user(camera_id):
        return jsonify(success=False, message="Invalid link password or no access"), 403

    camera = Camera.get_by_id(camera_id)
    if not camera:
        return jsonify(success=False, message="Unknown camera ID"), 404

    camera_data = camera.to_dict()
    camera_url = camera_data.get('ngrok_url')
    response = requests.post(f'{camera_url}/clear_polygon')

    # Return whatever response you get from the Raspberry Pi
    return response.content, response.status_code


@views.route('/')
@login_required
def home():
    # Fetch only the cameras that the current user has added
    user_cameras = current_user.cameras
    user_camera_urls = {camera.id: (camera.to_dict().get('camera_url') if camera.exists else '') for camera in
                        user_cameras}

    return render_template('index.html', user_cameras=user_cameras, camera_urls=user_camera_urls)
