"""
Test cases for the Hotel Recommender API
"""

import pytest
from fastapi.testclient import TestClient

from api.main import app

# Create test client
client = TestClient(app)


def test_health_endpoint():
    """Test the health check endpoint"""
    response = client.get("/health")

    # Check status code
    assert response.status_code == 200

    # Check response structure
    data = response.json()
    assert "status" in data
    assert "timestamp" in data
    assert "service" in data
    assert "version" in data
    assert "environment" in data

    # Check specific values
    assert data["status"] == "healthy"
    assert data["service"] == "hotel-recommender"
    assert data["version"] == "0.1.0"

    # Check environment section
    env = data["environment"]
    assert "google_places_configured" in env
    assert "rakuten_app_configured" in env
    assert "rakuten_affiliate_configured" in env

    # API keys should be false since they are not set in the test environment
    assert env["google_places_configured"] is False
    assert env["rakuten_app_configured"] is False
    assert env["rakuten_affiliate_configured"] is False


def test_health_endpoint_response_format():
    """Test that the health endpoint returns valid JSON"""
    response = client.get("/health")
    assert response.headers["content-type"] == "application/json"

    # Should be able to parse as JSON
    data = response.json()
    assert isinstance(data, dict)


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
