"""
End-to-End Integration Tests

Comprehensive integration tests for the complete hotel recommendation workflow.
Tests the entire system from frontend API calls to backend processing.
"""

import asyncio
import pytest
import httpx
import os
import time
from typing import Dict, Any, List, Optional
import json
from datetime import datetime, timedelta

# Configuration
BASE_URL = "http://127.0.0.1:8001"
TIMEOUT = 30.0


class E2ETestRunner:
    """End-to-end test runner for hotel recommendation system."""
    
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.client: Optional[httpx.AsyncClient] = None
        self.test_results = []
    
    async def __aenter__(self):
        """Async context manager entry."""
        self.client = httpx.AsyncClient(timeout=TIMEOUT)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.client:
            await self.client.aclose()
    
    async def check_server_health(self) -> bool:
        """Check if the server is running and healthy."""
        try:
            if not self.client:
                return False
            response = await self.client.get(f"{self.base_url}/health")
            return response.status_code == 200
        except Exception as e:
            print(f"❌ Server health check failed: {e}")
            return False
    
    async def test_frontend_loading(self) -> Dict[str, Any]:
        """Test frontend page loading."""
        test_name = "Frontend Page Loading"
        start_time = time.time()
        
        try:
            if not self.client:
                raise RuntimeError("HTTP client not initialized")
                
            # Test main page
            response = await self.client.get(f"{self.base_url}/")
            assert response.status_code == 200
            assert "text/html" in response.headers.get("content-type", "")
            assert "ホテル推薦システム" in response.text
            
            # Test static files
            css_response = await self.client.get(f"{self.base_url}/static/css/style.css")
            assert css_response.status_code == 200
            
            js_response = await self.client.get(f"{self.base_url}/static/js/app.js")
            assert js_response.status_code == 200
            
            duration = time.time() - start_time
            
            return {
                "test": test_name,
                "status": "PASS",
                "duration": duration,
                "details": "All frontend resources loaded successfully"
            }
            
        except Exception as e:
            return {
                "test": test_name,
                "status": "FAIL",
                "duration": time.time() - start_time,
                "error": str(e)
            }
    
    async def test_api_suggestion_workflow(self, station_name: str, price_limit: int, 
                                          expected_status: int = 200) -> Dict[str, Any]:
        """Test complete API suggestion workflow."""
        test_name = f"API Workflow: {station_name} (¥{price_limit:,})"
        start_time = time.time()
        
        try:
            if not self.client:
                raise RuntimeError("HTTP client not initialized")
                
            # Prepare request
            tomorrow = datetime.now() + timedelta(days=1)
            request_data = {
                "station_name": station_name,
                "price_limit": price_limit,
                "date": tomorrow.strftime("%Y-%m-%d")
            }
            
            # Make API request
            response = await self.client.post(
                f"{self.base_url}/api/suggest",
                json=request_data
            )
            
            duration = time.time() - start_time
            
            # Validate response
            assert response.status_code == expected_status
            
            if response.status_code == 200:
                data = response.json()
                assert "suggestions" in data
                assert isinstance(data["suggestions"], list)
                
                # Validate hotel data structure
                for hotel in data["suggestions"]:
                    assert "name" in hotel
                    assert "price" in hotel or hotel["price"] is None
                    if "booking_url" in hotel:
                        assert hotel["booking_url"].startswith("http")
                
                return {
                    "test": test_name,
                    "status": "PASS",
                    "duration": duration,
                    "details": f"Found {len(data['suggestions'])} suggestions",
                    "response_size": len(response.text),
                    "hotels_found": len(data["suggestions"])
                }
            else:
                # Handle error responses
                error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text
                return {
                    "test": test_name,
                    "status": "EXPECTED_FAIL" if expected_status != 200 else "FAIL",
                    "duration": duration,
                    "details": f"Status {response.status_code}: {error_data}",
                    "response_size": len(response.text)
                }
                
        except Exception as e:
            return {
                "test": test_name,
                "status": "FAIL",
                "duration": time.time() - start_time,
                "error": str(e)
            }
    
    async def test_error_handling(self) -> List[Dict[str, Any]]:
        """Test various error scenarios."""
        error_tests = []
        
        # Test invalid station name
        error_tests.append(await self.test_api_suggestion_workflow(
            "存在しない駅名12345", 10000, expected_status=404
        ))
        
        # Test invalid price (too low)
        error_tests.append(await self.test_api_suggestion_workflow(
            "新宿駅", 100, expected_status=200  # May return empty results
        ))
        
        # Test invalid request format
        start_time = time.time()
        try:
            if not self.client:
                raise RuntimeError("HTTP client not initialized")
                
            response = await self.client.post(
                f"{self.base_url}/api/suggest",
                json={"invalid": "data"}
            )
            
            error_tests.append({
                "test": "Invalid Request Format",
                "status": "PASS" if response.status_code == 422 else "FAIL",
                "duration": time.time() - start_time,
                "details": f"Status {response.status_code} (expected 422)"
            })
            
        except Exception as e:
            error_tests.append({
                "test": "Invalid Request Format",
                "status": "FAIL",
                "duration": time.time() - start_time,
                "error": str(e)
            })
        
        return error_tests
    
    async def test_performance_benchmarks(self) -> Dict[str, Any]:
        """Run performance benchmarks."""
        test_name = "Performance Benchmarks"
        start_time = time.time()
        
        try:
            # Test multiple concurrent requests
            concurrent_requests = 5
            tasks = []
            
            for i in range(concurrent_requests):
                task = self.test_api_suggestion_workflow(
                    "新宿駅", 10000 + (i * 1000)
                )
                tasks.append(task)
            
            # Execute concurrent requests
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Calculate metrics
            total_duration = time.time() - start_time
            successful_requests = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "PASS")
            avg_duration = sum(r["duration"] for r in results if isinstance(r, dict) and "duration" in r) / len(results)
            
            return {
                "test": test_name,
                "status": "PASS",
                "duration": total_duration,
                "details": f"{successful_requests}/{concurrent_requests} requests successful",
                "concurrent_requests": concurrent_requests,
                "average_request_duration": avg_duration,
                "requests_per_second": concurrent_requests / total_duration
            }
            
        except Exception as e:
            return {
                "test": test_name,
                "status": "FAIL",
                "duration": time.time() - start_time,
                "error": str(e)
            }
    
    async def run_all_tests(self) -> List[Dict[str, Any]]:
        """Run all end-to-end tests."""
        all_results = []
        
        print("🚀 Starting End-to-End Integration Tests")
        print("=" * 60)
        
        # Check server health
        print("🔍 Checking server health...")
        if not await self.check_server_health():
            return [{
                "test": "Server Health Check",
                "status": "FAIL",
                "error": "Server is not running or unhealthy"
            }]
        print("✅ Server is healthy")
        
        # Test frontend loading
        print("\n📱 Testing frontend loading...")
        frontend_result = await self.test_frontend_loading()
        all_results.append(frontend_result)
        print(f"  {frontend_result['status']}: {frontend_result['test']}")
        
        # Test API workflows with various scenarios
        print("\n🏨 Testing API workflows...")
        
        # Popular stations
        stations_to_test = [
            ("新宿駅", 15000),
            ("渋谷駅", 12000),
            ("東京駅", 20000),
            ("品川駅", 18000),
        ]
        
        for station, price in stations_to_test:
            result = await self.test_api_suggestion_workflow(station, price)
            all_results.append(result)
            print(f"  {result['status']}: {result['test']}")
            
            # Add small delay between requests to be respectful to APIs
            await asyncio.sleep(0.5)
        
        # Test error handling
        print("\n❌ Testing error handling...")
        error_results = await self.test_error_handling()
        all_results.extend(error_results)
        for result in error_results:
            print(f"  {result['status']}: {result['test']}")
        
        # Performance benchmarks
        print("\n⚡ Running performance benchmarks...")
        perf_result = await self.test_performance_benchmarks()
        all_results.append(perf_result)
        print(f"  {perf_result['status']}: {perf_result['test']}")
        
        return all_results


async def run_integration_tests():
    """Main entry point for integration tests."""
    async with E2ETestRunner() as runner:
        results = await runner.run_all_tests()
        
        # Generate report
        print("\n" + "=" * 60)
        print("📊 TEST RESULTS SUMMARY")
        print("=" * 60)
        
        total_tests = len(results)
        passed_tests = sum(1 for r in results if r["status"] == "PASS")
        failed_tests = sum(1 for r in results if r["status"] == "FAIL")
        expected_fails = sum(1 for r in results if r["status"] == "EXPECTED_FAIL")
        
        print(f"Total Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests}")
        print(f"❌ Failed: {failed_tests}")
        print(f"⚠️  Expected Fails: {expected_fails}")
        print(f"Success Rate: {(passed_tests + expected_fails) / total_tests * 100:.1f}%")
        
        # Detailed results
        print("\n📋 DETAILED RESULTS:")
        for result in results:
            status_icon = {
                "PASS": "✅",
                "FAIL": "❌",
                "EXPECTED_FAIL": "⚠️"
            }.get(result["status"], "❓")
            
            print(f"\n{status_icon} {result['test']}")
            if "duration" in result:
                print(f"   Duration: {result['duration']:.2f}s")
            if "details" in result:
                print(f"   Details: {result['details']}")
            if "error" in result:
                print(f"   Error: {result['error']}")
        
        # Performance metrics
        perf_results = [r for r in results if "requests_per_second" in r]
        if perf_results:
            print(f"\n⚡ PERFORMANCE METRICS:")
            for result in perf_results:
                print(f"   Requests/Second: {result['requests_per_second']:.2f}")
                print(f"   Average Duration: {result['average_request_duration']:.2f}s")
        
        # Save results to file
        with open("e2e_test_results.json", "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"\n💾 Results saved to: e2e_test_results.json")
        
        return results


# Pytest integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("GOOGLE_PLACES_API_KEY") or not os.getenv("RAKUTEN_APP_ID"),
    reason="API keys required for integration tests"
)
async def test_full_integration():
    """Pytest wrapper for full integration tests."""
    results = await run_integration_tests()
    
    # Assert overall success
    failed_tests = [r for r in results if r["status"] == "FAIL"]
    if failed_tests:
        pytest.fail(f"Integration tests failed: {[r['test'] for r in failed_tests]}")


if __name__ == "__main__":
    # Run integration tests directly
    print("🏨 Hotel Recommender - End-to-End Integration Tests")
    print("=" * 60)
    print("⚠️  Make sure the server is running on http://127.0.0.1:8000")
    print("⚠️  API keys should be configured in .env file")
    print()
    
    try:
        asyncio.run(run_integration_tests())
    except KeyboardInterrupt:
        print("\n👋 Tests interrupted by user")
    except Exception as e:
        print(f"\n❌ Test execution failed: {e}")
        import traceback
        traceback.print_exc()