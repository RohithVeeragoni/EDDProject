cat > test_camera.py << 'EOF'
import cv2
print("Attempting to open camera...")
cap = cv2.VideoCapture(0)
print(f"Camera opened: {cap.isOpened()}")
if cap.isOpened():
    print("Reading a frame...")
    ret, frame = cap.read()
    print(f"Frame read successfully: {ret}")
cap.release()
print("Done!")
EOF