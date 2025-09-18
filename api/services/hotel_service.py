"""
Integrated Hotel Recommendation Service.

This service orchestrates the complete hotel recommendation workflow:
1. Station lookup and validation
2. Hotel search near stations
3. Intelligent ranking and scoring
4. Result optimization and caching
"""

import asyncio
import logging
from datetime import date
from typing import Dict, List, Optional, Tuple, Any

from api.schemas import HotelInfo, StationInfo, SuggestionRequest, SuggestionResponse, HotelResult
from api.services.resolver import normalize_station_name, resolve_date_from_input
from api.services.recommendation import (
    HotelRecommendationEngine,
    RecommendationContext,
    RankingCriteria,
    HotelScore
)
from api.providers import GooglePlacesStationProvider, RakutenHotelProvider
from api.providers.station_base import StationNotFoundError
from api.providers.hotel_base import HotelNotFoundError


logger = logging.getLogger(__name__)


class HotelRecommendationService:
    """
    High-level service for complete hotel recommendation workflow.
    
    This service coordinates multiple providers and services to deliver
    optimized hotel recommendations based on user input.
    """
    
    def __init__(
        self,
        station_provider: Optional[GooglePlacesStationProvider] = None,
        hotel_provider: Optional[RakutenHotelProvider] = None,
        recommendation_engine: Optional[HotelRecommendationEngine] = None
    ):
        """
        Initialize the recommendation service.
        
        Args:
            station_provider: Station information provider
            hotel_provider: Hotel information provider  
            recommendation_engine: Hotel ranking engine
        """
        self.station_provider = station_provider or GooglePlacesStationProvider()
        self.hotel_provider = hotel_provider or RakutenHotelProvider()
        self.recommendation_engine = recommendation_engine or HotelRecommendationEngine()
        
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.logger.info("Hotel Recommendation Service initialized")
    
    async def get_hotel_recommendations(
        self, 
        request: SuggestionRequest
    ) -> SuggestionResponse:
        """
        Get hotel recommendations based on user request.
        
        This is the main entry point that orchestrates the complete workflow:
        1. Resolve and validate input parameters
        2. Find stations matching user input
        3. Search hotels near those stations  
        4. Rank hotels using intelligent algorithm
        5. Format and return results
        
        Args:
            request: User's hotel search request
            
        Returns:
            SuggestionResponse with ranked hotel recommendations
            
        Raises:
            ValueError: Invalid request parameters
            StationNotFoundError: No stations found for input
            HotelNotFoundError: No hotels found matching criteria
        """
        self.logger.info(f"Processing hotel recommendation request for {len(request.stations)} stations")
        
        # Step 1: Resolve and validate input parameters
        resolved_date = resolve_date_from_input(request.date, request.weekday)
        
        # Step 2: Find stations (parallel processing for multiple stations)
        station_tasks = []
        for station_name in request.stations:
            normalized_name = normalize_station_name(station_name)
            task = self.station_provider.get_station_info(station_name, normalized_name)
            station_tasks.append((station_name, task))
        
        # Wait for all station lookups to complete
        all_stations = []
        station_errors = []
        
        for station_name, task in station_tasks:
            try:
                stations = await task
                all_stations.extend(stations)
                self.logger.debug(f"Found {len(stations)} stations for '{station_name}'")
            except StationNotFoundError as e:
                station_errors.append(f"駅 '{station_name}': {str(e)}")
                self.logger.warning(f"Station not found: {station_name}")
        
        if not all_stations:
            error_msg = "指定された駅が見つかりませんでした。"
            if station_errors:
                error_msg += f" エラー: {'; '.join(station_errors)}"
            raise StationNotFoundError(error_msg)
        
        # Remove duplicate stations (same place_id)
        unique_stations = self._deduplicate_stations(all_stations)
        self.logger.info(f"Using {len(unique_stations)} unique stations after deduplication")
        
        # Step 3: Search hotels near stations
        try:
            hotels = await self.hotel_provider.find_hotels_near_stations(
                stations=unique_stations,
                max_price_per_night=request.price_max,
                check_in_date=resolved_date,
                search_radius_m=800,  # Default search radius
                max_results=50       # Get plenty of candidates for ranking
            )
        except HotelNotFoundError as e:
            # Return empty results with explanation rather than raising
            self.logger.info(f"No hotels found: {e}")
            return SuggestionResponse(
                resolved_date=resolved_date.isoformat(),
                results=[]
            )
        
        # Step 4: Intelligent ranking and scoring
        ranking_criteria = self._determine_ranking_criteria(request)
        recommendation_context = RecommendationContext(
            user_budget=request.price_max,
            stations=unique_stations,
            check_in_date=resolved_date,
            preferred_criteria=ranking_criteria,
            max_walking_distance_m=1200,  # 15-minute walk maximum
            preferred_amenities=[]  # Could be extended from request
        )
        
        ranked_hotels = self.recommendation_engine.rank_hotels(hotels, recommendation_context)
        
        # Step 5: Format results using the new schema (limit to top 3)
        hotel_results = []
        for hotel, score in ranked_hotels[:3]:  # Take top 3 only
            from api.services.distance import haversine_distance
            
            # Find distance to nearest station
            min_distance_m = float('inf')
            nearest_station_name = score.nearest_station
            
            for station in unique_stations:
                distance_m = haversine_distance(
                    hotel.latitude, hotel.longitude,
                    station.latitude, station.longitude
                )
                if distance_m < min_distance_m:
                    min_distance_m = distance_m
            
            hotel_results.append(HotelResult(
                hotel_id=hotel.hotel_id,
                name=hotel.name,
                distance_text=f"{nearest_station_name}から徒歩{score.walking_time_minutes}分",
                distance_m=int(min_distance_m) if min_distance_m != float('inf') else 0,
                price_total=hotel.price_total,
                cancellable=hotel.cancellable,
                highlights=hotel.highlights,
                booking_url=hotel.booking_url,
                reason=score.recommendation_reason
            ))
        
        self.logger.info(f"Returning {len(hotel_results)} hotel recommendations")
        
        return SuggestionResponse(
            resolved_date=resolved_date.isoformat(),
            results=hotel_results
        )
    
    def _deduplicate_stations(self, stations: List[StationInfo]) -> List[StationInfo]:
        """
        Remove duplicate stations based on place_id or proximity.
        
        Args:
            stations: List of stations to deduplicate
            
        Returns:
            List of unique stations
        """
        seen_place_ids = set()
        unique_stations = []
        
        for station in stations:
            # Primary deduplication by place_id
            if station.place_id and station.place_id in seen_place_ids:
                continue
            
            # Secondary deduplication by proximity (same location within 50m)
            is_duplicate = False
            for existing in unique_stations:
                from api.services.distance import haversine_distance
                distance_m = haversine_distance(
                    station.latitude, station.longitude,
                    existing.latitude, existing.longitude
                ) * 1000
                
                if distance_m < 50:  # Within 50 meters
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                unique_stations.append(station)
                if station.place_id:
                    seen_place_ids.add(station.place_id)
        
        return unique_stations
    
    def _determine_ranking_criteria(self, request: SuggestionRequest) -> RankingCriteria:
        """
        Determine the best ranking criteria based on user request characteristics.
        
        Args:
            request: User's request
            
        Returns:
            Appropriate ranking criteria
        """
        # Analyze request to infer user priorities
        budget_ratio = request.price_max / 20000.0  # Assume 20k as high-end
        
        if budget_ratio < 0.4:  # Budget under 8k - likely budget-focused
            return RankingCriteria.BUDGET_FOCUSED
        elif budget_ratio > 0.8:  # Budget over 16k - likely comfort-focused  
            return RankingCriteria.COMFORT_FOCUSED
        elif len(request.stations) == 1:  # Single station - likely distance-focused
            return RankingCriteria.DISTANCE_FOCUSED
        else:
            return RankingCriteria.BALANCED
    
    def _enhance_hotel_with_score(self, hotel: HotelInfo, score: HotelScore) -> HotelInfo:
        """
        Enhance hotel information with scoring data.
        
        Args:
            hotel: Base hotel information
            score: Calculated hotel score
            
        Returns:
            Enhanced HotelInfo with additional fields
        """
        # Create new hotel info with enhanced data
        enhanced = HotelInfo(
            hotel_id=hotel.hotel_id,
            name=hotel.name,
            latitude=hotel.latitude,
            longitude=hotel.longitude,
            price_total=hotel.price_total,
            cancellable=hotel.cancellable,
            highlights=hotel.highlights,
            booking_url=hotel.booking_url,
            distance_m=hotel.distance_m,
            distance_text=hotel.distance_text,
            priority_score=score.total_score
        )
        
        # Add ranking explanation to highlights if not already present
        if score.recommendation_reason and score.recommendation_reason not in hotel.highlights:
            enhanced.highlights = [score.recommendation_reason] + hotel.highlights
        
        return enhanced
    
    async def get_service_health(self) -> Dict[str, Any]:
        """
        Get health status of all service components.
        
        Returns:
            Dict with health status information
        """
        health = {
            "service": "HotelRecommendationService",
            "status": "healthy",
            "components": {},
            "timestamp": date.today().isoformat()
        }
        
        # Check station provider health
        try:
            # Simple test call
            test_stations = await self.station_provider.get_station_info("テスト", "test")
            health["components"]["station_provider"] = {
                "status": "healthy",
                "provider": self.station_provider.__class__.__name__
            }
        except Exception as e:
            health["components"]["station_provider"] = {
                "status": "unhealthy", 
                "error": str(e),
                "provider": self.station_provider.__class__.__name__
            }
            health["status"] = "degraded"
        
        # Check hotel provider health  
        try:
            # Check provider configuration
            provider_name = self.hotel_provider.get_provider_name()
            health["components"]["hotel_provider"] = {
                "status": "healthy",
                "provider": provider_name,
                "supports_location": self.hotel_provider.supports_location_search(),
                "supports_price_filter": self.hotel_provider.supports_price_filtering()
            }
        except Exception as e:
            health["components"]["hotel_provider"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            health["status"] = "degraded"
        
        # Check recommendation engine
        try:
            engine_type = self.recommendation_engine.__class__.__name__
            health["components"]["recommendation_engine"] = {
                "status": "healthy",
                "engine": engine_type,
                "criteria_available": list(RankingCriteria)
            }
        except Exception as e:
            health["components"]["recommendation_engine"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            health["status"] = "degraded"
        
        return health
    
    async def get_service_stats(self) -> Dict[str, Any]:
        """
        Get service performance statistics.
        
        Returns:
            Dict with service statistics
        """
        # Import cache stats
        from api.cache import get_cache_stats
        
        stats = await get_cache_stats()
        stats.update({
            "service": "HotelRecommendationService",
            "providers": {
                "station": self.station_provider.__class__.__name__,
                "hotel": self.hotel_provider.__class__.__name__,
                "recommendation": self.recommendation_engine.__class__.__name__
            }
        })
        
        return stats