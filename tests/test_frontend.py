"""
Frontend Integration Tests

Tests for the frontend interface and API integration.
"""

import pytest
import httpx
from fastapi.testclient import TestClient
import os

# Import the app
from api.main import app

@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)

@pytest.fixture
def sample_request():
    """Sample hotel search request."""
    return {
        "station_name": "新宿駅",
        "price_limit": 10000,
        "date": "2025-09-19"
    }

class TestFrontendEndpoints:
    """Test frontend-related endpoints."""
    
    def test_root_endpoint_serves_html(self, client):
        """Test that root endpoint serves the HTML page."""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
    
    def test_static_files_accessible(self, client):
        """Test that static files are accessible."""
        # Test CSS file
        css_response = client.get("/static/css/style.css")
        assert css_response.status_code == 200
        assert "text/css" in css_response.headers.get("content-type", "")
        
        # Test JavaScript file
        js_response = client.get("/static/js/app.js")
        assert js_response.status_code == 200
        assert "javascript" in js_response.headers.get("content-type", "").lower()
    
    def test_api_suggest_endpoint_exists(self, client):
        """Test that the API suggest endpoint exists and handles requests."""
        # This will likely fail without proper API keys, but should not return 404
        response = client.post("/api/suggest", json={
            "station_name": "テスト駅",
            "price_limit": 5000
        })
        
        # Should not be 404 (endpoint exists)
        assert response.status_code != 404
        # Could be 500 (internal error) or other status depending on API keys
        assert response.status_code in [200, 400, 422, 500]
    
    def test_health_endpoint(self, client):
        """Test the health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data

class TestFrontendContent:
    """Test frontend content and structure."""
    
    def test_html_contains_required_elements(self, client):
        """Test that HTML contains required form elements."""
        response = client.get("/")
        content = response.text
        
        # Check for form elements
        assert 'id="hotel-search-form"' in content
        assert 'id="station-name"' in content
        assert 'id="price-limit"' in content
        assert 'id="date"' in content
        assert 'id="weekday"' in content
        
        # Check for result sections
        assert 'id="results-section"' in content
        assert 'id="error-section"' in content
        
        # Check for JavaScript inclusion
        assert '/static/js/app.js' in content
        
        # Check for CSS inclusion
        assert '/static/css/style.css' in content
    
    def test_css_contains_styling(self, client):
        """Test that CSS file contains expected styles."""
        response = client.get("/static/css/style.css")
        content = response.text
        
        # Check for key CSS classes
        assert '.container' in content
        assert '.search-form' in content
        assert '.hotel-card' in content
        assert '.results-section' in content
        assert '.error-section' in content
    
    def test_js_contains_functionality(self, client):
        """Test that JavaScript file contains expected functionality."""
        response = client.get("/static/js/app.js")
        content = response.text
        
        # Check for key JavaScript components
        assert 'HotelRecommenderApp' in content
        assert 'handleSubmit' in content
        assert 'searchHotels' in content
        assert 'displayResults' in content
        assert 'displayError' in content
        assert '/api/suggest' in content

@pytest.mark.skipif(
    not os.getenv("GOOGLE_PLACES_API_KEY") or not os.getenv("RAKUTEN_APP_ID"),
    reason="API keys not configured"
)
class TestFrontendIntegration:
    """Integration tests with real APIs (requires API keys)."""
    
    @pytest.mark.asyncio
    async def test_frontend_api_integration(self):
        """Test frontend API integration with real backend."""
        async with httpx.AsyncClient() as client:
            # Test health endpoint
            health_response = await client.get("http://127.0.0.1:8000/health")
            if health_response.status_code == 200:
                # Server is running, test suggest endpoint
                suggest_response = await client.post(
                    "http://127.0.0.1:8000/api/suggest",
                    json={
                        "station_name": "新宿駅",
                        "price_limit": 10000
                    }
                )
                
                # Should get either success or proper error
                assert suggest_response.status_code in [200, 400, 404, 500]
                
                if suggest_response.status_code == 200:
                    data = suggest_response.json()
                    assert "suggestions" in data
                    assert isinstance(data["suggestions"], list)

if __name__ == "__main__":
    # Run basic tests
    import subprocess
    import sys
    
    print("🧪 Running frontend tests...")
    result = subprocess.run([
        sys.executable, "-m", "pytest", 
        __file__, 
        "-v", 
        "--tb=short"
    ])
    
    sys.exit(result.returncode)