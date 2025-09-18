"""
Test suite for Hotel Provider implementations.

Tests the hotel provider system including caching, error handling,
and integration with Rakuten Travel API using mocks.
"""

import pytest
import asyncio
import httpx
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date, timedelta
import json

from api.schemas import HotelInfo, StationInfo
from api.providers.hotel_rakuten import RakutenHotelProvider
from api.providers.hotel_base import (
    HotelNotFoundError,
    HotelProviderTimeoutError,
    HotelProviderRateLimitError,
    HotelProviderUnavailableError,
    HotelProviderQuotaExceededError,
)
from api.cache import cache_manager


class TestRakutenHotelProvider:
    """Test Rakuten Travel API hotel provider."""

    @pytest.fixture
    def mock_app_id(self):
        """Mock Rakuten application ID."""
        return "test_rakuten_app_id"

    @pytest.fixture
    def mock_affiliate_id(self):
        """Mock affiliate ID."""
        return "test_affiliate_id"

    @pytest.fixture
    def provider(self, mock_app_id, mock_affiliate_id):
        """Create provider instance for testing."""
        with patch.dict("os.environ", {
            "RAKUTEN_APPLICATION_ID": mock_app_id,
            "RAKUTEN_AFFILIATE_ID": mock_affiliate_id
        }):
            return RakutenHotelProvider()

    @pytest.fixture
    async def clean_cache(self):
        """Clean cache before each test."""
        await cache_manager.clear_all()
        yield
        await cache_manager.clear_all()

    @pytest.fixture
    def sample_stations(self):
        """Sample station data for testing."""
        return [
            StationInfo(
                name="Tokyo Station",
                normalized_name="tokyo",
                latitude=35.6812362,
                longitude=139.7671248,
                place_id="ChIJ_tokyo_station",
                address="1-1-1 Marunouchi, Chiyoda City, Tokyo"
            ),
            StationInfo(
                name="Shinjuku Station", 
                normalized_name="shinjuku",
                latitude=35.6896067,
                longitude=139.7005713,
                place_id="ChIJ_shinjuku_station",
                address="3-38-1 Shinjuku, Shinjuku City, Tokyo"
            )
        ]

    @pytest.fixture
    def mock_rakuten_response(self):
        """Mock successful Rakuten Travel API response."""
        return {
            "hotels": [
                {
                    "hotel": [
                        {
                            "hotelBasicInfo": {
                                "hotelNo": "12345",
                                "hotelName": "Tokyo Grand Hotel",
                                "latitude": 35.6815,
                                "longitude": 139.7670,
                                "hotelMinCharge": 8500,
                                "hotelFacilities": "WiFi, Restaurant, Parking",
                                "hotelSpecial": "Near Station"
                            },
                            "planList": [
                                {
                                    "planBasicInfo": {
                                        "planCharge": 8500,
                                        "roomBasicInfo": {
                                            "roomName": "Standard Single"
                                        }
                                    }
                                }
                            ]
                        }
                    ]
                },
                {
                    "hotel": [
                        {
                            "hotelBasicInfo": {
                                "hotelNo": "67890",
                                "hotelName": "Business Hotel Center",
                                "latitude": 35.6820,
                                "longitude": 139.7675,
                                "hotelMinCharge": 6500,
                                "hotelFacilities": "WiFi, Breakfast",
                            },
                            "planList": []
                        }
                    ]
                }
            ]
        }

    @pytest.mark.asyncio
    async def test_find_hotels_near_stations_success(
        self, 
        provider,
        clean_cache,
        sample_stations,
        mock_rakuten_response
    ):
        """Test successful hotel search near stations."""
        check_in_date = date.today() + timedelta(days=7)
        
        with patch.object(provider, '_search_hotels_near_location') as mock_search:
            # Mock return hotels for each station
            mock_hotels = [
                HotelInfo(
                    hotel_id="12345",
                    name="Tokyo Grand Hotel",
                    latitude=35.6815,
                    longitude=139.7670,
                    price_total=8500,
                    cancellable=None,
                    highlights=["WiFi", "Restaurant", "Parking"],
                    booking_url="https://travel.rakuten.co.jp/HOTEL?f_no=12345",
                    distance_m=None,
                    distance_text=None,
                    priority_score=None
                )
            ]
            
            mock_search.return_value = mock_hotels
            
            results = await provider.find_hotels_near_stations(
                stations=sample_stations,
                max_price_per_night=10000,
                check_in_date=check_in_date,
                search_radius_m=800,
                max_results=10
            )
            
            assert len(results) > 0
            hotel = results[0]
            assert isinstance(hotel, HotelInfo)
            assert hotel.name == "Tokyo Grand Hotel"
            assert hotel.distance_m is not None  # Should be calculated
            assert hotel.distance_text is not None
            assert hotel.priority_score is not None
            
            # Should have called search for each station
            assert mock_search.call_count == len(sample_stations)

    @pytest.mark.asyncio
    async def test_find_hotels_cache_hit(
        self,
        provider,
        clean_cache,
        sample_stations,
    ):
        """Test that cache is used on subsequent requests."""
        check_in_date = date.today() + timedelta(days=7)
        
        with patch.object(provider, '_search_hotels_near_location') as mock_search:
            mock_hotels = [
                HotelInfo(
                    hotel_id="12345",
                    name="Test Hotel",
                    latitude=35.6815,
                    longitude=139.7670,
                    price_total=8500,
                    cancellable=None,
                    highlights=["WiFi"],
                    booking_url="https://test.com",
                    distance_m=None,
                    distance_text=None,
                    priority_score=None
                )
            ]
            mock_search.return_value = mock_hotels
            
            # First call - should hit API
            results1 = await provider.find_hotels_near_stations(
                stations=sample_stations,
                max_price_per_night=10000,
                check_in_date=check_in_date,
                search_radius_m=800,
                max_results=10
            )
            
            initial_call_count = mock_search.call_count
            
            # Second call - should use cache
            results2 = await provider.find_hotels_near_stations(
                stations=sample_stations,
                max_price_per_night=10000,
                check_in_date=check_in_date,
                search_radius_m=800,
                max_results=10
            )
            
            # No additional API calls should be made
            assert mock_search.call_count == initial_call_count
            
            # Results should be identical
            assert len(results1) == len(results2)
            assert results1[0].hotel_id == results2[0].hotel_id

    @pytest.mark.asyncio
    async def test_find_hotels_no_results(self, provider, clean_cache, sample_stations):
        """Test handling when no hotels are found."""
        check_in_date = date.today() + timedelta(days=7)
        
        with patch.object(provider, '_search_hotels_near_location') as mock_search:
            mock_search.return_value = []  # No hotels found
            
            with pytest.raises(HotelNotFoundError) as exc_info:
                await provider.find_hotels_near_stations(
                    stations=sample_stations,
                    max_price_per_night=10000,
                    check_in_date=check_in_date,
                    search_radius_m=800,
                    max_results=10
                )
            
            assert "No hotels found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_search_hotels_near_location_success(self, provider, mock_rakuten_response):
        """Test successful location-based hotel search."""
        check_in_date = date.today() + timedelta(days=7)
        
        with patch('httpx.AsyncClient.get') as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_rakuten_response
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            hotels = await provider._search_hotels_near_location(
                latitude=35.6812362,
                longitude=139.7671248,
                radius_m=800,
                max_price=10000,
                check_in_date=check_in_date
            )
            
            assert len(hotels) == 2
            assert hotels[0].name == "Tokyo Grand Hotel"
            assert hotels[0].price_total == 8500
            assert hotels[1].name == "Business Hotel Center"
            assert hotels[1].price_total == 6500

    @pytest.mark.asyncio
    async def test_search_hotels_api_error(self, provider):
        """Test handling of API errors."""
        check_in_date = date.today() + timedelta(days=7)
        
        with patch('httpx.AsyncClient.get') as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "error": {
                    "error_description": "Invalid application ID"
                }
            }
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            hotels = await provider._search_hotels_near_location(
                latitude=35.6812362,
                longitude=139.7671248,
                radius_m=800,
                max_price=10000,
                check_in_date=check_in_date
            )
            
            # Should return empty list on API error
            assert hotels == []

    @pytest.mark.asyncio
    async def test_search_hotels_timeout(self, provider):
        """Test handling of timeout errors."""
        check_in_date = date.today() + timedelta(days=7)
        
        with patch('httpx.AsyncClient.get') as mock_get:
            mock_get.side_effect = httpx.TimeoutException("Request timeout")
            
            with pytest.raises(HotelProviderTimeoutError) as exc_info:
                await provider._search_hotels_near_location(
                    latitude=35.6812362,
                    longitude=139.7671248,
                    radius_m=800,
                    max_price=10000,
                    check_in_date=check_in_date
                )
            
            assert "timeout" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_search_hotels_rate_limit(self, provider):
        """Test handling of rate limit errors."""
        check_in_date = date.today() + timedelta(days=7)
        
        with patch('httpx.AsyncClient.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 429
            mock_get.side_effect = httpx.HTTPStatusError(
                "Rate limit exceeded",
                request=MagicMock(),
                response=mock_response
            )
            
            with pytest.raises(HotelProviderRateLimitError) as exc_info:
                await provider._search_hotels_near_location(
                    latitude=35.6812362,
                    longitude=139.7671248,
                    radius_m=800,
                    max_price=10000,
                    check_in_date=check_in_date
                )
            
            assert "rate limit" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_search_hotels_quota_exceeded(self, provider):
        """Test handling of quota exceeded errors."""
        check_in_date = date.today() + timedelta(days=7)
        
        with patch('httpx.AsyncClient.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 403
            mock_get.side_effect = httpx.HTTPStatusError(
                "Quota exceeded",
                request=MagicMock(),
                response=mock_response
            )
            
            with pytest.raises(HotelProviderQuotaExceededError) as exc_info:
                await provider._search_hotels_near_location(
                    latitude=35.6812362,
                    longitude=139.7671248,
                    radius_m=800,
                    max_price=10000,
                    check_in_date=check_in_date
                )
            
            assert "quota" in str(exc_info.value).lower()

    def test_validate_search_params_valid(self, provider, sample_stations):
        """Test validation with valid parameters."""
        check_in_date = date.today() + timedelta(days=7)
        
        # Should not raise any exceptions
        provider.validate_search_params(
            stations=sample_stations,
            max_price_per_night=8000,
            check_in_date=check_in_date,
            search_radius_m=800,
            max_results=10
        )

    def test_validate_search_params_invalid_stations(self, provider):
        """Test validation with invalid stations."""
        check_in_date = date.today() + timedelta(days=7)
        
        with pytest.raises(ValueError, match="At least one station"):
            provider.validate_search_params(
                stations=[],
                max_price_per_night=8000,
                check_in_date=check_in_date,
                search_radius_m=800,
                max_results=10
            )

    def test_validate_search_params_invalid_price(self, provider, sample_stations):
        """Test validation with invalid price."""
        check_in_date = date.today() + timedelta(days=7)
        
        with pytest.raises(ValueError, match="at least 1000 JPY"):
            provider.validate_search_params(
                stations=sample_stations,
                max_price_per_night=500,  # Too low
                check_in_date=check_in_date,
                search_radius_m=800,
                max_results=10
            )

    def test_validate_search_params_invalid_date(self, provider, sample_stations):
        """Test validation with invalid date."""
        past_date = date.today() - timedelta(days=1)
        
        with pytest.raises(ValueError, match="cannot be in the past"):
            provider.validate_search_params(
                stations=sample_stations,
                max_price_per_night=8000,
                check_in_date=past_date,
                search_radius_m=800,
                max_results=10
            )

    def test_validate_search_params_invalid_radius(self, provider, sample_stations):
        """Test validation with invalid search radius."""
        check_in_date = date.today() + timedelta(days=7)
        
        with pytest.raises(ValueError, match="exceeds maximum"):
            provider.validate_search_params(
                stations=sample_stations,
                max_price_per_night=8000,
                check_in_date=check_in_date,
                search_radius_m=5000,  # Exceeds max 3000m
                max_results=10
            )

    def test_generate_booking_url(self, provider):
        """Test booking URL generation."""
        check_in_date = date(2024, 3, 15)
        
        url = provider._generate_booking_url("12345", check_in_date)
        
        assert "travel.rakuten.co.jp" in url
        assert "f_no=12345" in url
        assert "f_ci=20240315" in url
        assert "f_afcid=test_affiliate_id" in url

    def test_parse_hotel_result(self, provider):
        """Test parsing of Rakuten API hotel result."""
        check_in_date = date.today() + timedelta(days=7)
        
        hotel_data = {
            "hotel": [{
                "hotelBasicInfo": {
                    "hotelNo": "12345",
                    "hotelName": "Test Hotel",
                    "latitude": 35.6815,
                    "longitude": 139.7670,
                    "hotelMinCharge": 8500,
                    "hotelFacilities": "WiFi, Restaurant",
                    "hotelSpecial": "Near Station"
                },
                "planList": [{
                    "planBasicInfo": {
                        "planCharge": 8500,
                        "roomBasicInfo": {
                            "roomName": "Standard Room"
                        }
                    }
                }]
            }]
        }
        
        hotel = provider._parse_hotel_result(hotel_data, check_in_date)
        
        assert isinstance(hotel, HotelInfo)
        assert hotel.hotel_id == "12345"
        assert hotel.name == "Test Hotel"
        assert hotel.price_total == 8500
        assert "WiFi" in hotel.highlights
        assert "Restaurant" in hotel.highlights
        assert "travel.rakuten.co.jp" in hotel.booking_url

    def test_deduplicate_hotels(self, provider):
        """Test hotel deduplication."""
        hotels = [
            HotelInfo(
                hotel_id="123",
                name="Hotel A",
                latitude=35.6815,
                longitude=139.7670,
                price_total=8000,
                cancellable=None,
                booking_url="https://test.com/123",
                highlights=[],
                distance_m=None,
                distance_text=None,
                priority_score=None
            ),
            HotelInfo(
                hotel_id="123",  # Same ID - should be deduplicated
                name="Hotel A Duplicate",
                latitude=35.6816,
                longitude=139.7671,
                price_total=8100,
                cancellable=None,
                booking_url="https://test.com/123",
                highlights=[],
                distance_m=None,
                distance_text=None,
                priority_score=None
            ),
            HotelInfo(
                hotel_id="456",
                name="Hotel B",
                latitude=35.6820,
                longitude=139.7675,
                price_total=7500,
                cancellable=None,
                booking_url="https://test.com/456",
                highlights=[],
                distance_m=None,
                distance_text=None,
                priority_score=None
            )
        ]
        
        unique_hotels = provider._deduplicate_hotels(hotels)
        
        assert len(unique_hotels) == 2
        assert unique_hotels[0].hotel_id == "123"
        assert unique_hotels[1].hotel_id == "456"

    def test_format_distance_text(self, provider):
        """Test distance text formatting."""
        assert provider._format_distance_text(500) == "500m"
        assert provider._format_distance_text(1500) == "1.5km"
        assert provider._format_distance_text(2000) == "2.0km"

    def test_calculate_hotel_priority_score(self, provider, sample_stations):
        """Test hotel priority score calculation."""
        hotel = HotelInfo(
            hotel_id="123",
            name="Test Hotel",
            latitude=35.6815,
            longitude=139.7670,
            price_total=8000,
            cancellable=None,
            booking_url="https://test.com",
            highlights=["WiFi", "Restaurant", "Parking"],
            distance_m=200,  # Close to station
            distance_text="200m",
            priority_score=None
        )
        
        score = provider.calculate_hotel_priority_score(hotel, sample_stations)
        
        assert 0.0 <= score <= 1.0
        assert score > 0.5  # Should be high due to close distance and reasonable price

    @pytest.mark.asyncio
    async def test_rate_limiting(self, provider):
        """Test rate limiting functionality."""
        # This test would need more sophisticated time mocking
        # For now, just test that the method exists and doesn't crash
        await provider._enforce_rate_limit()
        await provider._enforce_rate_limit()

    def test_provider_properties(self, provider):
        """Test provider property methods."""
        assert provider.get_provider_name() == "Rakuten Travel"
        assert provider.supports_location_search() is True
        assert provider.supports_price_filtering() is True
        assert provider.get_max_search_radius_m() == 3000
        assert provider.get_rate_limit_per_second() == 5.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])