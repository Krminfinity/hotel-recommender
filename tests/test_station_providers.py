"""
Test suite for Station Provider implementations.

Tests the station provider system including caching, error handling,
and integration with Google Places API using mocks.
"""

import pytest
import asyncio
import httpx
from unittest.mock import AsyncMock, MagicMock, patch
import json

from api.schemas import StationInfo
from api.providers.station_google import GooglePlacesStationProvider
from api.providers.station_base import (
    StationNotFoundError,
    StationProviderTimeoutError,
    StationProviderRateLimitError,
    StationProviderUnavailableError,
)
from api.cache import cache_manager


class TestGooglePlacesStationProvider:
    """Test Google Places API station provider."""

    @pytest.fixture
    def mock_api_key(self):
        """Mock API key for testing."""
        return "test_api_key"

    @pytest.fixture
    def provider(self, mock_api_key):
        """Create provider instance for testing."""
        with patch.dict("os.environ", {"GOOGLE_PLACES_API_KEY": mock_api_key}):
            return GooglePlacesStationProvider()

    @pytest.fixture
    async def clean_cache(self):
        """Clean cache before each test."""
        await cache_manager.clear_all()
        yield
        await cache_manager.clear_all()

    @pytest.fixture
    def mock_places_response(self):
        """Mock successful Google Places API response."""
        return {
            "candidates": [
                {
                    "place_id": "ChIJ_test_place_id_1",
                    "name": "Tokyo Station",
                    "formatted_address": "1-1-1 Marunouchi, Chiyoda City, Tokyo 100-0005, Japan",
                    "geometry": {
                        "location": {
                            "lat": 35.6812362,
                            "lng": 139.7671248
                        }
                    },
                    "types": ["train_station", "transit_station", "point_of_interest", "establishment"]
                }
            ],
            "status": "OK"
        }

    @pytest.fixture
    def mock_place_details_response(self):
        """Mock Google Places Place Details API response."""
        return {
            "result": {
                "place_id": "ChIJ_test_place_id_1",
                "name": "Tokyo Station",
                "formatted_address": "1-1-1 Marunouchi, Chiyoda City, Tokyo 100-0005, Japan",
                "geometry": {
                    "location": {
                        "lat": 35.6812362,
                        "lng": 139.7671248
                    }
                },
                "types": ["train_station", "transit_station", "point_of_interest", "establishment"],
                "rating": 4.1,
                "user_ratings_total": 15234
            },
            "status": "OK"
        }

    @pytest.mark.asyncio
    async def test_get_station_info_success(
        self, 
        provider, 
        clean_cache,
        mock_places_response,
        mock_place_details_response
    ):
        """Test successful station information retrieval."""
        with patch.object(provider, '_text_search') as mock_text_search, \
             patch.object(provider, 'get_place_details') as mock_place_details:
            
            mock_text_search.return_value = mock_places_response["candidates"]
            mock_place_details.return_value = mock_place_details_response["result"]
            
            stations = await provider.get_station_info("東京駅", "tokyo")
            
            assert len(stations) == 1
            station = stations[0]
            assert isinstance(station, StationInfo)
            assert station.name == "Tokyo Station"
            assert station.normalized_name == "tokyo"
            assert station.latitude == 35.6812362
            assert station.longitude == 139.7671248
            assert station.place_id == "ChIJ_test_place_id_1"

    @pytest.mark.asyncio
    async def test_get_station_info_cache_hit(
        self, 
        provider, 
        clean_cache,
        mock_places_response,
        mock_place_details_response
    ):
        """Test that cache is used on subsequent requests."""
        with patch.object(provider, '_text_search') as mock_text_search, \
             patch.object(provider, 'get_place_details') as mock_place_details:
            
            mock_text_search.return_value = mock_places_response["candidates"]
            mock_place_details.return_value = mock_place_details_response["result"]
            
            # First call - should hit API
            stations1 = await provider.get_station_info("東京駅", "tokyo")
            assert mock_text_search.call_count == 1
            
            # Second call - should use cache
            stations2 = await provider.get_station_info("東京駅", "tokyo")
            assert mock_text_search.call_count == 1  # No additional calls
            
            # Results should be identical
            assert len(stations1) == len(stations2) == 1
            assert stations1[0].place_id == stations2[0].place_id

    @pytest.mark.asyncio
    async def test_get_station_info_fallback_search(
        self, 
        provider, 
        clean_cache,
        mock_places_response,
        mock_place_details_response
    ):
        """Test fallback search when initial search returns no results."""
        with patch.object(provider, '_text_search') as mock_text_search, \
             patch.object(provider, 'get_place_details') as mock_place_details:
            
            # First call returns empty, second call returns results
            mock_text_search.side_effect = [[], mock_places_response["candidates"]]
            mock_place_details.return_value = mock_place_details_response["result"]
            
            stations = await provider.get_station_info("東京", "tokyo")
            
            # Should have called text search twice (original + fallback)
            assert mock_text_search.call_count == 2
            # First call with "東京", second with "東京 駅"
            assert mock_text_search.call_args_list[0][0][0] == "東京"
            assert mock_text_search.call_args_list[1][0][0] == "東京 駅"
            
            assert len(stations) == 1

    @pytest.mark.asyncio
    async def test_get_station_info_not_found(self, provider, clean_cache):
        """Test handling when no stations are found."""
        with patch.object(provider, '_text_search') as mock_text_search:
            mock_text_search.return_value = []
            
            with pytest.raises(StationNotFoundError) as exc_info:
                await provider.get_station_info("NonexistentStation", "nonexistent")
            
            assert "No stations found" in str(exc_info.value)
            # Should have tried fallback search
            assert mock_text_search.call_count == 2

    @pytest.mark.asyncio
    async def test_get_station_info_timeout(self, provider, clean_cache):
        """Test handling of API timeout."""
        with patch.object(provider, '_text_search') as mock_text_search:
            mock_text_search.side_effect = httpx.TimeoutException("Request timeout")
            
            with pytest.raises(StationProviderTimeoutError) as exc_info:
                await provider.get_station_info("東京駅", "tokyo")
            
            assert "timeout" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_get_station_info_rate_limit(self, provider, clean_cache):
        """Test handling of rate limit errors."""
        with patch.object(provider, '_text_search') as mock_text_search:
            mock_response = MagicMock()
            mock_response.status_code = 429
            mock_text_search.side_effect = httpx.HTTPStatusError(
                "Rate limit exceeded", 
                request=MagicMock(), 
                response=mock_response
            )
            
            with pytest.raises(StationProviderRateLimitError) as exc_info:
                await provider.get_station_info("東京駅", "tokyo")
            
            assert "rate limit" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_get_station_info_service_unavailable(self, provider, clean_cache):
        """Test handling of service unavailable errors."""
        with patch.object(provider, '_text_search') as mock_text_search:
            mock_response = MagicMock()
            mock_response.status_code = 503
            mock_text_search.side_effect = httpx.HTTPStatusError(
                "Service unavailable", 
                request=MagicMock(), 
                response=mock_response
            )
            
            with pytest.raises(StationProviderUnavailableError) as exc_info:
                await provider.get_station_info("東京駅", "tokyo")
            
            assert "unavailable" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_filter_duplicate_stations(self, provider):
        """Test filtering of duplicate nearby stations."""
        stations = [
            StationInfo(
                name="Tokyo Station",
                normalized_name="tokyo",
                latitude=35.6812362,
                longitude=139.7671248,
                place_id="place_1",
                address="Address 1"
            ),
            StationInfo(
                name="Tokyo Station East",
                normalized_name="tokyo",
                latitude=35.6812400,  # Very close
                longitude=139.7671300,
                place_id="place_2",
                address="Address 2"
            ),
            StationInfo(
                name="Shinjuku Station",
                normalized_name="tokyo",
                latitude=35.6896067,  # Far away
                longitude=139.7005713,
                place_id="place_3",
                address="Address 3"
            ),
        ]
        
        filtered = provider._filter_duplicate_stations(stations)
        
        # Should keep the first Tokyo Station and Shinjuku Station
        assert len(filtered) == 2
        assert filtered[0].name == "Tokyo Station"
        assert filtered[1].name == "Shinjuku Station"

    @pytest.mark.asyncio
    async def test_validate_station_name(self, provider):
        """Test station name validation."""
        # Valid names should not raise
        provider._validate_station_name("東京駅")
        provider._validate_station_name("Tokyo Station")
        
        # Invalid names should raise
        with pytest.raises(ValueError):
            provider._validate_station_name("")
        
        with pytest.raises(ValueError):
            provider._validate_station_name("   ")
        
        with pytest.raises(ValueError):
            provider._validate_station_name("a" * 101)  # Too long

    def test_create_cache_key(self, provider):
        """Test cache key creation."""
        key1 = provider._create_cache_key("tokyo")
        key2 = provider._create_cache_key("tokyo")
        key3 = provider._create_cache_key("osaka")
        
        # Same input should produce same key
        assert key1 == key2
        
        # Different input should produce different key
        assert key1 != key3
        
        # Keys should be reasonable length
        assert len(key1) == 16
        assert isinstance(key1, str)

    @pytest.mark.asyncio
    async def test_rate_limiting(self, provider):
        """Test rate limiting functionality."""
        # This test would need more sophisticated mocking of time
        # For now, just test that the method exists and doesn't crash
        await provider._enforce_rate_limit()
        await provider._enforce_rate_limit()

    @pytest.mark.asyncio
    async def test_parse_place_result(self, provider, mock_place_details_response):
        """Test parsing of place result into StationInfo."""
        place_result = {
            "place_id": "ChIJ_test_place_id_1",
            "name": "Tokyo Station",
            "formatted_address": "1-1-1 Marunouchi, Chiyoda City, Tokyo 100-0005, Japan",
            "geometry": {
                "location": {
                    "lat": 35.6812362,
                    "lng": 139.7671248
                }
            },
            "types": ["train_station", "transit_station", "point_of_interest", "establishment"]
        }
        
        with patch.object(provider, 'get_place_details') as mock_place_details:
            mock_place_details.return_value = mock_place_details_response["result"]
            
            station = provider._parse_place_result(place_result, "tokyo")
            
            assert isinstance(station, StationInfo)
            assert station.name == "Tokyo Station"
            assert station.normalized_name == "tokyo"
            assert station.latitude == 35.6812362
            assert station.longitude == 139.7671248
            assert station.place_id == "ChIJ_test_place_id_1"
            assert station.address == "1-1-1 Marunouchi, Chiyoda City, Tokyo 100-0005, Japan"


class TestCacheIntegration:
    """Test cache integration with providers."""

    @pytest.fixture
    async def clean_cache(self):
        """Clean cache before each test."""
        await cache_manager.clear_all()
        yield
        await cache_manager.clear_all()

    @pytest.mark.asyncio
    async def test_cache_stats(self, clean_cache):
        """Test cache statistics functionality."""
        stats = cache_manager.station_cache.get_stats()
        
        assert "size" in stats
        assert "hits" in stats
        assert "misses" in stats
        assert "hit_rate" in stats
        assert stats["size"] == 0
        
    @pytest.mark.asyncio
    async def test_cache_health_check(self, clean_cache):
        """Test cache health check."""
        health = await cache_manager.health_check()
        
        assert "stations" in health
        assert "hotels" in health
        assert "general" in health
        assert all(health.values())  # All should be healthy

    @pytest.mark.asyncio
    async def test_cache_ttl_expiration(self, clean_cache):
        """Test that cache entries expire after TTL."""
        # Set a short TTL for testing
        test_cache = cache_manager.station_cache
        
        # Set value with 1 second TTL
        await test_cache.set("test_key", ["test_value"], 1)
        
        # Should be available immediately
        result = await test_cache.get("test_key")
        assert result == ["test_value"]
        
        # Wait for expiration
        await asyncio.sleep(1.1)
        
        # Should be expired now
        result = await test_cache.get("test_key")
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])