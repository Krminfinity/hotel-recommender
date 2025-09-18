#!/usr/bin/env python3
"""
Direct Rakuten Provider Test

Test the Rakuten Travel API integration directly without Google Places dependency.
"""

import asyncio
import os
import sys
from datetime import date, timedelta

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
from api.providers.hotel_rakuten import RakutenHotelProvider
from api.schemas import StationInfo

# Load environment variables
load_dotenv()

async def test_rakuten_provider():
    """Test Rakuten provider directly with known coordinates."""
    
    # Check if Rakuten API credentials are available
    app_id = os.getenv('RAKUTEN_APPLICATION_ID')
    affiliate_id = os.getenv('RAKUTEN_AFFILIATE_ID')
    
    if not app_id or not affiliate_id:
        print("❌ Rakuten API credentials not found in environment variables")
        print("   Make sure RAKUTEN_APPLICATION_ID and RAKUTEN_AFFILIATE_ID are set in .env")
        return False
    
    print(f"🔑 Using Rakuten Application ID: {app_id}")
    print(f"🔑 Using Rakuten Affiliate ID: {affiliate_id[:20]}...")
    
    # Initialize Rakuten provider
    provider = RakutenHotelProvider()
    
    # Test stations (Tokyo stations with known coordinates)
    test_stations = [
        {
            "name": "新宿駅周辺",
            "station": StationInfo(
                name="新宿駅",
                normalized_name="新宿",
                latitude=35.6896,
                longitude=139.7006,
                place_id=None,
                address="東京都新宿区"
            ),
            "price_max": 15000
        },
        {
            "name": "渋谷駅周辺", 
            "station": StationInfo(
                name="渋谷駅",
                normalized_name="渋谷",
                latitude=35.6580,
                longitude=139.7016,
                place_id=None,
                address="東京都渋谷区"
            ),
            "price_max": 10000
        }
    ]
    
    success_count = 0
    
    for test in test_stations:
        print(f"\n🔍 Testing {test['name']}...")
        try:
            hotels = await provider.find_hotels_near_stations(
                stations=[test["station"]],
                max_price_per_night=test["price_max"],
                check_in_date=date.today() + timedelta(days=30)
            )
            
            if hotels:
                print(f"✅ Found {len(hotels)} hotels")
                print("🏨 Top 3 hotels:")
                for i, hotel in enumerate(hotels[:3]):
                    print(f"   {i+1}. {hotel.name}")
                    print(f"      💰 Price: ¥{hotel.price_total:,}/night")
                    print(f"      🔗 URL: {hotel.booking_url[:50]}...")
                    if hotel.highlights:
                        print(f"      ✨ Features: {', '.join(hotel.highlights[:3])}")
                    print()
                success_count += 1
            else:
                print("⚠️  No hotels found")
                
        except Exception as e:
            print(f"❌ Error: {e}")
            
    print(f"\n📊 Success rate: {success_count}/{len(test_stations)} ({success_count/len(test_stations)*100:.1f}%)")
    
    if success_count > 0:
        print("🎉 Rakuten API integration is working!")
        return True
    else:
        print("❌ Rakuten API integration failed")
        return False

async def main():
    """Main test runner."""
    print("🏨 Direct Rakuten Provider Test")
    print("=" * 50)
    
    success = await test_rakuten_provider()
    
    if success:
        print("\n✅ Rakuten Travel API integration is fully functional!")
        print("🔗 Hotels can be booked through the provided booking URLs")
    else:
        print("\n❌ Rakuten API integration test failed")
    
    return success

if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n👋 Test interrupted")
        exit(1)
    except Exception as e:
        print(f"\n❌ Test execution failed: {e}")
        exit(1)