#!/usr/bin/env python3
"""
Performance Testing and Load Testing Suite

This script tests the performance characteristics of the hotel recommendation system
under various load conditions and measures key performance metrics.
"""

import asyncio
import httpx
import time
import statistics
from typing import List, Dict, Any
import json
import argparse
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import threading

# Configuration
BASE_URL = "http://127.0.0.1:8000"
DEFAULT_CONCURRENT_USERS = [1, 5, 10, 20, 50]
DEFAULT_DURATION = 60  # seconds
DEFAULT_RAMP_UP = 10   # seconds


class PerformanceTestResult:
    """Container for performance test results."""
    
    def __init__(self):
        self.response_times: List[float] = []
        self.status_codes: List[int] = []
        self.errors: List[str] = []
        self.start_time: float = 0
        self.end_time: float = 0
        self.concurrent_users: int = 0
        self.total_requests: int = 0
    
    @property
    def duration(self) -> float:
        return self.end_time - self.start_time
    
    @property
    def requests_per_second(self) -> float:
        return self.total_requests / self.duration if self.duration > 0 else 0
    
    @property
    def success_rate(self) -> float:
        successful = sum(1 for code in self.status_codes if 200 <= code < 400)
        return successful / len(self.status_codes) if self.status_codes else 0
    
    @property
    def avg_response_time(self) -> float:
        return statistics.mean(self.response_times) if self.response_times else 0
    
    @property
    def p95_response_time(self) -> float:
        return statistics.quantiles(self.response_times, n=20)[18] if len(self.response_times) > 0 else 0
    
    @property
    def p99_response_time(self) -> float:
        return statistics.quantiles(self.response_times, n=100)[98] if len(self.response_times) > 0 else 0


class LoadTester:
    """Load testing framework for the hotel recommendation system."""
    
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.test_scenarios = [
            {
                "name": "Popular Station - Tokyo",
                "station_name": "東京駅",
                "price_limit": 15000
            },
            {
                "name": "Popular Station - Shinjuku", 
                "station_name": "新宿駅",
                "price_limit": 12000
            },
            {
                "name": "Budget Request",
                "station_name": "渋谷駅", 
                "price_limit": 8000
            },
            {
                "name": "Premium Request",
                "station_name": "品川駅",
                "price_limit": 25000
            }
        ]
    
    async def make_request(self, client: httpx.AsyncClient, scenario: Dict[str, Any]) -> Dict[str, Any]:
        """Make a single API request and measure performance."""
        start_time = time.time()
        
        try:
            tomorrow = datetime.now() + timedelta(days=1)
            payload = {
                "station_name": scenario["station_name"],
                "price_limit": scenario["price_limit"],
                "date": tomorrow.strftime("%Y-%m-%d")
            }
            
            response = await client.post(
                f"{self.base_url}/api/suggest",
                json=payload,
                timeout=30.0
            )
            
            await response.aread()  # Read the response
            
            return {
                "response_time": time.time() - start_time,
                "status_code": response.status_code,
                "error": None
            }
                
        except Exception as e:
            return {
                "response_time": time.time() - start_time,
                "status_code": 0,
                "error": str(e)
            }
    
    async def run_load_test(self, concurrent_users: int, duration: int, 
                           ramp_up: int = 10) -> PerformanceTestResult:
        """Run a load test with specified parameters."""
        result = PerformanceTestResult()
        result.concurrent_users = concurrent_users
        result.start_time = time.time()
        
        print(f"🚀 Starting load test: {concurrent_users} users for {duration}s")
        
        # Create semaphore to limit concurrent requests
        semaphore = asyncio.Semaphore(concurrent_users)
        
        async def worker():
            """Worker coroutine that makes requests continuously."""
            async with httpx.AsyncClient() as client:
                end_time = time.time() + duration
                
                while time.time() < end_time:
                    async with semaphore:
                        # Randomly select a test scenario
                        scenario = self.test_scenarios[len(result.response_times) % len(self.test_scenarios)]
                        request_result = await self.make_request(client, scenario)
                        
                        result.response_times.append(request_result["response_time"])
                        result.status_codes.append(request_result["status_code"])
                        
                        if request_result["error"]:
                            result.errors.append(request_result["error"])
                        
                        # Small delay to prevent overwhelming the server
                        await asyncio.sleep(0.1)
        
        # Start workers with ramp-up
        workers = []
        for i in range(concurrent_users):
            # Stagger worker starts during ramp-up period
            if ramp_up > 0:
                await asyncio.sleep(ramp_up / concurrent_users)
            
            worker_task = asyncio.create_task(worker())
            workers.append(worker_task)
        
        # Wait for test duration
        await asyncio.sleep(duration)
        
        # Cancel all workers
        for worker_task in workers:
            worker_task.cancel()
        
        # Wait for workers to finish
        await asyncio.gather(*workers, return_exceptions=True)
        
        result.end_time = time.time()
        result.total_requests = len(result.response_times)
        
        return result
    
    async def run_stress_test(self) -> List[PerformanceTestResult]:
        """Run stress tests with increasing load."""
        results = []
        
        print("🔥 Starting stress test suite")
        print("=" * 50)
        
        for users in DEFAULT_CONCURRENT_USERS:
            try:
                result = await self.run_load_test(users, 30, ramp_up=5)
                results.append(result)
                
                print(f"✅ {users} users: {result.requests_per_second:.1f} RPS, "
                      f"{result.avg_response_time:.2f}s avg, "
                      f"{result.success_rate:.1%} success")
                
                # Cool down between tests
                await asyncio.sleep(2)
                
            except Exception as e:
                print(f"❌ {users} users: Failed - {e}")
        
        return results
    
    def generate_performance_report(self, results: List[PerformanceTestResult]) -> str:
        """Generate a comprehensive performance report."""
        if not results:
            return "No test results available"
        
        report = []
        report.append("🎯 PERFORMANCE TEST RESULTS")
        report.append("=" * 50)
        
        # Summary table
        report.append("\n📊 SUMMARY:")
        report.append(f"{'Users':<8} {'RPS':<8} {'Avg(s)':<8} {'P95(s)':<8} {'P99(s)':<8} {'Success%':<10}")
        report.append("-" * 60)
        
        for result in results:
            report.append(
                f"{result.concurrent_users:<8} "
                f"{result.requests_per_second:<8.1f} "
                f"{result.avg_response_time:<8.2f} "
                f"{result.p95_response_time:<8.2f} "
                f"{result.p99_response_time:<8.2f} "
                f"{result.success_rate:<10.1%}"
            )
        
        # Performance analysis
        report.append("\n📈 ANALYSIS:")
        
        max_rps_result = max(results, key=lambda r: r.requests_per_second)
        report.append(f"• Peak Performance: {max_rps_result.requests_per_second:.1f} RPS "
                     f"at {max_rps_result.concurrent_users} users")
        
        fastest_result = min(results, key=lambda r: r.avg_response_time)
        report.append(f"• Fastest Response: {fastest_result.avg_response_time:.2f}s "
                     f"at {fastest_result.concurrent_users} users")
        
        # Error analysis
        total_errors = sum(len(result.errors) for result in results)
        if total_errors > 0:
            report.append(f"• Total Errors: {total_errors}")
            
            # Most common errors
            all_errors = []
            for result in results:
                all_errors.extend(result.errors)
            
            if all_errors:
                from collections import Counter
                error_counts = Counter(all_errors)
                report.append("• Top Errors:")
                for error, count in error_counts.most_common(3):
                    report.append(f"  - {error}: {count} times")
        
        # Recommendations
        report.append("\n💡 RECOMMENDATIONS:")
        
        if max_rps_result.success_rate < 0.95:
            report.append("• Consider optimizing for higher success rates")
        
        if max_rps_result.p95_response_time > 5.0:
            report.append("• Response times are high - consider caching optimizations")
        
        if max_rps_result.requests_per_second < 10:
            report.append("• Low throughput - consider performance optimizations")
        else:
            report.append(f"• Good throughput achieved: {max_rps_result.requests_per_second:.1f} RPS")
        
        return "\n".join(report)
    
    def save_results(self, results: List[PerformanceTestResult], filename: str = "performance_results.json"):
        """Save test results to JSON file."""
        data = []
        for result in results:
            data.append({
                "concurrent_users": result.concurrent_users,
                "duration": result.duration,
                "total_requests": result.total_requests,
                "requests_per_second": result.requests_per_second,
                "avg_response_time": result.avg_response_time,
                "p95_response_time": result.p95_response_time,
                "p99_response_time": result.p99_response_time,
                "success_rate": result.success_rate,
                "error_count": len(result.errors),
                "response_times": result.response_times[:100],  # Sample for space
                "status_codes": result.status_codes[:100]  # Sample for space
            })
        
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        
        print(f"💾 Results saved to: {filename}")


async def main():
    """Main entry point for performance testing."""
    parser = argparse.ArgumentParser(description="Hotel Recommender Performance Testing")
    parser.add_argument("--url", default=BASE_URL, help="Base URL for testing")
    parser.add_argument("--users", nargs="+", type=int, default=DEFAULT_CONCURRENT_USERS,
                       help="Concurrent user counts to test")
    parser.add_argument("--duration", type=int, default=30, help="Test duration in seconds")
    parser.add_argument("--ramp-up", type=int, default=10, help="Ramp-up time in seconds")
    
    args = parser.parse_args()
    
    # Check if server is running
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{args.url}/health")
            if response.status_code != 200:
                print(f"❌ Server health check failed: {response.status_code}")
                return
        print("✅ Server is healthy, starting performance tests")
    except Exception as e:
        print(f"❌ Cannot connect to server at {args.url}: {e}")
        print("   Make sure the server is running with: python -m uvicorn api.main:app")
        return
    
    # Run tests
    tester = LoadTester(args.url)
    
    if args.users == DEFAULT_CONCURRENT_USERS:
        # Run full stress test suite
        results = await tester.run_stress_test()
    else:
        # Run custom test configuration
        results = []
        for user_count in args.users:
            result = await tester.run_load_test(user_count, args.duration, args.ramp_up)
            results.append(result)
            
            print(f"✅ {user_count} users: {result.requests_per_second:.1f} RPS, "
                  f"{result.avg_response_time:.2f}s avg")
            
            await asyncio.sleep(2)  # Cool down
    
    # Generate report
    report = tester.generate_performance_report(results)
    print("\n" + report)
    
    # Save results
    tester.save_results(results)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Performance testing interrupted")
    except Exception as e:
        print(f"\n❌ Performance testing failed: {e}")
        import traceback
        traceback.print_exc()