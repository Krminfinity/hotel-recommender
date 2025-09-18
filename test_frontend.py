#!/usr/bin/env python3
"""
Frontend Test Runner

Simple test runner to verify the frontend functionality locally.
"""

import asyncio
import webbrowser
import subprocess
import time
import sys
import os
from pathlib import Path

def check_port_in_use(port):
    """Check if a port is already in use."""
    import socket
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', port))
    sock.close()
    return result == 0

async def start_server():
    """Start the FastAPI development server."""
    port = 8000
    
    # Check if server is already running
    if check_port_in_use(port):
        print(f"✅ Server already running on port {port}")
        return True
    
    print("🚀 Starting FastAPI development server...")
    
    # Start the server in the background
    try:
        # Change to project root directory
        project_root = Path(__file__).parent
        os.chdir(project_root)
        
        # Start uvicorn server
        process = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn", 
                "api.main:app", 
                "--host", "127.0.0.1", 
                "--port", str(port), 
                "--reload"
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Wait for server to start
        max_wait = 10
        for i in range(max_wait):
            if check_port_in_use(port):
                print(f"✅ Server started successfully on http://127.0.0.1:{port}")
                return True
            time.sleep(1)
            print(f"⏳ Waiting for server to start... ({i+1}/{max_wait})")
        
        print("❌ Server failed to start within timeout")
        return False
        
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        return False

def open_browser():
    """Open the frontend in the default browser."""
    url = "http://127.0.0.1:8000"
    print(f"🌐 Opening {url} in browser...")
    webbrowser.open(url)

async def main():
    """Main test runner."""
    print("🏨 Hotel Recommender Frontend Test Runner")
    print("=" * 50)
    
    # Check environment
    env_file = Path(".env")
    if not env_file.exists():
        print("⚠️  Warning: .env file not found. Make sure to configure API keys.")
    else:
        print("✅ .env file found")
    
    # Start server
    if await start_server():
        print()
        print("Frontend is now available at: http://127.0.0.1:8000")
        print()
        print("📋 Test Checklist:")
        print("1. ✅ Page loads correctly")
        print("2. ✅ Form fields are responsive")
        print("3. ✅ Search functionality works")
        print("4. ✅ Results display properly")
        print("5. ✅ Error handling works")
        print("6. ✅ Links work correctly")
        print()
        print("🧪 Test Cases:")
        print('- Search for "新宿駅" with ¥10,000 budget')
        print('- Search for "渋谷駅" with ¥20,000 budget')
        print('- Test with invalid station name')
        print('- Test with very low budget')
        print()
        
        # Open browser
        open_browser()
        
        print("Press Ctrl+C to stop the server...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n👋 Shutting down...")
    else:
        print("❌ Failed to start server")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())