# Polyguard - IoT Device and Computer Vision Implementation on Raspberry Pi 4

## Overview
Polyguard is an innovative project focused on implementing advanced computer vision technology on Internet of Things (IoT) devices. Utilizing YOLOv5 with TensorFlow Lite models, Polyguard leverages the power of Coral AI's Accelerator USB as an Edge TPU, running on a Raspberry Pi 4. This project is designed to enhance surveillance and monitoring systems by providing precise and adaptable person detection capabilities.

## Key Features

### Computer Vision Software
- Device: Raspberry Pi 4 with TFlite model and Coral AI USB Accelerator.
- Functionality: Real-time person detection with adjustable detection areas through polygon drawing.
- Centroid Calculation: Utilizes bounding box coordinates (xmin, xmax, ymin, ymax) to determine the centroid point, enhancing detection accuracy.
- Centroid Ratio: Adjustable ratio (0 to 1) for fine-tuning detection sensitivity, accommodating different camera perspectives.
### Dashboard Website
Access Control: User registration and authentication system.
Camera Management: Add and configure camera settings using unique identifiers and passwords.
Customization: Edit detection polygons and centroid ratios remotely.
Alert System: Option to receive SMS alerts upon person detection.
Video Playback: Feature to review captured detection footage.
### Connectivity and Security
Remote Access: Utilizes ngrok to expose Raspberry Pi securely.
Enhanced Security: Integration of multiple security services to ensure data protection.
Performance and Hardware
Frame Rate: Achieves 35-40 FPS with 223x223 frame size.

## Hardware Cost:
- Raspberry Pi 4: $35
- Raspberry Pi AF Camera 5MP OV5647: $3
- Coral AI USB Accelerator: $59.99

## Technology Stack
- Programming: Python, Flask for software and backend development.
- Database: Firebase.
- Web Design: HTML/CSS with Bootstrap and W3Schools.

## Advantages Over MotionEyeOS
Polyguard surpasses traditional motion detectors like MotionEyeOS by implementing AI-driven computer vision. This allows for the detection of various objects (e.g., dogs, cars) based on the trained model, offering more versatility and precision for surveillance needs.

## Contribution
We welcome contributions from the community. Please refer to our contribution guidelines for more information on how to participate in the development of Polyguard.

## Acknowledgments
A special thanks to the developers and contributors who have made Polyguard a reality. Your dedication and expertise have been instrumental in bringing this project to life.
