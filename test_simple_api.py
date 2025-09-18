#!/usr/bin/env python3
"""
Simple API Test - Test the hotel suggestion API directly
"""

import requests
import json
import time

def test_api():
    """Test the hotel suggestion API"""
    
    # Wait for server to start
    print("⏳ Waiting for server to be ready...")
    for i in range(10):
        try:
            health_response = requests.get("http://127.0.0.1:8003/health", timeout=2)
            if health_response.status_code == 200:
                print("✅ Server is ready!")
                break
        except requests.exceptions.RequestException:
            time.sleep(1)
    else:
        print("❌ Server is not responding")
        return False
    
    # Test the suggestions endpoint
    print("🧪 Testing hotel suggestions...")
    
    test_data = {
        "stations": ["新宿駅"],
        "price_max": 15000,
        "date": "2025-12-25"
    }
    
    try:
        response = requests.post(
            "http://127.0.0.1:8003/api/suggest",
            json=test_data,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        print(f"📡 Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])
            print(f"🎉 Found {len(results)} hotel suggestions!")
            
            if results:
                print("\n🏨 Hotel recommendations:")
                for i, hotel in enumerate(results[:3]):
                    print(f"  {i+1}. {hotel['name']}")
                    print(f"     💰 Price: ¥{hotel['price_total']:,}/night")
                    print(f"     📍 Distance: {hotel['distance_text']}")
                    print(f"     🔗 Booking: {hotel['booking_url'][:50]}...")
                    print(f"     💡 Reason: {hotel['reason']}")
                    print()
                return True
            else:
                print("⚠️  No hotel suggestions found")
                return False
                
        else:
            print(f"❌ Error {response.status_code}: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")
        return False

if __name__ == "__main__":
    success = test_api()
    exit(0 if success else 1)