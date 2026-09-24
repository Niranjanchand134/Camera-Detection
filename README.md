# Camera_Detection - Multi-Camera AI Surveillance & Telemetry Dashboard

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0+-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![OpenCV](https://img.shields.io/badge/OpenCV-4.10+-5C3EE8?style=for-the-badge&logo=opencv&logoColor=white)](https://opencv.org/)
[![YOLO](https://img.shields.io/badge/YOLO-Ultralytics-FF6F00?style=for-the-badge&logo=yolo&logoColor=white)](https://ultralytics.com/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge)](LICENSE)

Camera_Detection is an intelligent multi-camera RTSP surveillance system and real-time telemetry dashboard. It features edge computer vision models for Person & Vehicle Detection, Speed Estimation, Optical Character Recognition (OCR) for License Plates, high-compatibility H.264 video recording, and an interactive dark-glassmorphic web dashboard with tap-to-focus and smooth optical zoom/pan.

---

## Key Features

- **Multi-Camera Real-Time Streaming**: High-performance multi-threaded RTSP ingestion with auto-reconnect, sub-second latency, and composite grid generation.
- **Direct Tap-to-Focus & Smooth Zoom**:
  - Click any camera in the grid view to zoom in and isolate its focused feed.
  - Interactive mouse wheel / button zooming (up to 4.0x) and drag/keyboard panning (WASD or Arrow keys).
  - Double-click or press `ESC` to instantly return to the grid view.
- **Real-Time Edge AI Detection**:
  - **Person Detection**: Real-time bounding boxes with confidence scores.
  - **Vehicle Detection + Intelligence**: Vehicle tracking with calibrated Speed Estimation (km/h) and License Plate OCR recognition.
  - Instant toggle between AI modes (`Off`, `Person`, `Vehicle`) without restarting streams.
- **Automatic Continuous Background Recording**:
  - Automatically captures 24/7 footage for each camera independently in rolling time segments (e.g. 10-minute chunks).
  - Organized automatically by date and camera: `recordings/YYYY-MM-DD/<Camera_Name>/recording_<Camera_Name>_<timestamp>.mp4`.
  - Encoded with hardware-compatible H.264 video encoding via PyAV for instant, seekable in-browser HTML5 playback.
- **Records & Analytics Reports**:
  - Real-time event logging to SQLite with automatic snapshot captures.
  - **Instant Auto-Filtering**: Live filtering for detections by camera, detection type, plate number, minimum speed, and date ranges.
  - **Day & Camera Video Archive Filter**: Filter saved recordings day-by-day and camera-by-camera with built-in seekable video player.
  - Single-click CSV report export.
  - Single and batch deletion for detection events and video recordings.
- **In-Browser Live Audio Streaming**:
  - Real-time MP3 transcoding of camera RTSP audio (`pcm_mulaw`/G.711u) directly streamed to the web browser.
  - Listen to live camera audio directly in your browser when focusing any camera with a microphone.
- **Security & Configuration**:
  - Credentials and RTSP endpoints stored securely in `.env` (excluded from Git).

---


## Installation & Setup

### 1. Clone the Repository
```bash
git clone https://github.com/Niranjanchand134/Camera-Detection.git
cd Camera-Detection
```

### 2. Create and Activate a Virtual Environment
```bash
# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate

# Windows
python -m venv .venv
.venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy `.env.example` to `.env` and fill in your camera RTSP credentials:
```bash
cp .env.example .env
```

Edit `.env` with your actual network camera configuration:
```env
CAMERA_USERNAME=your_camera_username
CAMERA_PASSWORD=your_camera_password
CAMERA_PORT=554
CAMERA_DEFAULT_CHANNEL=101

# Camera IP Addresses
CAMERA_1_NAME=Camera 1
CAMERA_1_IP=your_camera_IP_Address

CAMERA_2_NAME=Camera 2
CAMERA_2_IP=your_camera_IP_Address

CAMERA_3_NAME=Camera 3
CAMERA_3_IP=your_camera_IP_Address

CAMERA_4_NAME=Camera 4
CAMERA_4_IP=your_camera_IP_Address

# Web Server
WEB_HOST=0.0.0.0
WEB_PORT=5000
SECRET_KEY=your-random-secret-key
```

---

## Running the Application

### Launch Web Dashboard (Default)
```bash
python main.py
```
Or customize the binding host and port:
```bash
python main.py --mode web --host 0.0.0.0 --port 5000
```

Once started, open your web browser and navigate to:
```
http://localhost:5000
```

### Launch Native Desktop Mode (Optional)
```bash
python main.py --mode desktop
```

---

## Dashboard Navigation & Controls

### Live Monitoring Page (`/live`)
- **Camera Tap**: Click any camera tile in the grid to isolate and focus that camera.
- **Zoom & Pan**:
  - Use the mouse wheel or the on-screen `+` / `-` controls to zoom up to 4.0x.
  - Drag with your mouse or use `W`, `A`, `S`, `D` or `Arrow Keys` to pan across the viewport.
- **Return to Grid**: Click the "Back to All Cameras" button, double-click the viewport, or press `ESC`.
- **AI Mode Switcher**: Toggle between `Off`, `Person`, and `Vehicle + OCR & Speed`.
- **Recording Controls**: Select "Grid (All)" or any individual camera from the dropdown and click `Record`.
- **Audio Monitoring**: Click `Audio` (or press `M`) to toggle live audio from the focused camera.

### Records & Reports Page (`/records`)
- **Live Auto-Filter**: Type in the plate input, select a camera or category, or choose a date range — results update instantly with debounce.
- **Snapshot Viewer**: Click any snapshot thumbnail to inspect high-resolution detection frames in a modal dialog.
- **HTML5 Video Player**: Stream and seek saved video recordings with standard browser controls.
- **CSV Export**: Click "Export CSV" to download the current filtered dataset.
- **Deletion Management**: Delete individual records/videos or perform batch cleanup.

---

## Keyboard Shortcuts (Live View)

| Key | Action |
| --- | --- |
| `ESC` | Return to Grid View from Focused View |
| `+` / `=` | Zoom In |
| `-` | Zoom Out |
| `W` / `A` / `S` / `D` or `Arrows` | Pan Viewport (when zoomed in) |
| `R` | Toggle Recording |
| `M` | Toggle Audio Mute |

---
