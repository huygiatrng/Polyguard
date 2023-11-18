from flask import Flask, Response, jsonify, request, render_template
import cv2
from modeldetector import detector_generator, set_alert_callback, set_camera_identifier
from PIL import Image
import numpy as np
import torch
import logging
from flask_cors import CORS
import requests
import firebase_admin
from firebase_admin import credentials, firestore
import string
import random
import hashlib
import os
from flask.helpers import send_file
import pytextnow

# SMS constants
SID_COOKIE = "s%3AWAfpXLUBHNpqRHG7jNfEyZClIA8bNZx4.2AHTyOQpZchokzVuZTYYXkKtjIJXwCh1qyVXSC6fbm8"
CSRF_COOKIE = "s%3AbGmw_D0jKk3n71GnYsiiZpJM.HVXFL3UqLr1CT2s%2B4wruikAvGPKFvzNcdw7Dh1yPcoE"
SMS_client = pytextnow.Client("redrawn101", sid_cookie=SID_COOKIE, csrf_cookie=CSRF_COOKIE)
# Image Save Debounce
debounce = False
last_alert_time = None
# How long between each alert is allowed (in seconds)
debounce_time = 60


def generate_random_password(length=8):
    """Generate a random password with numeric digits."""
    digits = string.digits
    return ''.join(random.choice(digits) for i in range(length))


PASSWORD = generate_random_password()


def hash_password(password):
    """Hash a password using SHA-256."""
    sha_signature = hashlib.sha256(password.encode()).hexdigest()
    return sha_signature


def send_intrusion_alert(camera_id):
    # Find all user_ids associated with the camera_id
    print("Sending intrusion alert")
    user_camera_refs = db.collection('user_cameras').where('camera_id', '==', camera_id).stream()
    print(user_camera_refs)
    for user_camera_ref in user_camera_refs:
        user_camera_data = user_camera_ref.to_dict()
        # Check if the alert field is True
        print(f"Alert: {user_camera_data.get('alert')}")
        if user_camera_data.get('alert', False):
            user_id = user_camera_data.get('user_id')
            # Find the phone number for each user_id
            phone_number_ref = db.collection('phonenumbers').where('user_id', '==', user_id).get()
            if phone_number_ref:
                phone_number_data = phone_number_ref[0].to_dict()
                country_code = phone_number_data.get('countrycode')
                phone_number = phone_number_data.get('phonenumber')
                # Send SMS using your SMS service
                print(f"To the phone number {country_code} {phone_number}")
                send_sms(country_code, phone_number, "Intrusion detected on camera: " + camera_id)


def send_sms(country_code, phone_number, message):
    SMS_client.send_sms(f"{country_code}{phone_number}", message)


def get_ngrok_url():
    try:
        # Query ngrok API to get public URL
        tunnels = requests.get('http://localhost:4040/api/tunnels').json()['tunnels']
        for tunnel in tunnels:
            if tunnel['proto'] == 'https':
                return tunnel['public_url']
    except Exception as e:
        logging.error(f"Error fetching ngrok URL: {str(e)}")
        return None


NGROK_URL = get_ngrok_url()

cap = cv2.VideoCapture(0)
model = torch.hub.load('yolov5', 'custom', 'yolov5n.pt', source='local', force_reload=True)
model.conf = 0.5  # confidence threshold (0-1)
model.iou = 0.45  # NMS IoU threshold (0-1)
# Load class names
with open('model/classnames.txt', 'r') as f:
    class_names = [line.strip() for line in f]

if not firebase_admin._apps:
    cred = credentials.Certificate('FirestoreDB/polyguard-43608-firebase-adminsdk-oz458-f8bc3bb9e4.json')
    default_app = firebase_admin.initialize_app(cred)
# firebase_admin.initialize_app(cred)
db = firestore.client()

app = Flask(__name__)
# CORS(app)
cors = CORS(app, resources={
    r"/video/*": {"origins": "*", "methods": ["GET"], "allow_headers": ["Content-Type", "Authorization"]}})

logging.basicConfig(level=logging.INFO)


# Function to generate a unique identifier
def generate_identifier(length=8):
    letters_and_digits = string.ascii_letters + string.digits
    return ''.join(random.choice(letters_and_digits) for i in range(length))


# Function to check if the identifier exists in Firestore
def identifier_exists(identifier):
    camera_ref = db.collection('cameras').document(identifier)
    return camera_ref.get().exists


# Function to register the camera
def register_camera():
    # Check for existing camera with the same ngrok URL
    cameras_ref = db.collection('cameras')
    query = cameras_ref.where('ngrok_url', '==', NGROK_URL).limit(1)
    cameras = query.stream()

    for camera in cameras:
        # Camera with the same ngrok URL found
        camera_id = camera.id
        camera_ref = db.collection('cameras').document(camera_id)
        camera_ref.update({
            'ngrok_url': NGROK_URL,
            'link_password': hash_password(PASSWORD),
            # ... update any other data as needed ...
        })
        return camera_id

    # If no existing camera is found with the same ngrok URL, create a new one
    identifier = generate_identifier()

    # Keep generating a new identifier until we find a unique one
    while identifier_exists(identifier):
        identifier = generate_identifier()

    camera_ref = db.collection('cameras').document(identifier)
    camera_ref.set({
        'ngrok_url': NGROK_URL,
        'link_password': hash_password(PASSWORD),
        # ... any other data you want to store ...
    })

    return identifier


def generate_frames():
    for frame in detector_generator(cap, model, class_names, 640):
        ret, buffer = cv2.imencode('.jpg', frame)
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')


@app.route('/')
def home():
    return render_template('index.html', ngrok_url=NGROK_URL)


@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/save_polygon', methods=['POST'])
def save_polygon():
    try:
        points = request.json.get('points', [])
        saved_points = []
        with open('polygon.txt', 'w') as f:
            for point in points:
                # Ensure values are integers
                x = int(round(point['x']))
                y = int(round(point['y']))
                f.write(f"{x},{y}\n")
                saved_points.append({'x': x, 'y': y})

        return jsonify(success=True, points=saved_points)

    except Exception as e:
        logging.error(f"Error saving polygon: {str(e)}")
        return jsonify(success=False)


@app.route('/clear_polygon', methods=['POST'])
def clear_polygon():
    try:
        with open('polygon.txt', 'w') as f:
            f.write('')  # Overwrite the file with empty data
        return jsonify(success=True)

    except Exception as e:
        logging.error(f"Error clearing polygon data: {str(e)}")
        return jsonify(success=False)


@app.route('/update_centroid_y_ratio', methods=['POST'])
def update_centroid_y_ratio():
    try:
        new_ratio = request.json.get('y_ratio')
        if new_ratio is None or not (0 <= new_ratio <= 100):
            return jsonify(success=False, message="Invalid y-ratio value. It must be between 0 and 100.")

        with open('centroid.txt', 'w') as f:
            f.write(str(new_ratio))

        return jsonify(success=True, y_ratio=new_ratio)

    except Exception as e:
        logging.error(f"Error updating centroid y-ratio: {str(e)}")
        return jsonify(success=False, message=str(e))


@app.route('/get_centroid_y_ratio', methods=['GET'])
def get_centroid_y_ratio():
    try:
        with open('centroid.txt', 'r') as file:
            y_ratio = int(file.read().strip())
            return jsonify(success=True, y_ratio=y_ratio)

    except Exception as e:
        logging.error(f"Error fetching centroid y-ratio: {str(e)}")
        return jsonify(success=False, message=str(e))


@app.route('/favicon/.ico')
def favicon():
    return Response(status=204)


@app.route('/list_videos')
def list_videos():
    base_path = 'captured_video'
    video_list = {}
    for date_folder in os.listdir(base_path):
        folder_path = os.path.join(base_path, date_folder)
        if os.path.isdir(folder_path):
            video_list[date_folder] = os.listdir(folder_path)
    return jsonify(video_list)


@app.route('/video/<date>/<filename>')
def serve_video(date, filename):
    video_path = os.path.join('captured_video', date, filename)
    print(video_path)
    if os.path.exists(video_path):
        print("sent video")
        return send_file(video_path, mimetype='video/mp4', conditional=True)
    else:
        print("Video not found")
        return "Video not found", 404


@app.route('/delete_video/<date>/<filename>', methods=['POST'])
def delete_video(date, filename):
    # Optional: Add authentication or authorization checks here
    video_path = os.path.join('captured_video', date, filename)
    if os.path.exists(video_path):
        try:
            os.remove(video_path)
            return jsonify(success=True, message="Video deleted successfully.")
        except Exception as e:
            logging.error(f"Error deleting video: {str(e)}")
            return jsonify(success=False, message="Error deleting video."), 500
    else:
        return jsonify(success=False, message="Video not found."), 404


if __name__ == '__main__':
    # Register the camera and get the identifier
    identifier = register_camera()
    set_alert_callback(send_intrusion_alert)
    set_camera_identifier(identifier)
    # Print the password and identifier
    print("Camera Identifier:", identifier)
    print("Camera Password:", PASSWORD)

    # Start the Flask app
    app.run(host='0.0.0.0', port=5001, debug=True, use_reloader=False)
