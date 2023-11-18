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
    print(camera_snapshot.to_dict())
    if not camera_snapshot or not camera_snapshot.exists:
        return "Camera not found", 404

    camera_data = camera_snapshot.to_dict()
    print(camera_data)

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

    print(camera_url)

    response = requests.get(f'{camera_url}/video_feed', stream=True)

    def generate():
        for chunk in response.iter_content(chunk_size=8192):
            yield chunk

    return Response(generate(), content_type=response.headers['Content-Type'])


def hash_password(password):
    """Hash a password using SHA-256."""
    sha_signature = hashlib.sha256(password.encode()).hexdigest()
    return sha_signature


@views.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    # Fetch current user's phone number and country code
    phone_data = db.collection('phonenumbers').where('user_id', '==', current_user.id).get()
    if phone_data:
        current_phone_number = phone_data[0].to_dict()['phonenumber']
        current_country_code = phone_data[0].to_dict()['countrycode']
    else:
        current_phone_number, current_country_code = None, None

    if request.method == 'POST':
        country_code = request.form.get('countrycode')
        phone_number = request.form.get('phonenumber')

        # Prepend '+' to the country code
        full_country_code = f"+{country_code}" if country_code else None

        # Update logic
        if full_country_code and phone_number:
            db.collection('phonenumbers').document(phone_data[0].id).update({
                'countrycode': full_country_code,
                'phonenumber': phone_number
            })
            flash("Phone number and country code updated successfully.", category='success')

            # Update the variables to reflect the new values
            current_phone_number = phone_number
            current_country_code = full_country_code

    return render_template('settings.html', current_phone_number=current_phone_number,
                           current_country_code=current_country_code.replace('+', ''))


@views.route('/add_phonenumber', methods=['POST'])
@login_required
def add_phonenumber():
    countrycode = request.form['countrycode']
    phonenumber = request.form['phonenumber']

    user_phone_data = {
        'user_id': current_user.id,
        'countrycode': countrycode,
        'phonenumber': phonenumber
    }

    in_db = db.collection('phonenumbers').where('user_id', '==', current_user.id).get()
    if in_db:
        flash("A phone number already exists under this user!")
    else:
        db.collection('phonenumbers').add(user_phone_data)

    return redirect(url_for('views.home'))


@views.route('/add_camera', methods=['POST'])
@login_required
def add_camera():
    identifier = request.form['identifier']
    link_password = request.form['link_password']
    location = request.form['location']
    nickname = request.form.get('nickname', '')  # Optional

    # Check if the camera with the provided identifier exists in the database
    camera_snapshot = Camera.get_by_id(identifier)
    if not camera_snapshot or not camera_snapshot.exists:
        flash("The camera with this identifier does not exist.", category='error')
        return redirect(request.referrer)  # Redirect back to the same page

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
        'link_password': hashed_password, # Storing hashed link password
        'alert': False
    }
    db.collection('user_cameras').add(user_camera_data)
    return redirect(url_for('views.home'))


@views.route('/delete_camera/<string:camera_id>', methods=['POST'])
@login_required
def delete_camera(camera_id):
    print(f"Deleting connect with {camera_id}")
    # Extract camera IDs from the DocumentSnapshot list
    camera_ids_for_current_user = [camera.id for camera in current_user.cameras]

    # Check if the camera_id exists in the extracted IDs
    if camera_id not in camera_ids_for_current_user:
        print("You don't have permission to delete this camera.")
        return "You don't have permission to delete this camera.", 403

    # Remove the camera-user association
    db.collection('user_cameras').where('user_id', '==', current_user.id).where('camera_id', '==', camera_id).get()[
        0].reference.delete()

    return redirect(url_for('views.home'))

@views.route('/toggle_alert/<string:camera_id>', methods=['POST'])
@login_required
def toggle_alert(camera_id):
    # Ensure the user has access to the camera
    if not check_camera_access_for_user(camera_id):
        flash("You do not have access to this camera.", category='error')
        return redirect(url_for('views.home'))

    # Fetch the user_camera document
    user_camera_ref = db.collection('user_cameras').where('user_id', '==', current_user.id).where('camera_id', '==', camera_id).limit(1).get()

    if not user_camera_ref:
        flash("Camera not found.", category='error')
        return redirect(url_for('views.home'))

    # Toggle the alert status
    current_alert_status = user_camera_ref[0].to_dict().get('alert', False)
    new_alert_status = not current_alert_status

    # Update the alert field in Firestore
    user_camera_ref[0].reference.update({'alert': new_alert_status})

    flash(f"Alert status for camera {camera_id} set to {'on' if new_alert_status else 'off'}.", category='success')
    return jsonify(success=True, new_status=new_alert_status)

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


@views.route('/api/update_centroid_y_ratio/<string:camera_id>', methods=['POST'])
@login_required
def update_centroid_y_ratio(camera_id):
    if not check_camera_access_for_user(camera_id):
        return jsonify(success=False, message="Invalid link password or no access"), 403

    new_ratio = request.json.get('y_ratio')
    if new_ratio is None:
        return jsonify(success=False, message="Y-ratio value is missing."), 400

    try:
        new_ratio = int(new_ratio)
    except ValueError:
        return jsonify(success=False, message="Invalid y-ratio value. It must be a number."), 400

    if not (0 <= new_ratio <= 100):
        return jsonify(success=False, message="Invalid y-ratio value. It must be between 0 and 100."), 400

    camera = Camera.get_by_id(camera_id)
    if not camera:
        return jsonify(success=False, message="Unknown camera ID"), 404

    camera_data = camera.to_dict()
    camera_url = camera_data.get('ngrok_url')
    response = requests.post(f'{camera_url}/update_centroid_y_ratio', json={'y_ratio': new_ratio})

    # Return whatever response you get from the Raspberry Pi
    return response.content, response.status_code


@views.route('/api/get_centroid_y_ratio/<string:camera_id>', methods=['GET'])
@login_required
def get_centroid_y_ratio(camera_id):
    # Check the link password and camera access
    if not check_camera_access_for_user(camera_id):
        return jsonify(success=False, message="Invalid link password or no access"), 403

    camera = Camera.get_by_id(camera_id)
    if not camera:
        return jsonify(success=False, message="Unknown camera ID"), 404

    camera_data = camera.to_dict()
    camera_url = camera_data.get('ngrok_url')

    try:
        # Sending a request to Raspberry Pi to get the current centroid y-ratio
        response = requests.get(f'{camera_url}/get_centroid_y_ratio')
        if response.status_code == 200:
            # Assuming the Raspberry Pi returns JSON with a 'y_ratio' field
            y_ratio_data = response.json()
            return jsonify(success=True, y_ratio=y_ratio_data.get('y_ratio'))
        else:
            return jsonify(success=False, message="Failed to get centroid y-ratio from camera"), response.status_code
    except requests.RequestException as e:
        return jsonify(success=False, message=str(e)), 500


@views.route('/script.js')
@login_required
def script():
    # Fetch only the cameras that the current user has added
    user_cameras = current_user.cameras
    user_camera_urls = {camera.id: (camera.to_dict().get('camera_url') if camera.exists else '') for camera in
                        user_cameras}
    return render_template('script.js.html', user_cameras=user_cameras, camera_urls=user_camera_urls)


@views.route('/api/list_videos/<string:camera_id>', methods=['GET'])
@login_required
def api_list_videos(camera_id):
    if not check_camera_access_for_user(camera_id):
        return jsonify(success=False, message="No access"), 403

    camera = Camera.get_by_id(camera_id)
    if not camera:
        return jsonify(success=False, message="Unknown camera ID"), 404

    camera_data = camera.to_dict()
    camera_url = camera_data.get('ngrok_url')

    try:
        response = requests.get(f'{camera_url}/list_videos')
        if response.status_code == 200:
            video_list = response.json()
            print(video_list)
            return jsonify(success=True, video_list=video_list)
        else:
            return jsonify(success=False, message="Failed to list videos"), response.status_code
    except requests.RequestException as e:
        return jsonify(success=False, message=str(e)), 500


@views.route('/api/serve_video/<string:camera_id>/<string:date>/<string:filename>', methods=['GET'])
@login_required
def api_serve_video(camera_id, date, filename):
    if not check_camera_access_for_user(camera_id):
        return "No access", 403

    camera = Camera.get_by_id(camera_id)
    if not camera:
        return "Unknown camera ID", 404

    camera_data = camera.to_dict()
    camera_url = camera_data.get('ngrok_url')

    # Construct the correct URL to fetch the video from the Raspberry Pi server
    video_url = f'{camera_url}/video/{date}/{filename}'

    response = requests.get(video_url, stream=True)

    if response.status_code == 200:
        def generate():
            for chunk in response.iter_content(chunk_size=8192):
                yield chunk

        return Response(generate(), content_type=response.headers['Content-Type'])
    else:
        return "Video not found", 404


@views.route('/playback_video')
@login_required
def playback_video():
    user_cameras = current_user.cameras
    user_camera_data = []

    # Query user_cameras collection for current user's cameras
    user_cameras_data = db.collection('user_cameras').where('user_id', '==', current_user.id).stream()

    # Convert query results to a dictionary for easier access
    user_cameras_dict = {camera_doc.to_dict()['camera_id']: camera_doc.to_dict() for camera_doc in user_cameras_data}

    # Merge data from user_cameras with camera data
    for camera_snapshot in user_cameras:
        if camera_snapshot.exists:
            camera_id = camera_snapshot.id
            camera_data = camera_snapshot.to_dict()

            # Include the camera ID
            camera_data['id'] = camera_id

            # Include nickname and location if available in user_cameras
            if camera_id in user_cameras_dict:
                camera_data['nickname'] = user_cameras_dict[camera_id].get('nickname', 'Unknown')
                camera_data['location'] = user_cameras_dict[camera_id].get('location', 'Unknown Location')

            user_camera_data.append(camera_data)

    return render_template('playback_video.html', user_cameras=user_camera_data)


@views.route('/api/delete_video/<string:camera_id>/<string:date>/<string:filename>', methods=['POST'])
@login_required
def api_delete_video(camera_id, date, filename):
    if not check_camera_access_for_user(camera_id):
        flash("No access to this camera", category='error')
        return redirect(url_for('views.playback_video'))

    camera = Camera.get_by_id(camera_id)
    if not camera:
        flash("Unknown camera ID", category='error')
        return redirect(url_for('views.playback_video'))

    camera_data = camera.to_dict()
    camera_url = camera_data.get('ngrok_url')

    try:
        response = requests.post(f'{camera_url}/delete_video/{date}/{filename}')
        if response.status_code == 200:
            flash("Video deleted successfully", category='success')
        else:
            flash("Failed to delete video", category='error')
    except requests.RequestException as e:
        flash(str(e), category='error')

    return redirect(url_for('views.playback_video'))


@views.route('/')
@login_required
def home():
    user_cameras = current_user.cameras
    user_camera_urls = {camera.id: (camera.to_dict().get('camera_url') if camera.exists else '') for camera in user_cameras}

    # Create a dictionary mapping camera IDs to their alert status
    user_cameras_dict = {}
    user_cameras_data = db.collection('user_cameras').where('user_id', '==', current_user.id).stream()
    for camera_doc in user_cameras_data:
        camera_data = camera_doc.to_dict()
        user_cameras_dict[camera_data['camera_id']] = camera_data.get('alert', False)

    return render_template('index.html', user_cameras=user_camera_urls, user_cameras_dict=user_cameras_dict, camera_urls=user_camera_urls)
