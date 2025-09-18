"""
Google Places API station information provider

This module implements station information retrieval using Google Places API.
It uses the Text Search API with type=train_station for accurate station data.
"""

import asyncio
import hashlib
import json
import os
from typing import List, Optional
import httpx
import logging

from api.schemas import StationInfo
from api.cache import get_station_cache, set_station_cache
from api.providers.station_base import (
    StationProvider,
    StationNotFoundError,
    StationProviderTimeoutError,
    StationProviderRateLimitError,
    StationProviderUnavailableError,
    StationProviderError,
)


logger = logging.getLogger(__name__)


class GooglePlacesStationProvider(StationProvider):
    """
    Station information provider using Google Places API.
    
    Uses the Places API Text Search with type=train_station to find
    Japanese train stations. Configured for Japan region with Japanese language.
    """

    BASE_URL = "https://maps.googleapis.com/maps/api/place"

    def __init__(self, api_key: Optional[str] = None, timeout: int = 10):
        """
        Initialize Google Places station provider.
        
        Args:
            api_key: Google Places API key (defaults to GOOGLE_PLACES_API_KEY env var)
            timeout: Request timeout in seconds
        """
        super().__init__(timeout=timeout)
        
        self.api_key = api_key or os.getenv("GOOGLE_PLACES_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Google Places API key required. Set GOOGLE_PLACES_API_KEY "
                "environment variable or pass api_key parameter."
            )

        # Rate limiting configuration
        self.rate_limit_per_second = int(
            os.getenv("GOOGLE_PLACES_RATE_LIMIT_PER_SECOND", "10")
        )
        self._last_request_time = 0
        self._request_lock = asyncio.Lock()

    def _create_cache_key(self, normalized_name: str) -> str:
        """
        Create a cache key for the station name.
        
        Args:
            normalized_name: Normalized station name
            
        Returns:
            Cache key string
        """
        # Use hash to create a consistent, shorter key
        key_data = f"station:{normalized_name}:google"
        return hashlib.sha256(key_data.encode()).hexdigest()[:16]

    async def get_station_info(
        self, 
        station_name: str, 
        normalized_name: str
    ) -> List[StationInfo]:
        """
        Get station information from Google Places API with caching.
        
        Args:
            station_name: Original station name
            normalized_name: Normalized station name for caching
            
        Returns:
            List of StationInfo objects
            
        Raises:
            StationNotFoundError: When no stations found
            StationProviderTimeoutError: When request times out
            StationProviderRateLimitError: When rate limited
            StationProviderUnavailableError: When service unavailable
        """
        self._validate_station_name(station_name)
        
        # Create cache key
        cache_key = self._create_cache_key(normalized_name)
        
        # Try to get from cache first
        cached_result = await get_station_cache(cache_key)
        if cached_result is not None:
            logger.debug(f"Cache hit for station: {normalized_name}")
            return [StationInfo(**data) for data in cached_result]
        
        logger.debug(f"Cache miss for station: {normalized_name}")
        
        # Rate limiting
        await self._enforce_rate_limit()
        
        try:
            # First try Text Search API
            results = await self._text_search(station_name)
            
            if not results:
                # Fallback with different search term
                alt_search_term = f"{station_name} 駅" if not station_name.endswith("駅") else station_name
                results = await self._text_search(alt_search_term)
            
            if not results:
                raise StationNotFoundError(f"No stations found for '{station_name}'")
            
            stations = []
            for result in results:
                try:
                    station = self._parse_place_result(result, normalized_name)
                    stations.append(station)
                except Exception as e:
                    logger.warning(f"Failed to parse place result: {e}")
                    continue
            
            if not stations:
                raise StationNotFoundError(f"No valid stations found for '{station_name}'")
            
            # Filter out duplicates/nearby stations
            filtered_stations = self._filter_duplicate_stations(stations)
            
            # Cache the results (serialize to dict for JSON compatibility)
            cache_data = [station.model_dump() for station in filtered_stations]
            await set_station_cache(cache_key, cache_data)
            
            logger.info(f"Found {len(filtered_stations)} stations for '{station_name}'")
            return filtered_stations

        except httpx.TimeoutException:
            raise StationProviderTimeoutError(
                f"Google Places API timeout for station '{station_name}'"
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise StationProviderRateLimitError(
                    "Google Places API rate limit exceeded"
                )
            elif e.response.status_code in (502, 503, 504):
                raise StationProviderUnavailableError(
                    f"Google Places API unavailable (status {e.response.status_code})"
                )
            else:
                raise StationProviderError(
                    f"Google Places API error: {e.response.status_code}"
                )

    async def health_check(self) -> bool:
        """
        Check if Google Places API is available.
        
        Returns:
            True if API is accessible, False otherwise
        """
        try:
            # Simple test query for a well-known station
            await self.get_station_info("東京駅", "東京")
            return True
        except Exception:
            return False

    async def _text_search(self, query: str) -> List[dict]:
        """
        Perform Google Places Text Search.
        
        Args:
            query: Search query
            
        Returns:
            List of place results from API
        """
        url = f"{self.BASE_URL}/textsearch/json"
        
        params = {
            "query": query,
            "type": "train_station",
            "language": "ja",
            "region": "jp",
            "key": self.api_key,
        }
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get("status") == "ZERO_RESULTS":
                return []
            elif data.get("status") == "OVER_QUERY_LIMIT":
                raise StationProviderRateLimitError("Google Places API quota exceeded")
            elif data.get("status") not in ("OK", "ZERO_RESULTS"):
                raise StationProviderError(
                    f"Google Places API error: {data.get('status', 'UNKNOWN')}"
                )
            
            return data.get("results", [])

    def _parse_place_result(self, result: dict, normalized_name: str) -> StationInfo:
        """
        Parse a Google Places API result into StationInfo.
        
        Args:
            result: Place result from API
            normalized_name: Normalized station name for caching
            
        Returns:
            StationInfo object
        """
        # Extract location
        location = result.get("geometry", {}).get("location", {})
        if not location:
            raise ValueError("No location data in place result")
        
        latitude = location.get("lat")
        longitude = location.get("lng")
        
        if latitude is None or longitude is None:
            raise ValueError("Invalid coordinates in place result")
        
        # Extract name
        name = result.get("name", "")
        if not name:
            raise ValueError("No name in place result")
        
        # Extract place_id
        place_id = result.get("place_id")
        
        # Extract address
        address = result.get("formatted_address")
        
        return StationInfo(
            name=name,
            normalized_name=normalized_name,
            latitude=float(latitude),
            longitude=float(longitude),
            place_id=place_id,
            address=address,
        )

    async def _enforce_rate_limit(self) -> None:
        """
        Enforce rate limiting to avoid API quota issues.
        """
        async with self._request_lock:
            import time
            
            current_time = time.time()
            time_since_last = current_time - self._last_request_time
            min_interval = 1.0 / self.rate_limit_per_second
            
            if time_since_last < min_interval:
                sleep_time = min_interval - time_since_last
                await asyncio.sleep(sleep_time)
            
            self._last_request_time = time.time()

    async def get_place_details(self, place_id: str) -> Optional[dict]:
        """
        Get detailed information about a place using Place Details API.
        
        This is useful for getting additional information like phone numbers,
        opening hours, etc., though not typically needed for basic hotel search.
        
        Args:
            place_id: Google Places place_id
            
        Returns:
            Place details dictionary, or None if not found
        """
        if not place_id:
            return None
            
        await self._enforce_rate_limit()
        
        url = f"{self.BASE_URL}/details/json"
        
        params = {
            "place_id": place_id,
            "language": "ja",
            "key": self.api_key,
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                
                data = response.json()
                
                if data.get("status") == "OK":
                    return data.get("result", {})
                else:
                    logger.warning(f"Place details failed for {place_id}: {data.get('status')}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error fetching place details for {place_id}: {e}")
            return None