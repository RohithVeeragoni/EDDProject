import cv2

print("Testing camera access...")

# Try to open the camera
cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("❌ ERROR: Cannot open camera with index 0")
    print("Trying camera index 1...")
    cap = cv2.VideoCapture(1)
    
    if not cap.isOpened():
        print("❌ ERROR: Cannot open camera with index 1 either")
        print("\nPossible issues:")
        print("1. Camera is being used by another application")
        print("2. Python doesn't have camera permissions")
        print("3. No camera detected")
    else:
        print("✅ SUCCESS: Camera opened with index 1")
        ret, frame = cap.read()
        if ret:
            print(f"✅ Camera is working! Frame size: {frame.shape}")
        cap.release()
else:
    print("✅ SUCCESS: Camera opened with index 0")
    ret, frame = cap.read()
    if ret:
        print(f"✅ Camera is working! Frame size: {frame.shape}")
    else:
        print("❌ ERROR: Camera opened but cannot read frames")
    cap.release()

print("\nTest complete!")