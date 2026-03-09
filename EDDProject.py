import cv2
import numpy as np
from collections import deque
import time
from flask import Flask, render_template, Response
from flask_socketio import SocketIO, emit
import threading

app = Flask(__name__, template_folder='basketball-tracker/templates')
app.config['SECRET_KEY'] = 'basketball_tracker_secret'
app.config['TEMPLATES_AUTO_RELOAD'] = True

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

class BasketballTracker:
    def __init__(self, camera_index=0):
        # Camera setup
        self.cap = cv2.VideoCapture(camera_index)

        # Resolution options:
        # 640x480 (VGA) - Fast, lower quality
        # 1280x720 (720p HD) - Good balance ✓ RECOMMENDED
        # 1920x1080 (1080p Full HD) - Best quality, slower
        self.frame_width = 1280
        self.frame_height = 720

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.frame_width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.frame_height)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Reduce buffer for lower latency
        
        # Color range for rose pink detection (VERY WIDE BOUNDS for fast motion)
        self.lower_color = np.array([140, 40, 40])  # More lenient
        self.upper_color = np.array([180, 255, 255])
        
        # Ball tracking
        self.ball_positions = deque(maxlen=50)
        self.ball_timestamps = deque(maxlen=50)  # Track timestamps
        self.min_ball_radius = 3  # More lenient minimum
        self.max_ball_radius = 200  # More lenient maximum

        # Predictive tracking for fast motion
        self.last_valid_position = None
        self.last_valid_velocity = (0, 0)
        self.missed_detections = 0
        self.max_missed_before_reset = 10  # Allow 10 missed frames
        
        # Hoop calibration
        self.hoop_position = None
        self.pixels_per_meter = 100  # 100 pixels = 1 meter (adjust as needed)

        # Depth estimation (NEW!)
        self.camera_focal_length = 800            # Pixels (will be calibrated)
        self.real_ball_diameter = 0.24            # Basketball diameter in meters
        self.depth_calibrated = False              # Is depth estimation calibrated?
        self.current_depth = None                  # Current ball depth estimate
        
        # Metrics
        self.fps = 0
        self.frame_times = deque(maxlen=30)
        self.last_frame_time = time.time()
        self.frame_latency = 0
        self.detection_time = 0
        self.draw_time = 0
        self.frame_count = 0
        
        # Dashboard data
        self.current_frame = None
        self.current_distance = 0
        self.is_running = False
        self.max_speed = 0
        self.current_speed = 0
        self.current_angle = 0
        self.launch_angle = None
        
        # Shot statistics
        self.total_shots = 0
        self.made_shots = 0
        self.missed_shots = 0

        # Trajectory prediction (NEW!)
        self.trajectory_coefficients = None  # Parabola coefficients [a, b, c]
        self.predicted_outcome = None        # Make/miss prediction
        self.predicted_landing_x = None      # Where ball will cross hoop plane
        self.apex_height = None              # Highest point of trajectory
        self.apex_position = None            # (x, y) of apex
        self.entry_angle = None              # Angle ball enters hoop

        # Shot detection
        self.shot_in_progress = False        # Is a shot currently happening?
        self.last_detection_time = time.time()
        self.shot_timeout = 2.0              # Seconds before considering shot finished

        # Thread safety
        self.frame_lock = threading.Lock()
        
    def detect_ball(self, frame):
        """
        Detect ball in frame with motion prediction for fast objects.

        Returns:
            tuple: (x, y, radius, depth) or None if not found
                   depth will be None if not calibrated
        """
        # Convert to HSV
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, self.lower_color, self.upper_color)

        # MINIMAL morphology for fast motion tracking
        kernel = np.ones((2, 2), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

        # Find contours with simpler approximation
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        best_detection = None

        if len(contours) > 0:
            # Try to find valid ball among all contours
            for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:3]:  # Check top 3
                area = cv2.contourArea(contour)

                # Lower area threshold for fast motion
                if area > 50:
                    ((x, y), radius) = cv2.minEnclosingCircle(contour)

                    if self.min_ball_radius < radius < self.max_ball_radius:
                        # If we have previous position, prefer detections near predicted path
                        if self.last_valid_position is not None:
                            predicted_x = self.last_valid_position[0] + self.last_valid_velocity[0]
                            predicted_y = self.last_valid_position[1] + self.last_valid_velocity[1]
                            distance_from_prediction = np.sqrt(
                                (x - predicted_x)**2 + (y - predicted_y)**2
                            )

                            # Accept if within reasonable distance from prediction
                            if distance_from_prediction < 100:  # 100 pixels tolerance
                                best_detection = (int(x), int(y), int(radius))
                                break
                        else:
                            # No previous position, accept first valid detection
                            best_detection = (int(x), int(y), int(radius))
                            break

        # If we found a detection
        if best_detection:
            x, y, radius = best_detection

            # Update velocity for prediction
            if self.last_valid_position is not None:
                self.last_valid_velocity = (
                    x - self.last_valid_position[0],
                    y - self.last_valid_position[1]
                )

            self.last_valid_position = (x, y)
            self.missed_detections = 0

            # Estimate depth from ball size
            depth = self.estimate_depth_from_ball_size(radius)
            self.current_depth = depth

            return (x, y, radius, depth)

        # No detection - try prediction if we recently had valid tracking
        else:
            self.missed_detections += 1

            if self.missed_detections < 5 and self.last_valid_position is not None:
                # Predict position using last known velocity
                predicted_x = int(self.last_valid_position[0] + self.last_valid_velocity[0])
                predicted_y = int(self.last_valid_position[1] + self.last_valid_velocity[1])

                # Use last known radius for prediction
                last_radius = 10  # Default guess
                if len(self.ball_positions) > 0:
                    # Try to infer last radius from history
                    last_radius = 15

                self.last_valid_position = (predicted_x, predicted_y)

                # Return predicted position (marked as prediction with None depth)
                return (predicted_x, predicted_y, last_radius, None)

            # Too many missed frames - reset tracking
            if self.missed_detections > self.max_missed_before_reset:
                self.last_valid_position = None
                self.last_valid_velocity = (0, 0)
                self.missed_detections = 0

        return None
    
    def calculate_speed_and_angle(self):
        """Calculate current ball speed and trajectory angle"""
        if len(self.ball_positions) < 2:
            return 0, 0
        
        # Get last valid positions
        valid_positions = [(pos, ts) for pos, ts in zip(self.ball_positions, self.ball_timestamps) if pos is not None]
        
        if len(valid_positions) < 2:
            return 0, 0
        
        # Calculate speed using last 5 positions for smoothing
        num_points = min(5, len(valid_positions))
        recent_positions = valid_positions[-num_points:]
        
        total_distance = 0
        total_time = 0
        
        for i in range(1, len(recent_positions)):
            pos1, t1 = recent_positions[i-1]
            pos2, t2 = recent_positions[i]
            
            # Calculate pixel distance
            pixel_dist = np.sqrt((pos2[0] - pos1[0])**2 + (pos2[1] - pos1[1])**2)
            
            # Convert to meters
            meter_dist = pixel_dist / self.pixels_per_meter
            
            # Time difference
            time_diff = t2 - t1
            
            total_distance += meter_dist
            total_time += time_diff
        
        # Calculate average speed
        speed = total_distance / total_time if total_time > 0 else 0
        
        # Calculate angle (degrees from horizontal)
        if len(valid_positions) >= 2:
            pos1, _ = valid_positions[-2]
            pos2, _ = valid_positions[-1]
            
            dx = pos2[0] - pos1[0]
            dy = pos2[1] - pos1[1]
            
            # Calculate angle in degrees (0° = horizontal, 90° = up, -90° = down)
            angle = np.degrees(np.arctan2(-dy, dx))
            
            return speed, angle
        
        return speed, 0
    
    def calculate_launch_angle(self):
        """Calculate the initial launch angle using first few positions"""
        valid_positions = [pos for pos in self.ball_positions if pos is not None]

        if len(valid_positions) >= 3:
            pos1 = valid_positions[0]
            pos3 = valid_positions[2]

            dx = pos3[0] - pos1[0]
            dy = pos3[1] - pos1[1]

            angle = np.degrees(np.arctan2(-dy, dx))
            return angle

        return None

    # ============ TRAJECTORY REGRESSION METHODS ============

    def get_valid_trajectory_data(self):
        """
        Extract clean position and time data for regression.

        Returns:
            tuple: (x_coords, y_coords, times) or (None, None, None) if insufficient data

        Python Concepts:
        - zip(): Combines two lists element by element
        - List comprehension: Compact way to create lists
        - Tuple unpacking: Extracting multiple values from tuples
        """
        # Combine positions and timestamps, filtering out None values
        valid_data = []
        for pos, timestamp in zip(self.ball_positions, self.ball_timestamps):
            if pos is not None:
                valid_data.append((pos, timestamp))

        # Need at least 3 points for parabolic regression
        if len(valid_data) < 3:
            return None, None, None

        # Separate into individual arrays using list comprehension
        x_coords = [pos[0] for pos, t in valid_data]  # Extract X coordinates
        y_coords = [pos[1] for pos, t in valid_data]  # Extract Y coordinates
        times = [t for pos, t in valid_data]          # Extract timestamps

        return x_coords, y_coords, times

    def fit_trajectory(self):
        """
        Fit a parabolic curve (y = ax² + bx + c) to the ball's trajectory.

        Returns:
            np.array: Coefficients [a, b, c] or None if insufficient data

        Math Explanation:
        - Basketball shots follow parabolic paths due to gravity
        - We fit a 2nd degree polynomial: y = ax² + bx + c
        - 'a' controls curve steepness (more negative = steeper arc)
        - 'b' controls horizontal velocity component
        - 'c' is the y-intercept (starting height)

        Python Concepts:
        - np.array(): Convert Python list to NumPy array for math operations
        - np.polyfit(): Polynomial curve fitting function
        - deg=2: Fit a 2nd degree polynomial (parabola)
        """
        # Get clean trajectory data
        x_coords, y_coords, times = self.get_valid_trajectory_data()

        if x_coords is None:
            return None

        try:
            # Convert to NumPy arrays (required for polyfit)
            x_array = np.array(x_coords)
            y_array = np.array(y_coords)

            # Fit 2nd degree polynomial: y = ax² + bx + c
            # Returns [a, b, c] coefficients
            coefficients = np.polyfit(x_array, y_array, deg=2)

            return coefficients

        except Exception as e:
            print(f"Error fitting trajectory: {e}")
            return None

    def calculate_apex(self):
        """
        Calculate the apex (highest point) of the trajectory.

        Returns:
            dict: {'x': apex_x, 'y': apex_y, 'height_meters': height} or None

        Math Explanation:
        For parabola y = ax² + bx + c:
        - Apex occurs at x = -b / (2a)
        - This is where the derivative dy/dx = 0 (slope is flat)
        - Plug apex_x back into equation to get apex_y

        Why this matters:
        - Higher apex = better arc = higher make percentage
        - Ideal apex should be above the hoop
        - Too flat = ball hits front of rim
        """
        if self.trajectory_coefficients is None:
            return None

        try:
            a, b, c = self.trajectory_coefficients

            # Find X coordinate of apex (vertex of parabola)
            # Using calculus: derivative = 2ax + b = 0, solve for x
            apex_x = -b / (2 * a)

            # Calculate Y coordinate at apex
            apex_y = a * apex_x**2 + b * apex_x + c

            # Calculate height above ground (if we know ground level)
            # For now, just calculate height above starting position
            valid_positions = [pos for pos in self.ball_positions if pos is not None]
            if len(valid_positions) > 0:
                start_y = valid_positions[0][1]
                height_pixels = start_y - apex_y  # Remember: screen Y is inverted
                height_meters = height_pixels / self.pixels_per_meter
            else:
                height_meters = 0

            return {
                'x': apex_x,
                'y': apex_y,
                'height_meters': height_meters
            }

        except Exception as e:
            print(f"Error calculating apex: {e}")
            return None

    def predict_shot_outcome(self):
        """
        Predict if the shot will make it through the hoop.

        Returns:
            dict: Prediction results with confidence metrics or None

        Math Explanation:
        - We solve: hoop_y = ax² + bx + c for x
        - This is a quadratic equation: ax² + bx + (c - hoop_y) = 0
        - Solution uses quadratic formula: x = (-b ± √(b² - 4ac)) / 2a
        - We get 2 solutions (ball crosses hoop plane twice: up and down)
        - We want the larger X (forward trajectory when ball is coming down)

        Python Concepts:
        - Quadratic formula implementation
        - Dictionary return values for structured data
        - Error handling with try/except
        """
        # Need hoop position and trajectory fit
        if self.hoop_position is None or self.trajectory_coefficients is None:
            return None

        try:
            a, b, c = self.trajectory_coefficients
            hoop_x, hoop_y = self.hoop_position

            # Solve: hoop_y = ax² + bx + c
            # Rearrange: ax² + bx + (c - hoop_y) = 0
            # Use quadratic formula: x = (-b ± √discriminant) / 2a
            discriminant = b**2 - 4 * a * (c - hoop_y)

            # Negative discriminant = no real solution
            if discriminant < 0:
                return {
                    'will_make': False,
                    'confidence': 'high',
                    'reason': 'trajectory_too_low',
                    'predicted_x': None,
                    'distance_from_center': None
                }

            # Calculate both solutions
            sqrt_discriminant = np.sqrt(discriminant)
            x1 = (-b + sqrt_discriminant) / (2 * a)
            x2 = (-b - sqrt_discriminant) / (2 * a)

            # We want the forward trajectory (larger X)
            predicted_x = max(x1, x2)

            # Calculate horizontal distance from hoop center
            distance_pixels = abs(predicted_x - hoop_x)
            distance_meters = distance_pixels / self.pixels_per_meter

            # NBA hoop diameter = 18 inches = 0.4572 meters
            # Radius = 0.2286 meters
            # Ball diameter = 9.43 inches = 0.2395 meters
            # Effective hoop radius = 0.2286 - 0.1198 = 0.1088 meters
            hoop_radius_meters = 0.23
            effective_radius = hoop_radius_meters * 0.7  # 70% tolerance

            # Determine if shot will make it
            will_make = distance_meters < effective_radius

            # Calculate confidence based on trajectory quality
            data_points = len([p for p in self.ball_positions if p is not None])
            if data_points < 5:
                confidence = 'low'
            elif data_points < 10:
                confidence = 'medium'
            else:
                confidence = 'high'

            return {
                'will_make': will_make,
                'confidence': confidence,
                'reason': 'prediction',
                'predicted_x': float(predicted_x),
                'distance_from_center': float(distance_meters),
                'distance_pixels': float(distance_pixels),
                'hoop_radius': float(effective_radius)
            }

        except Exception as e:
            print(f"Error predicting shot outcome: {e}")
            return None

    def calculate_entry_angle(self):
        """
        Calculate the angle at which the ball will enter the hoop.

        Returns:
            float: Entry angle in degrees or None

        Why this matters:
        - Ideal entry angle: 45 degrees (gives most room for error)
        - Too steep (>60°): Ball bounces out more easily
        - Too shallow (<30°): Ball hits front rim
        - "High arc" shots have better make percentage

        Math Explanation:
        - Entry angle = angle of trajectory at hoop's X position
        - Use derivative of parabola: dy/dx = 2ax + b
        - Then: angle = arctan(dy/dx)
        """
        if self.trajectory_coefficients is None or self.predicted_landing_x is None:
            return None

        try:
            a, b, c = self.trajectory_coefficients
            x = self.predicted_landing_x

            # Calculate derivative (slope) at landing point
            # For y = ax² + bx + c, derivative dy/dx = 2ax + b
            slope = 2 * a * x + b

            # Calculate angle from horizontal
            # Note: Negative because screen Y is inverted
            angle_radians = np.arctan2(-slope, 1)
            angle_degrees = np.degrees(angle_radians)

            return angle_degrees

        except Exception as e:
            print(f"Error calculating entry angle: {e}")
            return None

    def detect_shot_start_end(self):
        """
        Detect when a shot starts and ends.

        Returns:
            str: 'started', 'in_progress', 'ended', or 'no_shot'

        Logic:
        - Shot starts: Ball detected after period of no detection
        - Shot in progress: Ball continuously detected
        - Shot ended: No ball detected for timeout period
        - This helps us know when to evaluate make/miss

        Python Concepts:
        - State machine pattern
        - Time-based event detection
        """
        current_time = time.time()
        time_since_last_detection = current_time - self.last_detection_time

        # Check if ball is currently detected
        ball_detected = any(pos is not None for pos in list(self.ball_positions)[-3:])

        if ball_detected:
            self.last_detection_time = current_time

            if not self.shot_in_progress:
                # Shot just started!
                self.shot_in_progress = True
                return 'started'
            else:
                return 'in_progress'

        else:
            # No ball detected
            if self.shot_in_progress and time_since_last_detection > self.shot_timeout:
                # Shot ended (no ball for timeout period)
                self.shot_in_progress = False
                return 'ended'

        return 'no_shot'

    def evaluate_shot_result(self):
        """
        Determine if the completed shot was a make or miss.

        Returns:
            str: 'make', 'miss', or 'unknown'

        Logic:
        - Compare actual trajectory near hoop with predicted outcome
        - Check if ball passed through hoop region
        - Update make/miss statistics

        This is called when a shot ends (detect_shot_start_end returns 'ended')
        """
        if self.hoop_position is None:
            return 'unknown'

        # Get last few positions before ball was lost
        last_positions = [pos for pos in list(self.ball_positions)[-10:] if pos is not None]

        if len(last_positions) < 3:
            return 'unknown'

        # Check if ball passed near hoop
        hoop_x, hoop_y = self.hoop_position
        hoop_radius_pixels = 0.23 * self.pixels_per_meter

        for pos in last_positions:
            distance = np.sqrt((pos[0] - hoop_x)**2 + (pos[1] - hoop_y)**2)
            if distance < hoop_radius_pixels * 1.5:  # Within 1.5x hoop radius
                # Ball passed near hoop - likely a make!
                self.made_shots += 1
                self.total_shots += 1
                return 'make'

        # Ball didn't pass near hoop - likely a miss
        self.missed_shots += 1
        self.total_shots += 1
        return 'miss'

    # ============ DEPTH ESTIMATION METHODS ============

    def estimate_depth_from_ball_size(self, radius_pixels):
        """
        Estimate ball's distance from camera using its apparent size.

        Physics Explanation:
        - Objects appear smaller when farther away
        - We use the "pinhole camera model"
        - Formula: depth = (real_size × focal_length) / pixel_size

        Math:
                Camera              Ball
                  |                  🏀
                  |                 /|
                  |                / |
                  |               /  | real_diameter
                  |              /   |
                  |             /    |
                  |____________/_____|
                      depth      pixel_size

        Args:
            radius_pixels: Ball radius on screen in pixels

        Returns:
            float: Estimated depth in meters or None
        """
        if radius_pixels <= 0 or not self.depth_calibrated:
            return None

        # Pinhole camera formula
        # depth = (real_diameter × focal_length) / (2 × radius_pixels)
        depth = (self.real_ball_diameter * self.camera_focal_length) / (2 * radius_pixels)

        return depth

    def calibrate_depth_estimation(self, ball_radius_pixels, known_distance_meters):
        """
        Calibrate depth estimation using ball at known distance.

        How to use:
        1. Place ball at known distance (e.g., 3 meters from camera)
        2. Measure its radius in pixels (from detection)
        3. Call this function with those values

        Math:
        - Rearrange pinhole formula to solve for focal_length
        - focal_length = (2 × radius_pixels × depth) / real_diameter

        Args:
            ball_radius_pixels: Ball radius on screen in pixels
            known_distance_meters: Actual distance from camera in meters
        """
        if ball_radius_pixels <= 0 or known_distance_meters <= 0:
            print("✗ Invalid calibration values")
            return False

        # Calculate camera focal length
        self.camera_focal_length = (2 * ball_radius_pixels * known_distance_meters) / self.real_ball_diameter

        self.depth_calibrated = True

        print(f"✓ Depth estimation calibrated!")
        print(f"  Focal length: {self.camera_focal_length:.1f} pixels")
        print(f"  Ball at {known_distance_meters}m = {ball_radius_pixels}px radius")

        return True

    def screen_to_world_coordinates(self, screen_x, screen_y, depth):
        """
        Convert 2D screen coordinates to 3D world coordinates.

        Explanation:
        - Screen shows 2D projection of 3D world
        - Need depth to reconstruct 3D position
        - Uses pinhole camera geometry

        Coordinate Systems:
        - Screen: (0,0) at top-left, Y increases downward
        - World: (0,0,0) at camera, Y increases upward, Z increases forward

        Args:
            screen_x, screen_y: Pixel coordinates
            depth: Distance from camera (Z-axis) in meters

        Returns:
            tuple: (world_x, world_y, world_z) in meters
        """
        if depth is None or depth <= 0:
            return None

        # Image dimensions (use actual frame dimensions)
        frame_width = self.frame_width
        frame_height = self.frame_height

        # Calculate offset from image center
        offset_x_pixels = screen_x - (frame_width / 2)
        offset_y_pixels = screen_y - (frame_height / 2)

        # Convert pixel offset to world coordinates using similar triangles
        # world_offset = (pixel_offset × depth) / focal_length
        world_x = (offset_x_pixels * depth) / self.camera_focal_length
        world_y = -(offset_y_pixels * depth) / self.camera_focal_length  # Negative: Y is flipped
        world_z = depth

        return (world_x, world_y, world_z)

    # ============ AUTOMATIC HOOP DETECTION METHODS ============

    def detect_hoop_by_color(self, frame):
        """
        Detect basketball hoop by its orange rim color.

        Basketball hoops have distinctive orange/red rims that stand out.
        This method uses HSV color filtering to find orange objects.

        HSV Color Space:
        - Hue (H): Color type (orange ≈ 10-20)
        - Saturation (S): Color intensity (100-255 for vivid)
        - Value (V): Brightness (100-255 for visible)

        Returns:
            tuple: (x, y) center of hoop or None
        """
        # Convert BGR to HSV color space
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Define orange color range for basketball rim
        # Hue: 5-20 (orange to red-orange)
        # Saturation: 100-255 (vivid colors)
        # Value: 100-255 (bright enough to see)
        lower_orange = np.array([5, 100, 100])
        upper_orange = np.array([20, 255, 255])

        # Create binary mask (white = orange, black = not orange)
        mask = cv2.inRange(hsv, lower_orange, upper_orange)

        # Clean up noise using morphology
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)   # Remove small noise
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)  # Fill small holes

        # Find contours (outlines) of orange regions
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if len(contours) > 0:
            # Find largest orange object (likely the rim)
            largest_contour = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(largest_contour)

            # Filter by minimum size
            if area > 500:
                # Calculate center using image moments
                # Moments = weighted averages of pixel locations
                M = cv2.moments(largest_contour)

                if M["m00"] != 0:  # Avoid division by zero
                    # Center X = m10 / m00, Center Y = m01 / m00
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])

                    return (cx, cy)

        return None

    def detect_hoop_by_circle(self, frame):
        """
        Detect hoop using circular shape detection (Hough Circle Transform).

        Basketball hoops are circular when viewed from certain angles.
        This method detects circles in the image.

        How it works:
        1. Convert to grayscale
        2. Apply edge detection
        3. Use Hough Circle Transform to find circles
        4. Filter by position and size

        Returns:
            tuple: (x, y) center of detected circle or None
        """
        # Convert to grayscale (circles easier to detect in grayscale)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Apply Gaussian blur to reduce noise
        gray = cv2.GaussianBlur(gray, (9, 9), 2)

        # Detect circles using Hough Circle Transform
        circles = cv2.HoughCircles(
            gray,
            cv2.HOUGH_GRADIENT,
            dp=1,                # Resolution ratio
            minDist=100,         # Minimum distance between circles
            param1=50,           # Edge detection threshold
            param2=30,           # Circle detection threshold (lower = more circles)
            minRadius=10,        # Minimum circle radius in pixels
            maxRadius=100        # Maximum circle radius in pixels
        )

        if circles is not None:
            circles = np.uint16(np.around(circles))

            # Filter circles by position
            # Hoop usually in upper 2/3 of frame
            frame_height = frame.shape[0]

            for circle in circles[0, :]:
                x, y, radius = circle

                # Keep only circles in reasonable position
                if y < frame_height * 0.66:  # Upper 66% of frame
                    return (int(x), int(y))

        return None

    def auto_detect_hoop(self, frame):
        """
        Try multiple methods to automatically detect hoop.

        Priority order:
        1. Color detection (orange rim) - most reliable
        2. Circle detection (shape) - works if rim visible
        3. Manual selection - fallback

        Returns:
            bool: True if hoop detected, False otherwise
        """
        # Try color detection first
        hoop_pos = self.detect_hoop_by_color(frame)

        if hoop_pos:
            self.hoop_position = hoop_pos
            print(f"✓ Hoop detected (color method) at: {hoop_pos}")
            return True

        # Try circle detection
        hoop_pos = self.detect_hoop_by_circle(frame)

        if hoop_pos:
            self.hoop_position = hoop_pos
            print(f"✓ Hoop detected (circle method) at: {hoop_pos}")
            return True

        print("✗ Automatic detection failed. Use manual selection.")
        return False

    def calculate_distance_from_hoop(self, ball_pos):
        if self.hoop_position is None:
            return None
        
        pixel_distance = np.sqrt(
            (ball_pos[0] - self.hoop_position[0])**2 + 
            (ball_pos[1] - self.hoop_position[1])**2
        )
        
        return pixel_distance / self.pixels_per_meter
    
    def draw_info(self, frame, ball_info):
        """
        Draw tracking information and predictions on the video frame.

        Python Concepts:
        - cv2.circle(): Draw circles (ball, hoop, apex)
        - cv2.line(): Draw lines (trajectory)
        - cv2.putText(): Draw text overlays
        - RGB color tuples: (B, G, R) format in OpenCV
        """
        # Draw enhanced hoop marker
        if self.hoop_position is not None:
            hx, hy = self.hoop_position

            # Draw target zone (make radius)
            hoop_radius_pixels = int(0.23 * self.pixels_per_meter * 0.7)  # Effective hoop radius
            cv2.circle(frame, (hx, hy), hoop_radius_pixels, (0, 255, 0), 1)

            # Draw outer glow ring
            cv2.circle(frame, (hx, hy), 20, (0, 255, 100), 2)

            # Draw inner target
            cv2.circle(frame, (hx, hy), 8, (0, 255, 0), -1)  # Filled center
            cv2.circle(frame, (hx, hy), 12, (0, 255, 0), 2)  # Outer ring

            # Draw crosshair
            crosshair_size = 30
            cv2.line(frame, (hx - crosshair_size, hy), (hx + crosshair_size, hy), (0, 255, 0), 2)
            cv2.line(frame, (hx, hy - crosshair_size), (hx, hy + crosshair_size), (0, 255, 0), 2)

            # Draw label with background
            label = "HOOP"
            label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
            label_x = hx - label_size[0] // 2
            label_y = hy - 40

            # Background rectangle
            cv2.rectangle(frame,
                         (label_x - 5, label_y - label_size[1] - 5),
                         (label_x + label_size[0] + 5, label_y + 5),
                         (0, 100, 0), -1)

            # Text
            cv2.putText(frame, label, (label_x, label_y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        if ball_info is not None:
            x, y, radius, depth = ball_info  # Now includes depth!
            # Draw ball
            cv2.circle(frame, (x, y), radius, (0, 0, 255), 2)
            cv2.circle(frame, (x, y), 2, (0, 0, 255), -1)

            # Draw simplified trajectory (only last 20 points)
            positions = list(self.ball_positions)[-20:]
            for i in range(1, len(positions)):
                if positions[i-1] is None or positions[i] is None:
                    continue
                cv2.line(frame, positions[i-1], positions[i], (255, 0, 0), 2)

            # Calculate distance
            distance = self.calculate_distance_from_hoop((x, y))
            if distance is not None:
                self.current_distance = distance

            # Display depth if calibrated (NEW!)
            if depth is not None:
                cv2.putText(frame, f"Depth:{depth:.2f}m", (x + 10, y - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)

        # === DRAW PREDICTIONS (NEW!) ===
        # Draw apex marker if available
        if self.apex_position is not None:
            apex_x, apex_y = int(self.apex_position[0]), int(self.apex_position[1])
            # Draw crosshair at apex
            cv2.drawMarker(frame, (apex_x, apex_y), (0, 255, 255),
                          cv2.MARKER_CROSS, 15, 2)
            cv2.putText(frame, "APEX", (apex_x + 10, apex_y - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)

        # Draw predicted landing point if available
        if self.predicted_landing_x is not None and self.hoop_position is not None:
            pred_x = int(self.predicted_landing_x)
            pred_y = int(self.hoop_position[1])

            # Draw X marker at predicted landing
            cv2.drawMarker(frame, (pred_x, pred_y), (255, 0, 255),
                          cv2.MARKER_TRIANGLE_DOWN, 15, 2)

        # Draw prediction result if available
        if self.predicted_outcome is not None and self.predicted_outcome.get('will_make') is not None:
            will_make = self.predicted_outcome['will_make']
            confidence = self.predicted_outcome.get('confidence', 'unknown')

            # Color: Green for make, Red for miss
            color = (0, 255, 0) if will_make else (0, 0, 255)
            text = f"{'MAKE' if will_make else 'MISS'} ({confidence})"

            cv2.putText(frame, text, (10, 75),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        # Simplified overlay text
        cv2.putText(frame, f"FPS:{self.fps:.1f}", (10, 25),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        cv2.putText(frame, f"Speed:{self.current_speed:.1f}m/s", (10, 50),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 165, 0), 1)

        return frame
    
    def get_dashboard_data(self):
        """
        Compile all tracking data for the web dashboard.

        Returns:
            dict: Complete tracking and prediction data

        Python Concepts:
        - Dictionary comprehension and creation
        - Conditional expressions (ternary operator)
        - Type conversion with round() and list()
        """
        trajectory = [{'x': pos[0], 'y': pos[1]} for pos in self.ball_positions if pos is not None]

        return {
            # Camera settings
            'frame_width': self.frame_width,
            'frame_height': self.frame_height,

            # Performance metrics
            'fps': round(self.fps, 1),
            'frame_latency': round(self.frame_latency * 1000, 1),
            'detection_time': round(self.detection_time * 1000, 1),
            'draw_time': round(self.draw_time * 1000, 1),

            # Ball tracking
            'distance': round(self.current_distance, 2) if self.current_distance else 0,
            'positions_tracked': len([p for p in self.ball_positions if p is not None]),
            'current_speed': round(self.current_speed, 2),
            'max_speed': round(self.max_speed, 2),
            'current_angle': round(self.current_angle, 1),
            'launch_angle': round(self.launch_angle, 1) if self.launch_angle is not None else 0,

            # Shot statistics
            'total_shots': self.total_shots,
            'made_shots': self.made_shots,
            'missed_shots': self.missed_shots,
            'accuracy': round((self.made_shots / self.total_shots * 100) if self.total_shots > 0 else 0, 1),

            # Trajectory visualization
            'trajectory': trajectory,
            'hoop_position': list(self.hoop_position) if self.hoop_position else None,

            # === PREDICTION DATA (NEW!) ===
            # Trajectory regression
            'has_prediction': self.trajectory_coefficients is not None,
            'trajectory_coefficients': list(self.trajectory_coefficients) if self.trajectory_coefficients is not None else None,

            # Shot prediction
            'predicted_outcome': self.predicted_outcome,
            'predicted_landing_x': round(self.predicted_landing_x, 2) if self.predicted_landing_x else None,

            # Apex data
            'apex_position': list(self.apex_position) if self.apex_position else None,
            'apex_height': round(self.apex_height, 2) if self.apex_height else None,

            # Entry angle
            'entry_angle': round(self.entry_angle, 1) if self.entry_angle else None,

            # Shot status
            'shot_in_progress': self.shot_in_progress,

            # === DEPTH ESTIMATION DATA (NEW!) ===
            'depth_calibrated': self.depth_calibrated,
            'current_depth': round(self.current_depth, 2) if self.current_depth else None,
            'camera_focal_length': round(self.camera_focal_length, 1),
        }
    
    def process_frame(self):
        ret, frame = self.cap.read()
        if not ret:
            return None
        
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
        
        # Measure detection time
        detect_start = time.time()
        ball_info = self.detect_ball(frame)
        self.detection_time = time.time() - detect_start

        # Update trajectory with timestamp
        if ball_info is not None:
            x, y, radius, depth = ball_info  # Now includes depth!
            self.ball_positions.append((x, y))
            self.ball_timestamps.append(current_time)
            
            # Calculate speed and angle
            speed, angle = self.calculate_speed_and_angle()
            self.current_speed = speed
            self.current_angle = angle
            
            # Update max speed
            if speed > self.max_speed:
                self.max_speed = speed
            
            # Calculate launch angle if this is a new shot
            if len(self.ball_positions) == 3:
                self.launch_angle = self.calculate_launch_angle()
        else:
            self.ball_positions.append(None)
            self.ball_timestamps.append(current_time)
            
            # Reset launch angle if ball is lost for too long
            none_count = sum(1 for p in list(self.ball_positions)[-10:] if p is None)
            if none_count > 7:
                self.launch_angle = None
        
        # Measure drawing time
        draw_start = time.time()
        display_frame = self.draw_info(frame, ball_info)
        self.draw_time = time.time() - draw_start

        # === TRAJECTORY PREDICTION (NEW!) ===
        # Only calculate predictions if we have enough data points
        valid_point_count = len([p for p in self.ball_positions if p is not None])

        if valid_point_count >= 5:
            # Fit trajectory parabola
            self.trajectory_coefficients = self.fit_trajectory()

            if self.trajectory_coefficients is not None:
                # Calculate apex (highest point)
                apex_data = self.calculate_apex()
                if apex_data:
                    self.apex_position = (apex_data['x'], apex_data['y'])
                    self.apex_height = apex_data['height_meters']

                # Predict shot outcome
                outcome = self.predict_shot_outcome()
                if outcome:
                    self.predicted_outcome = outcome
                    self.predicted_landing_x = outcome.get('predicted_x')

                    # Calculate entry angle
                    self.entry_angle = self.calculate_entry_angle()

        # Detect shot start/end for automatic make/miss tracking
        shot_status = self.detect_shot_start_end()
        if shot_status == 'ended':
            # Shot just finished - evaluate result
            result = self.evaluate_shot_result()
            print(f"🏀 Shot completed: {result.upper()}")

            # Clear trajectory for next shot
            self.ball_positions.clear()
            self.ball_timestamps.clear()
            self.trajectory_coefficients = None
            self.predicted_outcome = None

        # Store current frame with thread safety
        with self.frame_lock:
            self.current_frame = display_frame.copy()

        return display_frame
    
    def get_current_frame(self):
        with self.frame_lock:
            if self.current_frame is not None:
                return self.current_frame.copy()
        return None
    
    def run_headless(self):
        print("Basketball Tracker started in web mode")
        print("View dashboard at: http://localhost:8000")

        self.is_running = True
        last_emit_time = time.time()

        while self.is_running:
            frame = self.process_frame()

            if frame is None:
                break

            # Send data to web dashboard every 5 frames (more frequent updates)
            if self.frame_count % 5 == 0:
                data = self.get_dashboard_data()
                try:
                    socketio.emit('update', data)
                    # Log every 50 emits (every ~1.5 seconds at 30fps)
                    if self.frame_count % 150 == 0:
                        current_time = time.time()
                        elapsed = current_time - last_emit_time
                        print(f"📡 Emitting data: FPS={data['fps']:.1f}, Speed={data['current_speed']:.2f}m/s, Tracked={data['positions_tracked']}")
                        last_emit_time = current_time
                except Exception as e:
                    print(f"✗ Error emitting data: {e}")

            time.sleep(0.001)  # Minimal delay for max FPS
    
    def cleanup(self):
        self.is_running = False
        self.cap.release()
        print("Tracker stopped")

# Global tracker instance
tracker = None

def generate_frames():
    global tracker
    frame_skip = 0
    while True:
        if tracker is None:
            time.sleep(0.1)
            continue

        # Skip frames to reduce bandwidth and CPU usage
        frame_skip += 1
        if frame_skip % 2 != 0:  # Send every other frame
            time.sleep(0.03)
            continue

        frame = tracker.get_current_frame()

        if frame is None:
            time.sleep(0.01)
            continue

        # Reduce JPEG quality for faster encoding
        ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if not ret:
            continue

        frame_bytes = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

        time.sleep(0.03)  # ~30fps for video feed

@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@socketio.on('connect')
def handle_connect():
    print('✓ Client connected')
    emit('status', {'data': 'Connected'})
    # Send initial data when client connects
    if tracker:
        try:
            data = tracker.get_dashboard_data()
            emit('update', data)
            print('✓ Sent initial data to client')
        except Exception as e:
            print(f'✗ Error sending initial data: {e}')

@socketio.on('disconnect')
def handle_disconnect():
    print('✗ Client disconnected')

@socketio.on('reset_trajectory')
def handle_reset_trajectory():
    global tracker
    if tracker:
        tracker.ball_positions.clear()
        tracker.ball_timestamps.clear()
        print('Trajectory reset')

@socketio.on('set_hoop_position')
def handle_set_hoop_position(data):
    """
    Handle manual hoop position setting from web interface.
    User clicks on video to set hoop position.
    """
    global tracker
    if tracker:
        if data['x'] is not None and data['y'] is not None:
            tracker.hoop_position = (data['x'], data['y'])
            print(f'✓ Hoop position set manually: ({data["x"]}, {data["y"]})')
            emit('hoop_set_success', {'position': [data['x'], data['y']]})
        else:
            tracker.hoop_position = None
            print('✓ Hoop position cleared')
            emit('hoop_cleared')

@socketio.on('auto_detect_hoop')
def handle_auto_detect_hoop():
    """
    Handle automatic hoop detection request.
    User clicks "Auto-Detect Hoop" button on dashboard.

    Tries multiple detection methods:
    1. Color detection (orange rim)
    2. Circle detection (hoop shape)
    """
    global tracker
    if tracker:
        # Get current frame
        frame = tracker.get_current_frame()

        if frame is not None:
            # Try auto-detection
            success = tracker.auto_detect_hoop(frame)

            if success:
                emit('hoop_detected', {
                    'position': list(tracker.hoop_position),
                    'message': 'Hoop automatically detected!'
                })
            else:
                emit('hoop_detection_failed', {
                    'message': 'Could not detect hoop. Please set manually.'
                })
        else:
            emit('hoop_detection_failed', {
                'message': 'No camera frame available'
            })

@socketio.on('calibrate_depth')
def handle_calibrate_depth(data):
    """
    Handle depth calibration request.

    User provides:
    - Ball radius in current frame (from detection)
    - Known distance ball is from camera

    This calculates camera focal length for depth estimation.
    """
    global tracker
    if tracker:
        radius = data.get('radius')
        distance = data.get('distance')

        if radius and distance:
            success = tracker.calibrate_depth_estimation(radius, distance)

            if success:
                emit('depth_calibrated', {
                    'focal_length': tracker.camera_focal_length,
                    'message': f'Depth calibrated! Focal length: {tracker.camera_focal_length:.1f}px'
                })
            else:
                emit('calibration_failed', {
                    'message': 'Invalid calibration values'
                })
        else:
            emit('calibration_failed', {
                'message': 'Missing radius or distance values'
            })

def run_tracker():
    global tracker
    tracker = BasketballTracker(camera_index=0)
    tracker.run_headless()

if __name__ == "__main__":
    print("\n=== BASKETBALL SHOT TRACKER WEB DASHBOARD ===")
    print("Starting web server on http://localhost:8000")
    print("Open this URL in your browser to view the dashboard")
    print("Press Ctrl+C to stop")
    print("=" * 45 + "\n")

    tracker_thread = threading.Thread(target=run_tracker, daemon=True)
    tracker_thread.start()

    # Give tracker time to initialize
    print("Initializing camera...")
    time.sleep(2)
    print("✓ Camera ready\n")

    socketio.run(app, host='0.0.0.0', port=8000, debug=False, use_reloader=False)