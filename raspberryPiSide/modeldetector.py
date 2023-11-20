import cv2
import torch
import numpy as np
from PIL import Image
import datetime
import os
import pytextnow
import firebase_admin
from firebase_admin import credentials, firestore
import subprocess


cred = credentials.Certificate('FirestoreDB/polyguard-43608-firebase-adminsdk-oz458-f8bc3bb9e4.json')
firebase_admin.initialize_app(cred)
db = firestore.client()

# Color constants
POLYGON_DOT_COLOR = (255, 0, 0)  # Blue
POLYGON_COLOR = (255, 255, 0)  # Yellow
ALARM_TEXT_COLOR = (0, 0, 255)  # Red
TEXT_COLOR = (255, 255, 255)  # White

# Image Save Debounce
debounce = False
last_alert_time = None
# How long between each alert is allowed (in seconds)
debounce_time = 60

camera_identifier = None
alert_callback = None


def set_camera_identifier(identifier):
    global camera_identifier
    camera_identifier = identifier

def set_alert_callback(callback):
    global alert_callback
    alert_callback = callback


def detector_generator(cap, model, class_names, size_to_resize=224):
    points = []
    centroid_y_ratio = load_centroid_y_ratio()  # Load the centroid Y position ratio
    recording = False
    last_detection_time = None
    start_time = None
    cooldown_start_time = None
    video_writer = None
    video_filename = None
    frame_count = 0

    while True:
        ret, original_frame = cap.read()
        points = load_polygon_points()
        centroid_y_ratio = load_centroid_y_ratio()  # Reload the centroid Y position ratio for each frame

        if not ret:
            print("Error reading frame")
            continue  # Continue to next iteration instead of breaking

        original_frame = cv2.flip(original_frame, 1)  # Flip horizontally
        frame_resized = cv2.resize(original_frame, (size_to_resize, size_to_resize))

        # Inference
        results = model(frame_resized, size=size_to_resize)
        preds = results.xyxy[0].cpu().numpy()  # Get the detection results

        detected_inside_polygon = False
        for *xyxy, conf, cls in preds:
            x_ratio = original_frame.shape[1] / size_to_resize
            y_ratio = original_frame.shape[0] / size_to_resize

            x1, y1, x2, y2 = map(int, [xyxy[0] * x_ratio, xyxy[1] * y_ratio, xyxy[2] * x_ratio, xyxy[3] * y_ratio])
            centroid = ((x1 + x2) // 2, (y1 + y2) // 2)
            centroid_y_adjusted = y1 + int((y2 - y1) * centroid_y_ratio)
            centroid = (centroid[0], centroid_y_adjusted)

            class_name = class_names[int(cls)]

            if class_name == "person":
                if is_inside(points, centroid):
                    detected_inside_polygon = True
                cv2.circle(original_frame, centroid, 5, (0, 0, 255), -1)
                cv2.putText(original_frame, class_name, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, TEXT_COLOR, 2)
                cv2.rectangle(original_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            else:
                cv2.putText(original_frame, class_name, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.3, TEXT_COLOR, 2)
                # Draw a transparent rectangle
                original_frame = draw_transparent_rectangle(original_frame, (x1, y1), (x2, y2), (0, 255, 0), 0.05)

        original_frame = draw_polygon(original_frame, points)
        original_frame = display_alarm(original_frame, detected_inside_polygon)
        current_time = datetime.datetime.now()

        # Check for recording cooldown
        if cooldown_start_time and (current_time - cooldown_start_time < datetime.timedelta(seconds=30)):
            if recording:
                stop_video_recording(video_writer, video_filename, start_time, last_detection_time, frame_count)
                recording = False
            continue  # Skip recording during cooldown

        # Start recording if detected inside polygon
        if detected_inside_polygon:
            if not recording:
                if alert_callback:
                    alert_callback(camera_identifier)
                frame_count = 0
                recording = True
                start_time = current_time
                video_writer, video_filename = start_video_recording(original_frame)
                print(f"Started recording at {start_time.strftime('%H:%M:%S')}")
            video_writer.write(original_frame)
            last_detection_time = current_time
            frame_count += 1

        # Check if maximum recording time or no detection for 2 seconds
        if recording:
            recording_duration = current_time - start_time
            if recording_duration >= datetime.timedelta(seconds=60) or (
                    current_time - last_detection_time >= datetime.timedelta(seconds=2)):
                stop_video_recording(video_writer, video_filename, start_time, last_detection_time, frame_count)
                print(f"Stopped recording at {current_time.strftime('%H:%M:%S')}")

                # Check if the maximum recording time was reached to start cooldown
                if recording_duration >= datetime.timedelta(seconds=60):
                    cooldown_start_time = current_time

                recording = False

        yield original_frame

    cap.release()
    cv2.destroyAllWindows()


def handle_left_click(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        points.append((x, y))


def draw_polygon(frame, points):
    for point in points:
        cv2.circle(frame, point, 5, POLYGON_DOT_COLOR, -1)
    if len(points) >= 2:
        cv2.polylines(frame, [np.int32(points)], isClosed=True, color=POLYGON_COLOR, thickness=2)
    return frame


def load_polygon_points(filename='polygon.txt'):
    """Load polygon points from a file, or create an empty file if not found."""
    points = []
    try:
        with open(filename, 'r') as f:
            for line in f:
                parts = line.strip().split(',')
                if len(parts) != 2:
                    raise ValueError("Invalid line format in file")
                x, y = map(int, parts)
                points.append((x, y))
    except FileNotFoundError:
        # Create an empty file if it doesn't exist
        with open(filename, 'w') as f:
            pass
    return points


def load_centroid_y_ratio(filename='centroid.txt', default_value=50):
    """Load centroid Y position ratio from a file, or create one with a default value."""
    try:
        with open(filename, 'r') as file:
            value = int(file.read().strip())
            if 0 <= value <= 100:
                return 1 - (value / 100)  # Inverting the ratio
            else:
                raise ValueError("Value in file must be between 0 and 100")
    except (FileNotFoundError, ValueError):
        with open(filename, 'w') as file:
            file.write(str(default_value))
        return 1 - (default_value / 100)  # Inverting the ratio


def is_inside(points, centroid):
    """Check if a centroid is inside a polygon defined by points using the ray casting algorithm."""
    if len(points) < 3:
        return False

    n = len(points)
    inside = False

    p1x, p1y = points[0]
    for i in range(n + 1):
        p2x, p2y = points[i % n]
        if centroid[1] > min(p1y, p2y):
            if centroid[1] <= max(p1y, p2y):
                if centroid[0] <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (centroid[1] - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or centroid[0] <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y

    return inside


# Find a user's phone number by camera id to alert
def find_user_phonenumber_by_camera(identifier):
    camera_ref = db.collection('user_cameras').where('camera_id', '==', identifier)
    if len(camera_ref.get()) > 0:
        camera = camera_ref.get()[0]
        number_ref = db.collection('phonenumbers').where('user_id', '==', camera.to_dict()['user_id'])
        if len(number_ref.get()) > 0:
            number = number_ref.get()[0]
            return number


def get_camera_nickname(identifier):
    camera_ref = db.collection('user_cameras').where('camera_id', '==', identifier)
    if len(camera_ref.get()) > 0:
        camera = camera_ref.get()[0]
        camera = camera.to_dict()
        return camera['nickname']

# Debounce timer for alerting
def in_debounce():
    global debounce, last_alert_time
    if not debounce:
        debounce = True
        last_alert_time = datetime.datetime.utcnow()
        return not debounce

    if (datetime.datetime.utcnow() - last_alert_time).total_seconds() > debounce_time:
        debounce = False

    return True


def display_alarm(frame, condition):
    if condition:
        cv2.putText(frame, "ALARM: Person Detected!", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, ALARM_TEXT_COLOR, 2)
        # alert_user()
    return frame


def draw_transparent_rectangle(img, pt1, pt2, color, alpha):
    overlay = img.copy()
    cv2.rectangle(overlay, pt1, pt2, color, -1)
    return cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0)


def start_video_recording(frame):
    # Create directories
    today_folder = create_directory_structure()
    # Define video writer
    fourcc = cv2.VideoWriter_fourcc(*'avc1')  # Alternative codec
    video_filename = os.path.join(today_folder, datetime.datetime.now().strftime("%H-%M-%S") + ".mp4")
    video_writer = cv2.VideoWriter(video_filename, fourcc, 20.0, (frame.shape[1], frame.shape[0]))
    return video_writer, video_filename  # Return both the writer and filename


def stop_video_recording(video_writer, video_filename, start_time, end_time, frame_count):
    video_writer.release()

    actual_duration = (end_time - start_time).total_seconds()
    if actual_duration > 0:
        new_frame_rate = frame_count / actual_duration
    else:
        new_frame_rate = 20.0  # Default frame rate

    new_filename = f"{start_time.strftime('%H-%M-%S')}_{end_time.strftime('%H-%M-%S')}.mp4"
    temp_filename = video_filename + "_temp.mp4"

    # Use ffmpeg to adjust the frame rate
    subprocess.run([
        'ffmpeg', '-i', video_filename, '-r', str(new_frame_rate),
        '-c', 'copy', temp_filename
    ])

    # Rename the temporary file to the new file
    os.rename(temp_filename, os.path.join(os.path.dirname(video_filename), new_filename))

    # Clean up the original file
    os.remove(video_filename)


def create_directory_structure():
    base_folder = "captured_video"
    today_folder = os.path.join(base_folder, datetime.datetime.now().strftime("%Y-%m-%d"))
    if not os.path.exists(today_folder):
        os.makedirs(today_folder)
    return today_folder
