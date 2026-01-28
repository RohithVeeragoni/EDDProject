#!/usr/bin/env python3
"""
Basketball Tracker - Installation Test Script
Tests all dependencies and system requirements
"""

import sys

def test_imports():
    """Test if all required packages are installed"""
    print("🔍 Testing Python package imports...\n")
    
    tests = {
        'OpenCV': 'cv2',
        'NumPy': 'numpy',
        'Flask': 'flask',
        'Flask-SocketIO': 'flask_socketio',
        'Python-SocketIO': 'socketio'
    }
    
    passed = 0
    failed = 0
    
    for name, module in tests.items():
        try:
            __import__(module)
            print(f"✅ {name}: OK")
            passed += 1
        except ImportError as e:
            print(f"❌ {name}: FAILED ({e})")
            failed += 1
    
    print(f"\n📊 Results: {passed} passed, {failed} failed\n")
    return failed == 0

def test_camera():
    """Test if camera is accessible"""
    print("📷 Testing camera access...\n")
    
    try:
        import cv2
        cap = cv2.VideoCapture(0)
        
        if cap.isOpened():
            ret, frame = cap.read()
            cap.release()
            
            if ret:
                print(f"✅ Camera: OK (Resolution: {frame.shape[1]}x{frame.shape[0]})")
                return True
            else:
                print("❌ Camera: Could not read frame")
                return False
        else:
            print("❌ Camera: Could not open camera")
            print("   Try running: v4l2-ctl --list-devices")
            return False
    except Exception as e:
        print(f"❌ Camera test failed: {e}")
        return False

def test_network():
    """Test if network port is available"""
    print("\n🌐 Testing network configuration...\n")
    
    try:
        import socket
        
        # Test if port 5000 is available
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('localhost', 5000))
        sock.close()
        
        if result == 0:
            print("⚠️  Port 5000 is already in use")
            print("   Stop any running web servers or choose a different port")
            return False
        else:
            print("✅ Port 5000 is available")
            
        # Get local IP
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        print(f"ℹ️  Your local IP: {local_ip}")
        print(f"   Dashboard will be at: http://{local_ip}:5000")
        
        return True
    except Exception as e:
        print(f"❌ Network test failed: {e}")
        return False

def test_file_structure():
    """Test if all required files exist"""
    print("\n📁 Testing file structure...\n")
    
    import os
    
    required_files = [
        'basketball_tracker_web.py',
        'templates/dashboard.html',
        'requirements.txt',
        'README.md'
    ]
    
    all_exist = True
    
    for file in required_files:
        if os.path.exists(file):
            print(f"✅ {file}: Found")
        else:
            print(f"❌ {file}: Missing")
            all_exist = False
    
    return all_exist

def print_system_info():
    """Print system information"""
    print("\n💻 System Information:\n")
    
    import platform
    print(f"OS: {platform.system()} {platform.release()}")
    print(f"Python: {sys.version.split()[0]}")
    
    try:
        import cv2
        print(f"OpenCV: {cv2.__version__}")
    except:
        pass
    
    try:
        import numpy as np
        print(f"NumPy: {np.__version__}")
    except:
        pass

def main():
    print("="*60)
    print("🏀 BASKETBALL TRACKER - INSTALLATION TEST")
    print("="*60 + "\n")
    
    print_system_info()
    
    # Run all tests
    imports_ok = test_imports()
    camera_ok = test_camera()
    network_ok = test_network()
    files_ok = test_file_structure()
    
    print("\n" + "="*60)
    print("📋 SUMMARY")
    print("="*60 + "\n")
    
    all_ok = imports_ok and camera_ok and network_ok and files_ok
    
    if all_ok:
        print("✅ All tests passed! You're ready to run the tracker.")
        print("\n🚀 To start:")
        print("   python3 basketball_tracker_web.py")
        print("\n🌐 Then open:")
        print("   http://localhost:5000")
    else:
        print("❌ Some tests failed. Please check the errors above.")
        print("\n🔧 Common fixes:")
        print("   1. Install missing packages: pip3 install --break-system-packages -r requirements.txt")
        print("   2. Check camera connection: ls -l /dev/video*")
        print("   3. Verify file structure matches README")
    
    print("\n" + "="*60 + "\n")
    
    return 0 if all_ok else 1

if __name__ == "__main__":
    sys.exit(main())
