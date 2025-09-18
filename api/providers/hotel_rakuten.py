"""
Rakuten Travel API implementation for hotel information provider.

This module integrates with Rakuten Travel API to find hotels near stations
with proper price filtering, affiliate link generation, and rate limiting.
"""

import asyncio
import hashlib
import httpx
import json
import logging
import math
import os
from datetime import date
from typing import List, Optional, Dict, Any
from urllib.parse import urlencode

from api.schemas import HotelInfo, StationInfo
from api.cache import get_hotel_cache, set_hotel_cache
from api.services.distance import haversine_distance, calculate_walking_time_minutes
from .hotel_base import (
    HotelProvider,
    HotelNotFoundError,
    HotelProviderTimeoutError,
    HotelProviderRateLimitError,
    HotelProviderUnavailableError,
    HotelProviderQuotaExceededError,
)


logger = logging.getLogger(__name__)


class RakutenHotelProvider(HotelProvider):
    """
    Hotel information provider using Rakuten Travel API.
    
    Uses the Rakuten Travel API to search for hotels near stations with
    proper price filtering and affiliate link generation for monetization.
    """

    BASE_URL = "https://app.rakuten.co.jp/services/api"
    
    def __init__(
        self,
        application_id: Optional[str] = None,
        affiliate_id: Optional[str] = None,
        rate_limit_per_second: float = 5.0,  # Conservative rate limit
        timeout_seconds: int = 30,
    ):
        """
        Initialize Rakuten Travel API provider.
        
        Args:
            application_id: Rakuten application ID (from env if None)
            affiliate_id: Rakuten affiliate ID for monetization (from env if None)
            rate_limit_per_second: Maximum requests per second
            timeout_seconds: Request timeout in seconds
        """
        self.application_id = application_id or os.getenv("RAKUTEN_APPLICATION_ID")
        self.affiliate_id = affiliate_id or os.getenv("RAKUTEN_AFFILIATE_ID")
        
        if not self.application_id:
            raise ValueError(
                "Rakuten application ID is required. Set RAKUTEN_APPLICATION_ID env var."
            )
        
        self.rate_limit_per_second = rate_limit_per_second
        self.timeout = httpx.Timeout(timeout_seconds)
        
        # Rate limiting
        self._request_lock = asyncio.Lock()
        self._last_request_time = 0.0
        
        logger.info(f"Initialized Rakuten provider with rate limit {rate_limit_per_second}/sec")

    def get_provider_name(self) -> str:
        """Get provider name."""
        return "Rakuten Travel"

    def supports_location_search(self) -> bool:
        """Check if location search is supported."""
        return True

    def supports_price_filtering(self) -> bool:
        """Check if price filtering is supported."""
        return True

    def get_max_search_radius_m(self) -> int:
        """Get maximum search radius."""
        return 3000  # 3km max radius

    def get_rate_limit_per_second(self) -> float:
        """Get rate limit."""
        return self.rate_limit_per_second

    def _create_cache_key(
        self,
        stations: List[StationInfo],
        max_price_per_night: int,
        check_in_date: date,
        search_radius_m: int,
    ) -> str:
        """
        Create cache key for hotel search.
        
        Args:
            stations: Station list
            max_price_per_night: Max price
            check_in_date: Check-in date
            search_radius_m: Search radius
            
        Returns:
            Cache key string
        """
        # Create deterministic key from search parameters
        station_coords = []
        for station in sorted(stations, key=lambda s: s.place_id or ""):
            station_coords.append(f"{station.latitude:.6f},{station.longitude:.6f}")
        
        key_data = (
            f"hotels:rakuten:"
            f"coords={':'.join(station_coords)}:"
            f"price={max_price_per_night}:"
            f"date={check_in_date.isoformat()}:"
            f"radius={search_radius_m}"
        )
        
        return hashlib.sha256(key_data.encode()).hexdigest()[:16]

    async def find_hotels_near_stations(
        self,
        stations: List[StationInfo],
        max_price_per_night: int,
        check_in_date: date,
        search_radius_m: int = 800,
        max_results: int = 50,
    ) -> List[HotelInfo]:
        """
        Find hotels near stations using Rakuten Travel API with caching.
        
        Args:
            stations: List of station information
            max_price_per_night: Maximum price per night in JPY
            check_in_date: Check-in date
            search_radius_m: Search radius in meters
            max_results: Maximum number of results
            
        Returns:
            List of HotelInfo objects sorted by priority
        """
        self.validate_search_params(
            stations, max_price_per_night, check_in_date, search_radius_m, max_results
        )
        
        # Create cache key
        cache_key = self._create_cache_key(
            stations, max_price_per_night, check_in_date, search_radius_m
        )
        
        # Try cache first
        cached_result = await get_hotel_cache(cache_key)
        if cached_result is not None:
            logger.debug(f"Cache hit for hotel search: {cache_key}")
            return [HotelInfo(**data) for data in cached_result]
        
        logger.debug(f"Cache miss for hotel search: {cache_key}")
        
        # Search hotels near each station and aggregate results
        all_hotels = []
        
        for station in stations:
            try:
                station_hotels = await self._search_hotels_near_location(
                    station.latitude,
                    station.longitude,
                    search_radius_m,
                    max_price_per_night,
                    check_in_date,
                    max_results_per_station=max_results // len(stations) + 10
                )
                
                # Calculate distance and add station reference
                for hotel in station_hotels:
                    hotel.distance_m = int(haversine_distance(
                        station.latitude, station.longitude,
                        hotel.latitude, hotel.longitude
                    ) * 1000)
                    hotel.distance_text = self._format_distance_text(hotel.distance_m)
                
                all_hotels.extend(station_hotels)
                
            except Exception as e:
                logger.warning(f"Failed to search hotels near {station.name}: {e}")
                continue
        
        if not all_hotels:
            raise HotelNotFoundError(
                f"No hotels found within {search_radius_m}m of stations "
                f"under ¥{max_price_per_night:,} per night"
            )
        
        # Remove duplicates and sort by priority
        unique_hotels = self._deduplicate_hotels(all_hotels)
        
        # Calculate priority scores and sort
        for hotel in unique_hotels:
            hotel_score = self.calculate_hotel_priority_score(hotel, stations)
            hotel.priority_score = hotel_score
        
        # Sort by priority score (descending)
        sorted_hotels = sorted(
            unique_hotels,
            key=lambda h: getattr(h, 'priority_score', 0.0),
            reverse=True
        )
        
        # Limit results
        result_hotels = sorted_hotels[:max_results]
        
        # Cache results
        cache_data = [hotel.model_dump() for hotel in result_hotels]
        await set_hotel_cache(cache_key, cache_data)
        
        logger.info(f"Found {len(result_hotels)} hotels near {len(stations)} stations")
        return result_hotels

    async def _search_hotels_near_location(
        self,
        latitude: float,
        longitude: float,
        radius_m: int,
        max_price: int,
        check_in_date: date,
        max_results_per_station: int = 30,
    ) -> List[HotelInfo]:
        """
        Search hotels near a specific location using Rakuten API.
        
        Args:
            latitude: Location latitude
            longitude: Location longitude
            radius_m: Search radius in meters
            max_price: Maximum price per night
            check_in_date: Check-in date
            max_results_per_station: Max results per station
            
        Returns:
            List of HotelInfo objects
        """
        await self._enforce_rate_limit()
        
        # Convert radius to kilometers for API
        radius_km = radius_m / 1000.0
        
        # Rakuten Travel API parameters
        params = {
            "applicationId": self.application_id,
            "latitude": f"{latitude:.6f}",
            "longitude": f"{longitude:.6f}",
            "searchRadius": f"{radius_km:.1f}",
            "checkinDate": check_in_date.strftime("%Y-%m-%d"),
            "checkoutDate": check_in_date.strftime("%Y-%m-%d"),  # Same day for now
            "adultNum": "1",  # Default to 1 adult
            "maxCharge": str(max_price),
            "hits": str(min(max_results_per_station, 30)),  # API limit
            "responseType": "large",  # Get detailed information
            "datumType": "1",  # WGS84
            "sort": "standard",  # Standard sorting
        }
        
        if self.affiliate_id:
            params["affiliateId"] = self.affiliate_id
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                url = f"{self.BASE_URL}/Travel/SimpleHotelSearch/20170426"
                
                logger.debug(f"Searching hotels at ({latitude}, {longitude}) radius {radius_km}km")
                
                response = await client.get(url, params=params)
                response.raise_for_status()
                
                data = response.json()
                
                if "error" in data:
                    error_msg = data.get("error", {}).get("error_description", "Unknown error")
                    logger.error(f"Rakuten API error: {error_msg}")
                    return []
                
                hotels = data.get("hotels", [])
                if not hotels:
                    logger.debug("No hotels found in API response")
                    return []
                
                return [
                    self._parse_hotel_result(hotel_data, check_in_date)
                    for hotel_data in hotels
                    if self._is_valid_hotel_result(hotel_data)
                ]
                
        except httpx.TimeoutException:
            raise HotelProviderTimeoutError(
                f"Rakuten Travel API timeout for location ({latitude}, {longitude})"
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise HotelProviderRateLimitError("Rakuten Travel API rate limit exceeded")
            elif e.response.status_code in (502, 503, 504):
                raise HotelProviderUnavailableError(
                    f"Rakuten Travel API unavailable (status {e.response.status_code})"
                )
            elif e.response.status_code == 403:
                raise HotelProviderQuotaExceededError("Rakuten Travel API quota exceeded")
            else:
                logger.error(f"Rakuten API HTTP error: {e.response.status_code}")
                return []
        except Exception as e:
            logger.error(f"Unexpected error searching hotels: {e}")
            return []

    def _parse_hotel_result(self, hotel_data: dict, check_in_date: date) -> HotelInfo:
        """
        Parse Rakuten API hotel result into HotelInfo.
        
        Args:
            hotel_data: Raw hotel data from API
            check_in_date: Check-in date for booking URL
            
        Returns:
            HotelInfo object
        """
        hotel_basic = hotel_data.get("hotel", [{}])[0].get("hotelBasicInfo", {})
        
        # Extract basic information
        hotel_id = str(hotel_basic.get("hotelNo", ""))
        name = hotel_basic.get("hotelName", "Unknown Hotel")
        latitude = float(hotel_basic.get("latitude", 0))
        longitude = float(hotel_basic.get("longitude", 0))
        
        # Extract pricing (use minimum charge if available)
        price_info = hotel_basic.get("hotelMinCharge", 0)
        if not price_info:
            # Fallback to planList if available
            plans = hotel_data.get("hotel", [{}])[0].get("planList", [])
            if plans:
                plan_charges = [
                    plan.get("planBasicInfo", {}).get("planCharge", 0) 
                    for plan in plans
                ]
                price_info = min([p for p in plan_charges if p > 0], default=0)
        
        price_total = int(price_info) if price_info else 0
        
        # Extract amenities/highlights
        highlights = []
        
        # Hotel amenities
        amenities = hotel_basic.get("hotelFacilities", "")
        if amenities:
            highlights.extend([a.strip() for a in amenities.split(",") if a.strip()])
        
        # Special features
        special = hotel_basic.get("hotelSpecial", "")
        if special:
            highlights.append(special)
        
        # Room amenities from plans
        plans = hotel_data.get("hotel", [{}])[0].get("planList", [])
        for plan in plans[:3]:  # First 3 plans only
            plan_info = plan.get("planBasicInfo", {})
            room_info = plan_info.get("roomBasicInfo", {})
            if room_info:
                room_name = room_info.get("roomName", "")
                if room_name and room_name not in highlights:
                    highlights.append(room_name)
        
        # Limit highlights
        highlights = highlights[:5]
        
        # Generate booking URL with affiliate ID
        booking_url = self._generate_booking_url(hotel_id, check_in_date)
        
        return HotelInfo(
            hotel_id=hotel_id,
            name=name,
            latitude=latitude,
            longitude=longitude,
            price_total=price_total,
            cancellable=None,  # Would need to check individual plans
            highlights=highlights,
            booking_url=booking_url,
            distance_m=None,  # Will be set later
            distance_text=None,  # Will be set later
            priority_score=None,  # Will be set later
        )

    def _generate_booking_url(self, hotel_id: str, check_in_date: date) -> str:
        """
        Generate Rakuten Travel booking URL with affiliate tracking.
        
        Args:
            hotel_id: Hotel ID
            check_in_date: Check-in date
            
        Returns:
            Booking URL string
        """
        base_url = "https://travel.rakuten.co.jp/HOTEL"
        
        # Basic parameters
        params = {
            "f_no": hotel_id,
            "f_ci": check_in_date.strftime("%Y%m%d"),
            "f_co": check_in_date.strftime("%Y%m%d"),  # Same day checkout for now
            "f_teikei": "1",  # Adult count
        }
        
        # Add affiliate ID if available
        if self.affiliate_id:
            params["f_afcid"] = self.affiliate_id
        
        return f"{base_url}?{urlencode(params)}"

    def _is_valid_hotel_result(self, hotel_data: dict) -> bool:
        """
        Check if hotel result is valid and complete.
        
        Args:
            hotel_data: Raw hotel data
            
        Returns:
            True if valid
        """
        try:
            hotel_basic = hotel_data.get("hotel", [{}])[0].get("hotelBasicInfo", {})
            
            # Must have basic required fields
            return (
                hotel_basic.get("hotelNo") and
                hotel_basic.get("hotelName") and
                hotel_basic.get("latitude") and
                hotel_basic.get("longitude")
            )
        except (KeyError, IndexError, TypeError):
            return False

    def _deduplicate_hotels(self, hotels: List[HotelInfo]) -> List[HotelInfo]:
        """
        Remove duplicate hotels based on ID and location.
        
        Args:
            hotels: List of hotels
            
        Returns:
            Deduplicated list
        """
        seen_ids = set()
        unique_hotels = []
        
        for hotel in hotels:
            # Use hotel_id as primary deduplication key
            if hotel.hotel_id not in seen_ids:
                seen_ids.add(hotel.hotel_id)
                unique_hotels.append(hotel)
        
        return unique_hotels

    def _format_distance_text(self, distance_m: int) -> str:
        """
        Format distance as human-readable text.
        
        Args:
            distance_m: Distance in meters
            
        Returns:
            Formatted distance string
        """
        if distance_m < 1000:
            return f"{distance_m}m"
        else:
            km = distance_m / 1000.0
            return f"{km:.1f}km"

    async def _enforce_rate_limit(self) -> None:
        """Enforce rate limiting."""
        async with self._request_lock:
            import time
            
            current_time = time.time()
            time_since_last = current_time - self._last_request_time
            min_interval = 1.0 / self.rate_limit_per_second
            
            if time_since_last < min_interval:
                sleep_time = min_interval - time_since_last
                await asyncio.sleep(sleep_time)
            
            self._last_request_time = time.time()

    async def get_hotel_details(self, hotel_id: str) -> Optional[HotelInfo]:
        """
        Get detailed hotel information (not implemented yet).
        
        Args:
            hotel_id: Hotel ID
            
        Returns:
            HotelInfo if found
        """
        # This would use the Rakuten Hotel Detail API
        # For MVP, we'll use the search results as details
        logger.warning(f"Hotel details not implemented for {hotel_id}")
        return None