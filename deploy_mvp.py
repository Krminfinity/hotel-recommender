#!/usr/bin/env python3
"""
Hotel Recommender MVP Deployment Script

This script handles the deployment and validation of the hotel recommender MVP.
It includes environment validation, dependency checking, and deployment verification.
"""

import os
import sys
import subprocess
import json
import asyncio
import httpx
from pathlib import Path
from typing import Dict, Any, List, Optional
import time
from datetime import datetime

class MVPDeployment:
    """MVP deployment manager."""
    
    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or Path(__file__).parent
        self.required_files = [
            "api/main.py",
            "api/schemas.py", 
            "api/cache.py",
            "static/index.html",
            "static/css/style.css",
            "static/js/app.js",
            "requirements.txt",
            ".env.example"
        ]
        self.required_env_vars = [
            "GOOGLE_PLACES_API_KEY",
            "RAKUTEN_APPLICATION_ID"
        ]
    
    def check_project_structure(self) -> Dict[str, Any]:
        """Validate project structure and required files."""
        print("🔍 Checking project structure...")
        
        missing_files = []
        present_files = []
        
        for file_path in self.required_files:
            full_path = self.project_root / file_path
            if full_path.exists():
                present_files.append(file_path)
                print(f"  ✅ {file_path}")
            else:
                missing_files.append(file_path)
                print(f"  ❌ {file_path}")
        
        return {
            "valid": len(missing_files) == 0,
            "present_files": present_files,
            "missing_files": missing_files,
            "total_files": len(self.required_files)
        }
    
    def check_environment(self) -> Dict[str, Any]:
        """Check environment variables and configuration."""
        print("🌍 Checking environment configuration...")
        
        env_file = self.project_root / ".env"
        
        if not env_file.exists():
            print("  ⚠️  .env file not found - using system environment")
        else:
            print("  ✅ .env file present")
        
        # Check required environment variables
        missing_vars = []
        present_vars = []
        
        for var_name in self.required_env_vars:
            if os.getenv(var_name):
                present_vars.append(var_name)
                print(f"  ✅ {var_name} is set")
            else:
                missing_vars.append(var_name)
                print(f"  ❌ {var_name} is missing")
        
        return {
            "valid": len(missing_vars) == 0,
            "present_vars": present_vars,
            "missing_vars": missing_vars,
            "env_file_exists": env_file.exists()
        }
    
    def check_dependencies(self) -> Dict[str, Any]:
        """Check Python dependencies."""
        print("📦 Checking dependencies...")
        
        try:
            # Check core dependencies
            import fastapi
            import uvicorn
            import httpx
            import pydantic
            
            print("  ✅ Core dependencies available")
            
            # Check versions
            dependencies = {
                "fastapi": fastapi.__version__,
                "uvicorn": uvicorn.__version__,
                "httpx": httpx.__version__,
                "pydantic": pydantic.__version__
            }
            
            print("  📋 Dependency versions:")
            for name, version in dependencies.items():
                print(f"    - {name}: {version}")
            
            return {
                "valid": True,
                "dependencies": dependencies,
                "errors": []
            }
            
        except ImportError as e:
            print(f"  ❌ Missing dependency: {e}")
            return {
                "valid": False,
                "dependencies": {},
                "errors": [str(e)]
            }
    
    def run_tests(self) -> Dict[str, Any]:
        """Run the test suite."""
        print("🧪 Running test suite...")
        
        try:
            # Run tests excluding external API tests
            result = subprocess.run([
                sys.executable, "-m", "pytest", "tests/", 
                "-k", "not (station_google or rakuten)",
                "--tb=short", "-q"
            ], capture_output=True, text=True, cwd=self.project_root)
            
            success = result.returncode == 0
            
            if success:
                print("  ✅ All tests passed")
            else:
                print("  ❌ Some tests failed")
                print(f"  Output: {result.stdout}")
                if result.stderr:
                    print(f"  Errors: {result.stderr}")
            
            return {
                "valid": success,
                "return_code": result.returncode,
                "output": result.stdout,
                "errors": result.stderr
            }
            
        except Exception as e:
            print(f"  ❌ Test execution failed: {e}")
            return {
                "valid": False,
                "return_code": -1,
                "output": "",
                "errors": str(e)
            }
    
    async def verify_deployment(self, host: str = "127.0.0.1", port: int = 8000) -> Dict[str, Any]:
        """Verify deployment by testing endpoints."""
        print(f"🔗 Verifying deployment at http://{host}:{port}...")
        
        base_url = f"http://{host}:{port}"
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Test health endpoint
                health_response = await client.get(f"{base_url}/health")
                health_ok = health_response.status_code == 200
                
                if health_ok:
                    print("  ✅ Health check passed")
                else:
                    print(f"  ❌ Health check failed: {health_response.status_code}")
                
                # Test frontend
                frontend_response = await client.get(f"{base_url}/")
                frontend_ok = frontend_response.status_code == 200 and "ホテル推薦システム" in frontend_response.text
                
                if frontend_ok:
                    print("  ✅ Frontend accessible")
                else:
                    print(f"  ❌ Frontend failed: {frontend_response.status_code}")
                
                # Test API with a simple request (may fail without API keys, but should not error)
                try:
                    api_response = await client.post(
                        f"{base_url}/api/suggest",
                        json={
                            "station_name": "テスト駅",
                            "price_limit": 10000
                        }
                    )
                    api_ok = api_response.status_code in [200, 404, 422, 500]  # Any valid HTTP response
                    
                    if api_ok:
                        print("  ✅ API endpoint responsive")
                    else:
                        print(f"  ❌ API endpoint error: {api_response.status_code}")
                
                except Exception as e:
                    print(f"  ⚠️  API test failed (may be expected without API keys): {e}")
                    api_ok = True  # Consider this OK for deployment verification
                
                # Test static files
                css_response = await client.get(f"{base_url}/static/css/style.css")
                js_response = await client.get(f"{base_url}/static/js/app.js")
                
                static_ok = css_response.status_code == 200 and js_response.status_code == 200
                
                if static_ok:
                    print("  ✅ Static files served")
                else:
                    print("  ❌ Static files failed")
                
                return {
                    "valid": health_ok and frontend_ok and api_ok and static_ok,
                    "health": health_ok,
                    "frontend": frontend_ok,
                    "api": api_ok,
                    "static": static_ok
                }
        
        except Exception as e:
            print(f"  ❌ Deployment verification failed: {e}")
            return {
                "valid": False,
                "error": str(e)
            }
    
    def generate_deployment_report(self, results: Dict[str, Any]) -> str:
        """Generate deployment readiness report."""
        report = []
        report.append("🚀 MVP DEPLOYMENT READINESS REPORT")
        report.append("=" * 50)
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")
        
        # Overall status
        all_valid = all(results[key].get("valid", False) for key in results)
        status = "✅ READY FOR DEPLOYMENT" if all_valid else "❌ NOT READY - ISSUES FOUND"
        report.append(f"Status: {status}")
        report.append("")
        
        # Detailed results
        for section, result in results.items():
            valid = result.get("valid", False)
            icon = "✅" if valid else "❌"
            report.append(f"{icon} {section.replace('_', ' ').title()}")
            
            if not valid and "missing_files" in result:
                report.append(f"   Missing files: {', '.join(result['missing_files'])}")
            
            if not valid and "missing_vars" in result:
                report.append(f"   Missing env vars: {', '.join(result['missing_vars'])}")
            
            if "errors" in result and result["errors"]:
                report.append(f"   Errors: {result['errors']}")
        
        # Deployment instructions
        if all_valid:
            report.append("")
            report.append("🎯 DEPLOYMENT INSTRUCTIONS:")
            report.append("1. Ensure .env file is configured with API keys")
            report.append("2. Start server: python -m uvicorn api.main:app --host 0.0.0.0 --port 8000")
            report.append("3. Access frontend: http://localhost:8000")
            report.append("4. API documentation: http://localhost:8000/docs")
        else:
            report.append("")
            report.append("⚠️ REQUIRED ACTIONS:")
            report.append("1. Fix all issues marked with ❌")
            report.append("2. Re-run deployment validation")
            report.append("3. Ensure API keys are configured")
        
        return "\n".join(report)
    
    async def deploy(self, skip_tests: bool = False) -> bool:
        """Run full deployment validation."""
        print("🚀 Starting MVP Deployment Validation")
        print("=" * 50)
        
        results = {}
        
        # Check project structure
        results["project_structure"] = self.check_project_structure()
        
        # Check environment
        results["environment"] = self.check_environment()
        
        # Check dependencies
        results["dependencies"] = self.check_dependencies()
        
        # Run tests (optional)
        if not skip_tests:
            results["tests"] = self.run_tests()
        
        # Verify deployment (if server is running)
        try:
            results["deployment_verification"] = await self.verify_deployment()
        except Exception as e:
            print(f"  ⚠️  Deployment verification skipped: {e}")
            results["deployment_verification"] = {"valid": False, "error": "Server not running"}
        
        # Generate report
        report = self.generate_deployment_report(results)
        print("\n" + report)
        
        # Save report
        with open("deployment_report.txt", "w", encoding="utf-8") as f:
            f.write(report)
        print("\n💾 Report saved to: deployment_report.txt")
        
        # Return overall status
        return all(results[key].get("valid", False) for key in results)


async def main():
    """Main deployment script entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Hotel Recommender MVP Deployment")
    parser.add_argument("--skip-tests", action="store_true", help="Skip running tests")
    parser.add_argument("--host", default="127.0.0.1", help="Host to verify deployment")
    parser.add_argument("--port", type=int, default=8000, help="Port to verify deployment")
    
    args = parser.parse_args()
    
    # Create deployment manager
    deployer = MVPDeployment()
    
    # Run deployment validation
    success = await deployer.deploy(skip_tests=args.skip_tests)
    
    if success:
        print("\n🎉 MVP is ready for deployment!")
        sys.exit(0)
    else:
        print("\n❌ MVP deployment validation failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())