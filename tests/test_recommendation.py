"""
Test suite for Hotel Ranking and Recommendation System.

Tests the ranking algorithms, recommendation engine, and integrated service
with comprehensive scenarios and edge cases.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date, timedelta
import math

from api.schemas import HotelInfo, StationInfo, SuggestionRequest, WeekdayEnum
from api.services.recommendation import (
    HotelRecommendationEngine,
    RecommendationContext,
    RankingCriteria,
    RankingWeights,
    HotelScore
)
from api.services.hotel_service import HotelRecommendationService
from api.providers.station_base import StationNotFoundError
from api.providers.hotel_base import HotelNotFoundError


class TestRankingWeights:
    """Test ranking weights validation."""

    def test_valid_weights(self):
        """Test valid weights sum to 1.0."""
        weights = RankingWeights(0.4, 0.3, 0.2, 0.1)
        assert abs(weights.distance + weights.price_value + weights.amenities + weights.availability - 1.0) < 1e-6

    def test_invalid_weights(self):
        """Test invalid weights raise ValueError."""
        with pytest.raises(ValueError, match="must sum to 1.0"):
            RankingWeights(0.5, 0.3, 0.2, 0.2)  # Sums to 1.2


class TestHotelRecommendationEngine:
    """Test the core recommendation engine algorithms."""

    @pytest.fixture
    def engine(self):
        """Create recommendation engine instance."""
        return HotelRecommendationEngine()

    @pytest.fixture
    def sample_stations(self):
        """Sample stations for testing."""
        return [
            StationInfo(
                name="Tokyo Station",
                normalized_name="tokyo",
                latitude=35.6812362,
                longitude=139.7671248,
                place_id="tokyo_station",
                address="Tokyo Station"
            ),
            StationInfo(
                name="Shibuya Station", 
                normalized_name="shibuya",
                latitude=35.6580992,
                longitude=139.7016109,
                place_id="shibuya_station",
                address="Shibuya Station"
            )
        ]

    @pytest.fixture
    def sample_hotels(self):
        """Sample hotels with varying characteristics."""
        # Use Tokyo Station coordinates as reference: 35.6812362, 139.7671248
        return [
            # Close to station, moderate price, good amenities  
            HotelInfo(
                hotel_id="hotel_1",
                name="Grand Tokyo Hotel",
                latitude=35.6815000,  # Very close to Tokyo Station
                longitude=139.7675000,
                price_total=8000,
                cancellable=True,
                highlights=["WiFi", "Restaurant", "Parking", "Business Center"],
                booking_url="https://example.com/hotel1",
                distance_m=None,  # Will be calculated
                distance_text=None,
                priority_score=None
            ),
            # Far from station, cheap price, few amenities
            HotelInfo(
                hotel_id="hotel_2",
                name="Budget Inn",
                latitude=35.6900000,  # Farther away
                longitude=139.7800000,
                price_total=3000,
                cancellable=False,
                highlights=["WiFi"],
                booking_url="https://example.com/hotel2",
                distance_m=None,  # Will be calculated
                distance_text=None,
                priority_score=None
            ),
            # Medium distance, expensive, luxury amenities
            HotelInfo(
                hotel_id="hotel_3",
                name="Luxury Resort",
                latitude=35.6820000,  # Not too far
                longitude=139.7680000,
                price_total=15000,
                cancellable=True,
                highlights=["WiFi", "Spa", "Gym", "Restaurant", "Concierge", "Pool", "Valet"],
                booking_url="https://example.com/hotel3",
                distance_m=None,  # Will be calculated
                distance_text=None,
                priority_score=None
            ),
            # Medium distance, good value
            HotelInfo(
                hotel_id="hotel_4",
                name="Business Hotel Central",
                latitude=35.6810000,  # Close
                longitude=139.7665000,
                price_total=6000,
                cancellable=True,
                highlights=["WiFi", "Breakfast", "Business Center"],
                booking_url="https://example.com/hotel4",
                distance_m=None,  # Will be calculated
                distance_text=None,
                priority_score=None
            )
        ]

    @pytest.fixture
    def recommendation_context(self, sample_stations):
        """Standard recommendation context."""
        return RecommendationContext(
            user_budget=10000,
            stations=sample_stations,
            check_in_date=date.today() + timedelta(days=7),
            preferred_criteria=RankingCriteria.BALANCED,
            max_walking_distance_m=2000,  # More realistic 2km limit
            preferred_amenities=["WiFi", "Restaurant"]
        )

    def test_rank_hotels_basic(self, engine, sample_hotels, recommendation_context):
        """Test basic hotel ranking functionality."""
        ranked_hotels = engine.rank_hotels(sample_hotels, recommendation_context)
        
        assert len(ranked_hotels) > 0
        assert all(isinstance(hotel, HotelInfo) for hotel, _ in ranked_hotels)
        assert all(isinstance(score, HotelScore) for _, score in ranked_hotels)
        
        # Check that results are sorted by score (descending)
        scores = [score.total_score for _, score in ranked_hotels]
        assert scores == sorted(scores, reverse=True)

    def test_rank_hotels_empty_list(self, engine, recommendation_context):
        """Test ranking with empty hotel list."""
        ranked_hotels = engine.rank_hotels([], recommendation_context)
        assert ranked_hotels == []

    def test_distance_score_calculation(self, engine):
        """Test distance scoring algorithm."""
        # Very close hotel should get high score
        close_hotel = HotelInfo(
            hotel_id="close",
            name="Close Hotel",
            latitude=35.6812362,  # Same as Tokyo Station
            longitude=139.7671248,
            price_total=8000,
            cancellable=True,
            highlights=[],
            booking_url="https://example.com",
            distance_m=0,
            distance_text="0m",
            priority_score=None
        )
        
        stations = [StationInfo(
            name="Tokyo Station",
            normalized_name="tokyo",
            latitude=35.6812362,
            longitude=139.7671248,
            place_id="tokyo",
            address="Tokyo"
        )]
        
        distance_score = engine._calculate_distance_score(close_hotel, stations)
        assert distance_score > 0.9  # Should be very high
        
        # Far hotel should get low score
        far_hotel = HotelInfo(
            hotel_id="far",
            name="Far Hotel",
            latitude=35.7000000,  # Much farther
            longitude=139.8000000,
            price_total=8000,
            cancellable=True,
            highlights=[],
            booking_url="https://example.com",
            distance_m=2000,
            distance_text="2km",
            priority_score=None
        )
        
        distance_score_far = engine._calculate_distance_score(far_hotel, stations)
        assert distance_score_far < 0.3  # Should be low
        assert distance_score > distance_score_far  # Close should be better

    def test_price_score_calculation(self, engine):
        """Test price value scoring algorithm."""
        budget = 10000
        
        # Test optimal price (60-70% of budget)
        optimal_hotel = HotelInfo(
            hotel_id="optimal",
            name="Optimal Price Hotel",
            latitude=35.6812362,
            longitude=139.7671248,
            price_total=6000,  # 60% of budget
            cancellable=True,
            highlights=[],
            booking_url="https://example.com",
            distance_m=None,
            distance_text=None,
            priority_score=None
        )
        
        optimal_score = engine._calculate_price_score(optimal_hotel, budget)
        
        # Test too cheap (might indicate poor quality)
        cheap_hotel = HotelInfo(
            hotel_id="cheap",
            name="Very Cheap Hotel",
            latitude=35.6812362,
            longitude=139.7671248,
            price_total=1000,  # 10% of budget
            cancellable=True,
            highlights=[],
            booking_url="https://example.com",
            distance_m=None,
            distance_text=None,
            priority_score=None
        )
        
        cheap_score = engine._calculate_price_score(cheap_hotel, budget)
        
        # Test too expensive
        expensive_hotel = HotelInfo(
            hotel_id="expensive",
            name="Expensive Hotel",
            latitude=35.6812362,
            longitude=139.7671248,
            price_total=9500,  # 95% of budget
            cancellable=True,
            highlights=[],
            booking_url="https://example.com",
            distance_m=None,
            distance_text=None,
            priority_score=None
        )
        
        expensive_score = engine._calculate_price_score(expensive_hotel, budget)
        
        # Optimal price should score better than extremes
        assert optimal_score > cheap_score
        assert optimal_score > expensive_score
        
        # Over budget should get 0 score
        over_budget_score = engine._calculate_price_score(
            HotelInfo(
                hotel_id="over_budget",
                name="Over Budget Hotel",
                latitude=35.6812362,
                longitude=139.7671248,
                price_total=15000,  # Over budget
                cancellable=True,
                highlights=[],
                booking_url="https://example.com",
                distance_m=None,
                distance_text=None,
                priority_score=None
            ),
            budget
        )
        assert over_budget_score == 0.0

    def test_amenities_score_calculation(self, engine):
        """Test amenities scoring algorithm."""
        # Hotel with many amenities
        amenity_rich_hotel = HotelInfo(
            hotel_id="amenity_rich",
            name="Amenity Rich Hotel",
            latitude=35.6812362,
            longitude=139.7671248,
            price_total=8000,
            cancellable=True,
            highlights=["WiFi", "Restaurant", "Parking", "Spa", "Gym", "Pool"],
            booking_url="https://example.com",
            distance_m=None,
            distance_text=None,
            priority_score=None
        )
        
        # Hotel with few amenities
        basic_hotel = HotelInfo(
            hotel_id="basic",
            name="Basic Hotel",
            latitude=35.6812362,
            longitude=139.7671248,
            price_total=8000,
            cancellable=True,
            highlights=["WiFi"],
            booking_url="https://example.com",
            distance_m=None,
            distance_text=None,
            priority_score=None
        )
        
        # Hotel with no amenities
        no_amenity_hotel = HotelInfo(
            hotel_id="no_amenity",
            name="No Amenity Hotel",
            latitude=35.6812362,
            longitude=139.7671248,
            price_total=8000,
            cancellable=True,
            highlights=[],
            booking_url="https://example.com",
            distance_m=None,
            distance_text=None,
            priority_score=None
        )
        
        preferred_amenities = ["WiFi", "Restaurant", "Parking"]
        
        rich_score = engine._calculate_amenities_score(amenity_rich_hotel, preferred_amenities)
        basic_score = engine._calculate_amenities_score(basic_hotel, preferred_amenities)
        no_score = engine._calculate_amenities_score(no_amenity_hotel, preferred_amenities)
        
        # More amenities should score better
        assert rich_score > basic_score > no_score
        assert rich_score > 0.7  # Should be high
        assert no_score >= 0.2  # Base score for no amenities

    def test_availability_score_calculation(self, engine):
        """Test availability scoring."""
        # Cancellable booking
        cancellable_hotel = HotelInfo(
            hotel_id="cancellable",
            name="Cancellable Hotel",
            latitude=35.6812362,
            longitude=139.7671248,
            price_total=8000,
            cancellable=True,
            highlights=[],
            booking_url="https://example.com",
            distance_m=None,
            distance_text=None,
            priority_score=None
        )
        
        # Non-cancellable booking
        non_cancellable_hotel = HotelInfo(
            hotel_id="non_cancellable",
            name="Non-cancellable Hotel",
            latitude=35.6812362,
            longitude=139.7671248,
            price_total=8000,
            cancellable=False,
            highlights=[],
            booking_url="https://example.com",
            distance_m=None,
            distance_text=None,
            priority_score=None
        )
        
        # Unknown cancellation policy
        unknown_hotel = HotelInfo(
            hotel_id="unknown",
            name="Unknown Policy Hotel",
            latitude=35.6812362,
            longitude=139.7671248,
            price_total=8000,
            cancellable=None,
            highlights=[],
            booking_url="https://example.com",
            distance_m=None,
            distance_text=None,
            priority_score=None
        )
        
        cancellable_score = engine._calculate_availability_score(cancellable_hotel)
        non_cancellable_score = engine._calculate_availability_score(non_cancellable_hotel)
        unknown_score = engine._calculate_availability_score(unknown_hotel)
        
        # Cancellable should score highest
        assert cancellable_score > unknown_score > non_cancellable_score
        assert cancellable_score == 1.0  # Maximum score

    def test_different_ranking_criteria(self, engine, sample_hotels, sample_stations):
        """Test different ranking criteria produce different results."""
        base_context = RecommendationContext(
            user_budget=10000,
            stations=sample_stations,
            check_in_date=date.today() + timedelta(days=7),
            preferred_criteria=RankingCriteria.BALANCED,
            preferred_amenities=[]
        )
        
        # Test each ranking criteria
        criteria_results = {}
        for criteria in RankingCriteria:
            context = RecommendationContext(
                user_budget=base_context.user_budget,
                stations=base_context.stations,
                check_in_date=base_context.check_in_date,
                preferred_criteria=criteria,
                preferred_amenities=base_context.preferred_amenities
            )
            
            ranked = engine.rank_hotels(sample_hotels, context)
            criteria_results[criteria] = [hotel.hotel_id for hotel, _ in ranked]
        
        # Different criteria should potentially produce different rankings
        # At least distance_focused should differ from budget_focused  
        rankings_tuples = [tuple(ranking) for ranking in criteria_results.values()]
        assert criteria_results[RankingCriteria.DISTANCE_FOCUSED] != criteria_results[RankingCriteria.BUDGET_FOCUSED] or \
               len(set(rankings_tuples)) > 1

    def test_meets_minimum_criteria(self, engine, sample_stations):
        """Test minimum criteria filtering."""
        context = RecommendationContext(
            user_budget=5000,  # Low budget
            stations=sample_stations,
            check_in_date=date.today() + timedelta(days=7),
            preferred_criteria=RankingCriteria.BALANCED,
            max_walking_distance_m=800,  # Short walking distance
            preferred_amenities=[]
        )
        
        # Hotel over budget
        over_budget_hotel = HotelInfo(
            hotel_id="over_budget",
            name="Over Budget Hotel",
            latitude=35.6812362,
            longitude=139.7671248,
            price_total=6000,  # Over budget
            cancellable=True,
            highlights=[],
            booking_url="https://example.com",
            distance_m=None,
            distance_text=None,
            priority_score=None
        )
        
        # Hotel too far
        too_far_hotel = HotelInfo(
            hotel_id="too_far",
            name="Too Far Hotel",
            latitude=35.7000000,  # Very far
            longitude=139.8000000,
            price_total=4000,
            cancellable=True,
            highlights=[],
            booking_url="https://example.com",
            distance_m=None,
            distance_text=None,
            priority_score=None
        )
        
        # Acceptable hotel
        acceptable_hotel = HotelInfo(
            hotel_id="acceptable",
            name="Acceptable Hotel",
            latitude=35.6815000,  # Close
            longitude=139.7670000,
            price_total=4000,
            cancellable=True,
            highlights=[],
            booking_url="https://example.com",
            distance_m=None,
            distance_text=None,
            priority_score=None
        )
        
        assert not engine._meets_minimum_criteria(over_budget_hotel, context)
        assert not engine._meets_minimum_criteria(too_far_hotel, context)
        assert engine._meets_minimum_criteria(acceptable_hotel, context)

    def test_recommendation_reason_generation(self, engine):
        """Test recommendation reason generation."""
        hotel = HotelInfo(
            hotel_id="test",
            name="Test Hotel",
            latitude=35.6812362,
            longitude=139.7671248,
            price_total=8000,
            cancellable=True,
            highlights=["WiFi", "Restaurant"],
            booking_url="https://example.com",
            distance_m=None,
            distance_text=None,
            priority_score=None
        )
        
        # High distance score
        reason = engine._generate_recommendation_reason(
            hotel, 0.9, 0.5, 0.5, RankingCriteria.DISTANCE_FOCUSED
        )
        assert "近い" in reason or "立地" in reason
        
        # High price score
        reason = engine._generate_recommendation_reason(
            hotel, 0.5, 0.9, 0.5, RankingCriteria.BUDGET_FOCUSED
        )
        assert "コスト" in reason or "価格" in reason or "お手頃" in reason
        
        # High amenities score
        reason = engine._generate_recommendation_reason(
            hotel, 0.5, 0.5, 0.9, RankingCriteria.COMFORT_FOCUSED
        )
        assert "設備" in reason or "サービス" in reason or "アメニティ" in reason


class TestHotelRecommendationService:
    """Test the integrated hotel recommendation service."""

    @pytest.fixture
    def mock_station_provider(self):
        """Mock station provider."""
        mock = AsyncMock()
        mock.get_station_info.return_value = [
            StationInfo(
                name="Tokyo Station",
                normalized_name="tokyo",
                latitude=35.6812362,
                longitude=139.7671248,
                place_id="tokyo_station",
                address="Tokyo"
            )
        ]
        return mock

    @pytest.fixture
    def mock_hotel_provider(self):
        """Mock hotel provider."""
        mock = AsyncMock()
        mock.find_hotels_near_stations.return_value = [
            HotelInfo(
                hotel_id="test_hotel",
                name="Test Hotel",
                latitude=35.6815000,
                longitude=139.7670000,
                price_total=8000,
                cancellable=True,
                highlights=["WiFi", "Restaurant"],
                booking_url="https://example.com/test_hotel",
                distance_m=150,
                distance_text="150m",
                priority_score=None
            )
        ]
        return mock

    @pytest.fixture
    def service(self, mock_station_provider, mock_hotel_provider):
        """Create service instance with mocked providers."""
        return HotelRecommendationService(
            station_provider=mock_station_provider,
            hotel_provider=mock_hotel_provider
        )

    @pytest.fixture
    def sample_request(self):
        """Sample suggestion request."""
        return SuggestionRequest(
            stations=["東京駅"],
            price_max=10000,
            date=(date.today() + timedelta(days=7)).strftime("%Y-%m-%d"),
            weekday=None
        )

    @pytest.mark.asyncio
    async def test_get_hotel_recommendations_success(self, service, sample_request):
        """Test successful hotel recommendation flow."""
        response = await service.get_hotel_recommendations(sample_request)
        
        assert response.resolved_date is not None
        assert len(response.results) > 0
        
        # Check hotel structure
        hotel = response.results[0]
        assert hotel.hotel_id is not None
        assert hotel.name is not None
        assert hotel.price_total <= sample_request.price_max

    @pytest.mark.asyncio
    async def test_get_hotel_recommendations_station_not_found(self, service):
        """Test handling when stations are not found."""
        # Make station provider return no results
        service.station_provider.get_station_info.side_effect = StationNotFoundError("Station not found")
        
        request = SuggestionRequest(
            stations=["NonexistentStation"],
            price_max=10000,
            date=(date.today() + timedelta(days=7)).strftime("%Y-%m-%d"),
            weekday=None
        )
        
        with pytest.raises(StationNotFoundError):
            await service.get_hotel_recommendations(request)

    @pytest.mark.asyncio
    async def test_get_hotel_recommendations_no_hotels(self, service, sample_request):
        """Test handling when no hotels are found."""
        # Make hotel provider return no results
        service.hotel_provider.find_hotels_near_stations.side_effect = HotelNotFoundError("No hotels found")
        
        response = await service.get_hotel_recommendations(sample_request)
        
        assert len(response.results) == 0
        assert response.resolved_date is not None

    @pytest.mark.asyncio
    async def test_service_health_check(self, service):
        """Test service health check."""
        health = await service.get_service_health()
        
        assert health["service"] == "HotelRecommendationService"
        assert health["status"] in ["healthy", "degraded"]
        assert "components" in health
        assert "station_provider" in health["components"]
        assert "hotel_provider" in health["components"]
        assert "recommendation_engine" in health["components"]

    @pytest.mark.asyncio
    async def test_service_stats(self, service):
        """Test service statistics."""
        stats = await service.get_service_stats()
        
        assert "service" in stats
        assert "providers" in stats
        assert "caches" in stats


if __name__ == "__main__":
    pytest.main([__file__, "-v"])