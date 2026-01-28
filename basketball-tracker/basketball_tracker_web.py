import cv2
import numpy as np
from collections import deque
import time
import json
from flask import Flask, render_template
from flask_socketio import SocketIO
import threading

class BasketballTrackerWeb:
    def __init__(self, camera_index=0):
        """
        Initialize the basketball tracking system with web interface
        
        Args:
            camera_index: Camera device index (0 for default, or video file path)
        """
        # Camera setup
        self.cap = cv2.VideoCapture(camera_index)
        
        # Optimize for Raspberry Pi
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        
        # Color range for the colored circles (HSV)
        self.lower_color = np.array([35, 100, 100])
        self.upper_color = np.array([75, 255, 255])
        
        # Ball tracking parameters
        self.ball_positions = deque(maxlen=50)
        self.min_ball_radius = 5
        self.max_ball_radius = 150
        
        # Hoop calibration
        self.hoop_position = None
        self.pixels_per_meter = None
        
        # Frame processing
        self.frame_skip = 1
        self.frame_count = 0
        
        # Timing and performance metrics
        self.fps = 0
        self.frame_times = deque(maxlen=30)
        self.last_frame_time = time.time()
        self.frame_latency = 0
        self.detection_time = 0
        self.draw_time = 0
        
        # Shot statistics
        self.total_shots = 0
        self.made_shots = 0
        self.missed_shots = 0
        self.current_distance = None
        self.max_speed = 0
        
        # Web server
        self.app = Flask(__name__)
        self.socketio = SocketIO(self.app, cors_allowed_origins="*")
        self.running = False
        
        # Setup routes
        self.setup_routes()
    
    def setup_routes(self):
        """Setup Flask routes"""
        @self.app.route('/')
        def index():
            return render_template('dashboard.html')
        
        @self.socketio.on('connect')
        def handle_connect():
            print('Client connected')
        
        @self.socketio.on('disconnect')
        def handle_disconnect():
            print('Client disconnected')
        
        @self.socketio.on('calibrate_hoop')
        def handle_calibrate_hoop(data):
            self.hoop_position = (data['x'], data['y'])
            print(f"Hoop calibrated at: {self.hoop_position}")
            self.broadcast_data()
        
        @self.socketio.on('reset_trajectory')
        def handle_reset():
            self.ball_positions.clear()
            print("Trajectory reset")
            self.broadcast_data()
    
    def detect_ball(self, frame):
        """Detect the colored circle in frame using color detection"""
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, self.lower_color, self.upper_color)
        
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.erode(mask, kernel, iterations=2)
        mask = cv2.dilate(mask, kernel, iterations=2)
        
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if len(contours) > 0:
            largest_contour = max(contours, key=cv2.contourArea)
            ((x, y), radius) = cv2.minEnclosingCircle(largest_contour)
            
            if self.min_ball_radius < radius < self.max_ball_radius:
                return (int(x), int(y), int(radius))
        
        return None
    
    def calculate_distance_from_hoop(self, ball_pos):
        """Calculate distance from ball to hoop in meters"""
        if self.hoop_position is None or self.pixels_per_meter is None:
            return None
        
        pixel_distance = np.sqrt(
            (ball_pos[0] - self.hoop_position[0])**2 + 
            (ball_pos[1] - self.hoop_position[1])**2
        )
        
        return pixel_distance / self.pixels_per_meter
    
    def calculate_ball_speed(self):
        """Calculate ball speed based on recent positions"""
        if len(self.ball_positions) < 2:
            return 0
        
        # Get last two valid positions
        valid_positions = [pos for pos in list(self.ball_positions)[-5:] if pos is not None]
        if len(valid_positions) < 2:
            return 0
        
        # Calculate pixel distance
        dx = valid_positions[-1][0] - valid_positions[-2][0]
        dy = valid_positions[-1][1] - valid_positions[-2][1]
        pixel_distance = np.sqrt(dx**2 + dy**2)
        
        # Convert to m/s (assuming frame rate)
        if self.pixels_per_meter:
            meters = pixel_distance / self.pixels_per_meter
            time_delta = self.frame_latency
            if time_delta > 0:
                speed = meters / time_delta
                return speed
        
        return 0
    
    def broadcast_data(self):
        """Send current tracking data to all connected clients"""
        # Prepare trajectory data
        trajectory = []
        for pos in self.ball_positions:
            if pos is not None:
                trajectory.append({'x': pos[0], 'y': pos[1]})
        
        # Calculate current speed
        current_speed = self.calculate_ball_speed()
        if current_speed > self.max_speed:
            self.max_speed = current_speed
        
        data = {
            'fps': round(self.fps, 1),
            'frame_latency': round(self.frame_latency * 1000, 1),
            'detection_time': round(self.detection_time * 1000, 1),
            'draw_time': round(self.draw_time * 1000, 1),
            'distance': round(self.current_distance, 2) if self.current_distance else None,
            'trajectory': trajectory,
            'hoop_position': self.hoop_position,
            'total_shots': self.total_shots,
            'made_shots': self.made_shots,
            'missed_shots': self.missed_shots,
            'accuracy': round((self.made_shots / self.total_shots * 100), 1) if self.total_shots > 0 else 0,
            'current_speed': round(current_speed, 2),
            'max_speed': round(self.max_speed, 2),
            'positions_tracked': len([p for p in self.ball_positions if p is not None])
        }
        
        self.socketio.emit('update', data)
    
    def tracking_loop(self):
        """Main tracking loop running in separate thread"""
        print("Basketball Shot Tracker Started")
        
        while self.running:
            loop_start = time.time()
            
            ret, frame = self.cap.read()
            
            if not ret:
                print("Failed to grab frame")
                break
            
            # Calculate frame latency
            current_time = time.time()
            self.frame_latency = current_time - self.last_frame_time
            self.last_frame_time = current_time
            self.frame_times.append(self.frame_latency)
            
            # Calculate FPS
            if len(self.frame_times) > 0:
                avg_frame_time = sum(self.frame_times) / len(self.frame_times)
                self.fps = 1.0 / avg_frame_time if avg_frame_time > 0 else 0
            
            self.frame_count += 1
            
            # Skip frames for performance
            if self.frame_count % self.frame_skip != 0:
                continue
            
            # Measure detection time
            detect_start = time.time()
            ball_info = self.detect_ball(frame)
            self.detection_time = time.time() - detect_start
            
            # Update trajectory
            if ball_info is not None:
                self.ball_positions.append((ball_info[0], ball_info[1]))
                self.current_distance = self.calculate_distance_from_hoop((ball_info[0], ball_info[1]))
            else:
                self.ball_positions.append(None)
            
            # Broadcast data to web clients every 5 frames
            if self.frame_count % 5 == 0:
                self.broadcast_data()
            
            # Print timing info every 60 frames
            if self.frame_count % 60 == 0:
                print(f"Frame {self.frame_count}: FPS={self.fps:.1f}, "
                      f"Detect={self.detection_time*1000:.1f}ms")
        
        self.cleanup()
    
    def start(self):
        """Start the tracker and web server"""
        self.running = True
        
        # Start tracking in separate thread
        tracking_thread = threading.Thread(target=self.tracking_loop)
        tracking_thread.daemon = True
        tracking_thread.start()
        
        print("\n" + "="*50)
        print("Basketball Shot Tracker Web Interface")
        print("="*50)
        print("\nWeb Dashboard: http://localhost:5000")
        print("\nThe tracker is now running!")
        print("Open the dashboard in your browser to view real-time data")
        print("\nPress Ctrl+C to stop")
        print("="*50 + "\n")
        
        # Start Flask server (blocking)
        self.socketio.run(self.app, host='0.0.0.0', port=5000, debug=False)
    
    def stop(self):
        """Stop the tracker"""
        self.running = False
    
    def cleanup(self):
        """Release resources"""
        self.cap.release()
        print("Tracker stopped")


if __name__ == "__main__":
    # Initialize tracker
    tracker = BasketballTrackerWeb(camera_index=0)
    
    try:
        # Start tracking and web server
        tracker.start()
    except KeyboardInterrupt:
        print("\nShutting down...")
        tracker.stop()
