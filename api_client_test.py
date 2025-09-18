"""
Sample client for testing the Hotel Recommender API.

This script demonstrates how to interact with the API endpoints
and can be used for manual testing and validation.
"""

import httpx
import asyncio
import json
from datetime import date, timedelta

# API base URL (adjust if running on different host/port)
BASE_URL = "http://127.0.0.1:8000"


async def test_health_endpoint():
    """Test the health check endpoint."""
    print("Testing health endpoint...")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BASE_URL}/health")
            print(f"Health Status: {response.status_code}")
            print(f"Response: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
            return response.status_code == 200
        except httpx.RequestError as e:
            print(f"Health check failed: {e}")
            return False


async def test_suggest_endpoint():
    """Test the hotel suggestion endpoint."""
    print("\nTesting suggest endpoint...")
    
    # Sample request
    request_data = {
        "stations": ["東京駅", "新宿駅"],
        "price_max": 10000,
        "date": (date.today() + timedelta(days=7)).isoformat(),
        "weekday": None
    }
    
    print(f"Request: {json.dumps(request_data, indent=2, ensure_ascii=False)}")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                f"{BASE_URL}/api/suggest",
                json=request_data
            )
            
            print(f"Suggest Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"Response: {json.dumps(data, indent=2, ensure_ascii=False)}")
                
                if data.get("results"):
                    print(f"\n✅ Found {len(data['results'])} hotels!")
                    for i, hotel in enumerate(data["results"], 1):
                        print(f"  {i}. {hotel['name']} - ¥{hotel['price_total']:,} ({hotel['distance_text']})")
                        print(f"     {hotel['reason']}")
                else:
                    print("⚠️ No hotels found in response")
                
                return True
            else:
                print(f"Error: {response.text}")
                return False
                
        except httpx.RequestError as e:
            print(f"Request failed: {e}")
            return False


async def test_suggest_with_validation_error():
    """Test the suggest endpoint with invalid data."""
    print("\nTesting suggest endpoint with validation errors...")
    
    # Invalid request (empty stations)
    invalid_request = {
        "stations": [],  # Should cause validation error
        "price_max": 10000,
        "weekday": "fri"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{BASE_URL}/api/suggest",
                json=invalid_request
            )
            
            print(f"Validation Test Status: {response.status_code}")
            if response.status_code == 422:
                print("✅ Validation error correctly returned")
                print(f"Error details: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
                return True
            else:
                print(f"❌ Expected 422, got {response.status_code}")
                return False
                
        except httpx.RequestError as e:
            print(f"Validation test failed: {e}")
            return False


async def test_api_docs():
    """Test API documentation endpoints."""
    print("\nTesting API documentation...")
    
    async with httpx.AsyncClient() as client:
        try:
            # Test OpenAPI JSON
            response = await client.get(f"{BASE_URL}/openapi.json")
            if response.status_code == 200:
                print("✅ OpenAPI JSON available")
                schema = response.json()
                print(f"API Title: {schema.get('info', {}).get('title')}")
                print(f"Available endpoints: {list(schema.get('paths', {}).keys())}")
            else:
                print(f"❌ OpenAPI JSON failed: {response.status_code}")
            
            # Test Swagger UI
            response = await client.get(f"{BASE_URL}/docs")
            if response.status_code == 200:
                print("✅ Swagger UI available")
            else:
                print(f"❌ Swagger UI failed: {response.status_code}")
                
            return True
            
        except httpx.RequestError as e:
            print(f"API docs test failed: {e}")
            return False


async def run_all_tests():
    """Run all API tests."""
    print("🏨 Hotel Recommender API Client Test")
    print("=" * 50)
    
    results = []
    
    # Test health endpoint
    results.append(await test_health_endpoint())
    
    # Test suggest endpoint
    results.append(await test_suggest_endpoint())
    
    # Test validation
    results.append(await test_suggest_with_validation_error())
    
    # Test documentation
    results.append(await test_api_docs())
    
    # Summary
    print("\n" + "=" * 50)
    print("Test Summary:")
    passed = sum(results)
    total = len(results)
    
    print(f"✅ Passed: {passed}/{total}")
    
    if passed == total:
        print("🎉 All tests passed! API is working correctly.")
    else:
        print("⚠️ Some tests failed. Check the output above.")
    
    return passed == total


if __name__ == "__main__":
    print("Starting API tests...")
    print("Make sure the server is running: python -m api.main")
    print()
    
    try:
        success = asyncio.run(run_all_tests())
        exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n❌ Tests interrupted by user")
        exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        exit(1)