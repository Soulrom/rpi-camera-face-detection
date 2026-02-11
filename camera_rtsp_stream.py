#!/usr/bin/env python3
"""
Raspberry Pi 4 B - Camera with Face Detection and HTTP MJPEG Server
Local camera streaming via HTTP MJPEG + real-time face detection
"""

import cv2
import numpy as np
import time
import logging
import threading
from picamera2 import Picamera2
from flask import Flask, Response, render_template_string

# ============================================================================
# CONFIGURATION
# ============================================================================

VIDEO_WIDTH = 1280
VIDEO_HEIGHT = 720
VIDEO_FPS = 30

# FFmpeg/RTSP parameters
GST_HOST = "127.0.0.1"
BITRATE = 2000  # kbps (for H.264)

# Flask Web Server parameters
WEB_PORT = 5000
WEB_HOST = "0.0.0.0"

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Flask app for HTTP MJPEG stream
app = Flask(__name__)

# Global variable for latest frame
last_frame_data = None
last_frame_lock = threading.Lock()

@app.route('/')
def index():
    """Main page with HTML video player"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Raspberry Pi Camera - Face Detection</title>
        <style>
            body { font-family: Arial; text-align: center; background: #222; color: white; padding: 20px; }
            h1 { color: #4CAF50; }
            img { max-width: 100%; height: auto; border: 2px solid #4CAF50; margin-top: 20px; }
            .info { margin-top: 20px; font-size: 14px; color: #aaa; }
        </style>
    </head>
    <body>
        <h1>Raspberry Pi Camera Stream</h1>
        <h2>Face Detection with Haar Cascade</h2>
        <img src="/video_feed" width="100%" style="max-width: 1280px;">
        <div class="info">
            <p>Resolution: 1280x720 @ ~28 FPS</p>
            <p>Green boxes = Detected faces</p>
        </div>
    </body>
    </html>
    """
    return render_template_string(html)

@app.route('/video_feed')
def video_feed():
    """MJPEG stream for browser"""
    def generate():
        while True:
            global last_frame_data
            with last_frame_lock:
                if last_frame_data is not None:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n'
                           b'Content-length: ' + str(len(last_frame_data)).encode() + b'\r\n\r\n'
                           + last_frame_data + b'\r\n')
            time.sleep(0.03)  # 30 FPS (frame rate)
    
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

# ============================================================================
# FACE DETECTION
# ============================================================================

class FaceDetector:
    """Face detection with caching optimization"""
    
    def __init__(self):
        self.cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        self.frame_count = 0
        self.cached_faces = []  # Cache detection results
        logger.info("[OK] Haar Cascade loaded")
    
    def detect_and_draw(self, frame):
        """Detect and draw faces with caching"""
        self.frame_count += 1
        
        # Detect every 5th frame for optimization
        if self.frame_count % 5 == 0:
            # Resize for speed
            small_frame = cv2.resize(frame, (320, 240))
            gray = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
            
            # Detection on small frame
            faces = self.cascade.detectMultiScale(
                gray,
                scaleFactor=1.3,
                minNeighbors=5,
                minSize=(20, 20),
                flags=cv2.CASCADE_SCALE_IMAGE
            )
            
            # Scale back to original
            if len(faces) > 0:
                scale_x = frame.shape[1] / 320
                scale_y = frame.shape[0] / 240
                
                self.cached_faces = []
                for x, y, w, h in faces:
                    x = int(x * scale_x)
                    y = int(y * scale_y)
                    w = int(w * scale_x)
                    h = int(h * scale_y)
                    self.cached_faces.append((x, y, w, h))
            else:
                self.cached_faces = []
        
        # Draw cached faces on EVERY frame
        for x, y, w, h in self.cached_faces:
            # Draw green rectangle
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
            
            # Text label
            cv2.putText(
                frame,
                "Face",
                (x, y - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                2
            )
        
        return frame, len(self.cached_faces)

# ============================================================================
# CAMERA + GSTREAMER RTSP
# ============================================================================

class CameraRTSPStream:
    """Manager for camera stream with Flask HTTP MJPEG server"""
    
    def __init__(self):
        self.camera = None
        self.detector = FaceDetector()
        self.running = False
        self.frame_count = 0
        self.start_time = time.time()
        self.last_face_count = 0
        self.last_frame = None
        self.flask_thread = None
    
    def init_ffmpeg(self):
        """Initialize HTTP MJPEG streaming via Flask (no RTSP server)"""
        try:
            # Start Flask in separate thread
            self.flask_thread = threading.Thread(target=self.run_flask, daemon=True)
            self.flask_thread.start()
            time.sleep(1)  # Give Flask time to start
            
            logger.info("[OK] HTTP MJPEG Encoder ready")
            logger.info(f"   [WEB] Open browser: http://YOUR_PI_IP:5000")
            logger.info(f"   [Local] http://127.0.0.1:5000")
            
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] Flask initialization failed: {e}")
            return False
    
    def run_flask(self):
        """Start Flask web server"""
        app.run(host=WEB_HOST, port=WEB_PORT, debug=False, use_reloader=False)
    
    def init_camera(self):
        """Initialize camera"""
        try:
            self.camera = Picamera2()
            
            config = self.camera.create_preview_configuration(
                main={
                    "format": "RGB888",
                    "size": (VIDEO_WIDTH, VIDEO_HEIGHT)
                },
                controls={"FrameRate": VIDEO_FPS}
            )
            
            self.camera.configure(config)
            self.camera.start()
            
            # Warm up camera
            for _ in range(30):
                self.camera.capture_array()
                time.sleep(0.02)
            
            logger.info(f"[OK] Camera: {VIDEO_WIDTH}x{VIDEO_HEIGHT} @ {VIDEO_FPS}fps")
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] Camera initialization failed: {e}")
            return False
    
    def process_loop(self):
        """Main frame processing loop"""
        self.running = True
        logger.info("[START] Frame processing started...")
        
        try:
            while self.running:
                try:
                    global last_frame_data
                    
                    # Capture frame from camera (RGB format)
                    frame_rgb = self.camera.capture_array()
                    
                    # RGB to BGR (for OpenCV)
                    frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
                    
                    # Face detection and drawing
                    frame_with_faces, face_count = self.detector.detect_and_draw(frame_bgr)
                    self.last_face_count = face_count
                    
                    # Convert back to RGB for web transmission
                    frame_rgb_processed = cv2.cvtColor(frame_with_faces, cv2.COLOR_BGR2RGB)
                    
                    # Encode to JPEG for web server
                    ret, jpeg_buffer = cv2.imencode('.jpg', cv2.cvtColor(frame_rgb_processed, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 85])
                    if ret:
                        with last_frame_lock:
                            last_frame_data = jpeg_buffer.tobytes()
                    
                    # Store last processed frame
                    self.last_frame = frame_rgb_processed
                    
                    # Statistics
                    self.frame_count += 1
                    elapsed = time.time() - self.start_time
                    fps = self.frame_count / elapsed if elapsed > 0 else 0
                    
                    # Log every 30 frames
                    if self.frame_count % 30 == 0:
                        logger.info(
                            f"Frame: {self.frame_count:5d} | "
                            f"FPS: {fps:5.1f} | "
                            f"Faces: {self.last_face_count}"
                        )
                    
                    # Small delay
                    time.sleep(0.001)
                    
                except Exception as e:
                    logger.error(f"Error in loop: {e}")
                    time.sleep(0.1)
        
        except KeyboardInterrupt:
            logger.info("[STOP] Shutdown signal received")
        finally:
            self.stop()
    
    def stop(self):
        """Clean shutdown"""
        logger.info("[SHUTDOWN] System shutdown...")
        self.running = False
        
        try:
            # Stop camera
            if self.camera:
                try:
                    self.camera.stop()
                except:
                    pass
            
            # Statistics
            elapsed = time.time() - self.start_time
            avg_fps = self.frame_count / elapsed if elapsed > 0 else 0
            
            logger.info("")
            logger.info("=" * 70)
            logger.info("[STATS] Final statistics:")
            logger.info(f"   Total frames: {self.frame_count}")
            logger.info(f"   Runtime: {elapsed:.1f}s")
            logger.info(f"   Average FPS: {avg_fps:.1f}")
            logger.info("=" * 70)
            logger.info("[OK] System stopped")
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
    
    def run(self):
        """Run entire system"""
        logger.info("=" * 70)
        logger.info("[CAMERA] Raspberry Pi Camera HTTP MJPEG Stream with Face Detection")
        logger.info("=" * 70)
        
        # Initialize camera
        if not self.init_camera():
            logger.error("Camera initialization failed")
            return 1
        
        # Show instructions for viewing
        self.init_ffmpeg()
        
        logger.info("")
        
        # Main loop
        self.process_loop()
        
        return 0

# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main entry point"""
    stream = CameraRTSPStream()
    return stream.run()

if __name__ == '__main__':
    exit(main())

