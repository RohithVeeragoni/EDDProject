import cv2
import numpy as np
from collections import deque
import time

class BasketballTracker:
    def __init__(self, camera_index=0):
        """
        Initialize the basketball tracking system
        
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
        # Has low saturation and high value
        self.lower_color = np.array([0, 0, 200])
        self.upper_color = np.array([180, 30, 255])
        
        # Ball tracking parameters
        self.ball_positions = deque(maxlen=50)  # Store last 50 positions
        self.min_ball_radius = 5
        self.max_ball_radius = 150
        
        # Hoop calibration (to be set later)
        self.hoop_position = None  # (x, y) in pixels
        self.pixels_per_meter = None  # Calibration factor
        
        # Frame processing
        self.frame_skip = 1  # Process every nth frame for performance
        self.frame_count = 0
        
        # Timing and performance metrics
        self.fps = 0
        self.frame_times = deque(maxlen=30)  # Track last 30 frame times
        self.last_frame_time = time.time()
        self.frame_latency = 0
        self.detection_time = 0
        self.draw_time = 0
        
    def calibrate_hoop(self, frame):
        """
        Interactive hoop position calibration
        Click on the center of the hoop
        """
        clone = frame.copy()
        cv2.putText(clone, "Click on hoop center, then press 'c' to confirm", 
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        def mouse_callback(event, x, y, flags, param):
            if event == cv2.EVENT_LBUTTONDOWN:
                self.hoop_position = (x, y)
                cv2.circle(clone, (x, y), 5, (0, 255, 0), -1)
                cv2.imshow("Calibrate Hoop", clone)
        
        cv2.namedWindow("Calibrate Hoop")
        cv2.setMouseCallback("Calibrate Hoop", mouse_callback)
        cv2.imshow("Calibrate Hoop", clone)
        
        while True:
            key = cv2.waitKey(1) & 0xFF
            if key == ord('c') and self.hoop_position is not None:
                break
            elif key == ord('q'):
                return False
        
        cv2.destroyWindow("Calibrate Hoop")
        print(f"Hoop calibrated at: {self.hoop_position}")
        return True
    
    def calibrate_distance(self, known_distance_m, measured_pixels):
        """
        Calibrate pixel-to-meter conversion
        
        Args:
            known_distance_m: Known real-world distance in meters
            measured_pixels: Corresponding distance in pixels
        """
        self.pixels_per_meter = measured_pixels / known_distance_m
        print(f"Calibration: {self.pixels_per_meter:.2f} pixels per meter")
    
    def detect_ball(self, frame):
        """
        Detect the colored circle in frame using color detection
        
        Returns:
            Tuple of (center_x, center_y, radius) or None if not found
        """
        # Convert to HSV color space
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        
        # Create mask for the color
        mask = cv2.inRange(hsv, self.lower_color, self.upper_color)
        
        # Morphological operations to reduce noise
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.erode(mask, kernel, iterations=2)
        mask = cv2.dilate(mask, kernel, iterations=2)
        
        # Find contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if len(contours) > 0:
            # Find largest contour (assumed to be basketball)
            largest_contour = max(contours, key=cv2.contourArea)
            
            # Get minimum enclosing circle
            ((x, y), radius) = cv2.minEnclosingCircle(largest_contour)
            
            # Filter by size
            if self.min_ball_radius < radius < self.max_ball_radius:
                return (int(x), int(y), int(radius))
        
        return None
    
    def calculate_distance_from_hoop(self, ball_pos):
        """
        Calculate distance from ball to hoop in meters
        
        Args:
            ball_pos: Tuple of (x, y) ball position
            
        Returns:
            Distance in meters or None if not calibrated
        """
        if self.hoop_position is None or self.pixels_per_meter is None:
            return None
        
        pixel_distance = np.sqrt(
            (ball_pos[0] - self.hoop_position[0])**2 + 
            (ball_pos[1] - self.hoop_position[1])**2
        )
        
        return pixel_distance / self.pixels_per_meter
    
    def draw_info(self, frame, ball_info):
        """
        Draw tracking information on frame
        """
        # Draw hoop position
        if self.hoop_position is not None:
            cv2.circle(frame, self.hoop_position, 10, (0, 255, 0), 2)
            cv2.putText(frame, "HOOP", 
                       (self.hoop_position[0] - 20, self.hoop_position[1] - 20),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        
        # Draw ball
        if ball_info is not None:
            x, y, radius = ball_info
            cv2.circle(frame, (x, y), radius, (0, 0, 255), 2)
            cv2.circle(frame, (x, y), 3, (0, 0, 255), -1)
            
            # Draw trajectory
            for i in range(1, len(self.ball_positions)):
                if self.ball_positions[i-1] is None or self.ball_positions[i] is None:
                    continue
                cv2.line(frame, self.ball_positions[i-1], self.ball_positions[i],
                        (255, 0, 0), 2)
            
            # Display distance
            distance = self.calculate_distance_from_hoop((x, y))
            if distance is not None:
                cv2.putText(frame, f"Distance: {distance:.2f}m",
                           (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # Display performance metrics
        cv2.putText(frame, f"FPS: {self.fps:.1f}",
                   (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.putText(frame, f"Frame Latency: {self.frame_latency*1000:.1f}ms",
                   (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.putText(frame, f"Detection Time: {self.detection_time*1000:.1f}ms",
                   (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.putText(frame, f"Draw Time: {self.draw_time*1000:.1f}ms",
                   (10, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.putText(frame, f"Positions: {len(self.ball_positions)}",
                   (10, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        return frame
    
    def run(self):
        """
        Main tracking loop
        """
        print("Basketball Shot Tracker Started")
        print("Press 'h' to calibrate hoop position")
        print("Press 'r' to reset trajectory")
        print("Press 'q' to quit")
        
        while True:
            # Measure frame capture time
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
            else:
                self.ball_positions.append(None)
            
            # Measure drawing time
            draw_start = time.time()
            display_frame = self.draw_info(frame, ball_info)
            self.draw_time = time.time() - draw_start
            
            # Show frame
            cv2.imshow("Basketball Tracker", display_frame)
            
            # Calculate total loop time
            total_time = time.time() - loop_start
            
            # Print detailed timing info every 30 frames
            if self.frame_count % 30 == 0:
                print(f"Frame {self.frame_count}: FPS={self.fps:.1f}, "
                      f"Total={total_time*1000:.1f}ms, "
                      f"Detect={self.detection_time*1000:.1f}ms, "
                      f"Draw={self.draw_time*1000:.1f}ms")
            
            # Handle keyboard input
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('q'):
                break
            elif key == ord('h'):
                self.calibrate_hoop(frame)
            elif key == ord('r'):
                self.ball_positions.clear()
                print("Trajectory reset")
        
        self.cleanup()
    
    def cleanup(self):
        """
        Release resources
        """
        self.cap.release()
        cv2.destroyAllWindows()
        print("Tracker stopped")
        print(f"Average FPS: {self.fps:.1f}")
        if len(self.frame_times) > 0:
            avg_latency = sum(self.frame_times) / len(self.frame_times)
            print(f"Average Latency: {avg_latency*1000:.1f}ms")


if __name__ == "__main__":
    # Initialize tracker with MacBook camera (default is 0)
    tracker = BasketballTracker(camera_index=0)
    
    print("\n=== COLORED CIRCLE DETECTION MODE ===")
    print("Use a colored paper circle or colored ball for testing")
    print("Adjust lighting if detection is poor")
    print("\nControls:")
    print("  'h' - Calibrate target position")
    print("  'r' - Reset trajectory")
    print("  'q' - Quit")
    print("\n===================================\n")
    
    # Run tracker
    tracker.run()