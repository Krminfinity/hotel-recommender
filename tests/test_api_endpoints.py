"""
Test suite for Hotel Recommender API endpoints.

Tests the FastAPI endpoints including the main /api/suggest endpoint,
error handling, request validation, and integration behavior.
"""

import pytest
from unittest.mock import patch
from datetime import date, timedelta
from fastapi.testclient import TestClient

from api.main import app
from api.schemas import SuggestionResponse, HotelResult
from api.providers.station_base import StationNotFoundError
from api.providers.hotel_base import HotelNotFoundError


@pytest.fixture
def client():
    """Create test client for FastAPI app."""
    return TestClient(app)


@pytest.fixture
def sample_hotel_result():
    """Sample hotel result for testing."""
    return HotelResult(
        hotel_id="test_hotel_001",
        name="テストホテル東京",
        distance_text="東京駅から徒歩5分",
        distance_m=400,
        price_total=8000,
        cancellable=True,
        highlights=["WiFi", "朝食付き", "駅近"],
        booking_url="https://travel.rakuten.co.jp/hotel/test_hotel_001",
        reason="駅に近く、価格も手頃でおすすめです。"
    )


@pytest.fixture
def sample_suggestion_response(sample_hotel_result):
    """Sample suggestion response for testing."""
    return SuggestionResponse(
        resolved_date=(date.today() + timedelta(days=7)).isoformat(),
        results=[sample_hotel_result]
    )


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_check(self, client):
        """Test health check endpoint returns correct format."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert data["service"] == "hotel-recommender"
        assert data["version"] == "0.1.0"
        assert "environment" in data


class TestSuggestEndpoint:
    """Test hotel suggestion endpoint."""

    def test_suggest_hotels_success(self, client, sample_suggestion_response):
        """Test successful hotel suggestion request."""
        with patch("api.main.get_recommendation_service") as mock_service_getter:
            # Mock the service instance
            mock_service = mock_service_getter.return_value
            
            # Mock the async method 
            async def mock_get_recommendations(request):
                return sample_suggestion_response
            mock_service.get_hotel_recommendations.side_effect = mock_get_recommendations
            
            response = client.post("/api/suggest", json={
                "stations": ["東京駅"],
                "price_max": 10000,
                "date": "2025-09-25",
                "weekday": None
            })
            
            assert response.status_code == 200
            data = response.json()
            
            assert "resolved_date" in data
            assert "results" in data
            assert len(data["results"]) == 1
            
            hotel = data["results"][0]
            assert hotel["hotel_id"] == "test_hotel_001"
            assert hotel["name"] == "テストホテル東京"
            assert hotel["price_total"] == 8000

    def test_suggest_hotels_validation_errors(self, client):
        """Test request validation errors."""
        # Test empty stations list
        response = client.post("/api/suggest", json={
            "stations": [],
            "price_max": 10000,
            "weekday": "fri"
        })
        assert response.status_code == 422


if __name__ == "__main__":
    pytest.main([__file__, "-v"])