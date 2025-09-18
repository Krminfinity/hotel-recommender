"""
Base class for station information providers

This module defines the abstract interface for station information providers.
Concrete implementations should inherit from StationProvider and implement
the get_station_info method.
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from api.schemas import StationInfo


class StationProviderError(Exception):
    """Base exception for station provider errors"""
    pass


class StationNotFoundError(StationProviderError):
    """Raised when a station cannot be found"""
    pass


class StationProviderTimeoutError(StationProviderError):
    """Raised when station provider request times out"""
    pass


class StationProviderRateLimitError(StationProviderError):
    """Raised when rate limit is exceeded"""
    pass


class StationProviderUnavailableError(StationProviderError):
    """Raised when station provider service is unavailable"""
    pass


class StationProvider(ABC):
    """
    Abstract base class for station information providers.
    
    This class defines the interface that all station providers must implement.
    It handles the abstraction of different APIs (Google Places, Overpass, etc.)
    """

    def __init__(self, timeout: int = 10):
        """
        Initialize the station provider.
        
        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout

    @abstractmethod
    async def get_station_info(
        self, 
        station_name: str, 
        normalized_name: str
    ) -> List[StationInfo]:
        """
        Get station information by name.
        
        Args:
            station_name: Original station name from user input
            normalized_name: Normalized station name for consistent lookup
            
        Returns:
            List of StationInfo objects. May contain multiple results for
            stations with the same name in different locations.
            
        Raises:
            StationNotFoundError: When no stations are found
            StationProviderTimeoutError: When request times out
            StationProviderRateLimitError: When rate limit is exceeded
            StationProviderUnavailableError: When service is unavailable
            StationProviderError: For other provider-specific errors
            
        Examples:
            >>> provider = ConcreteStationProvider()
            >>> stations = await provider.get_station_info("新宿", "新宿")
            >>> len(stations)
            1
            >>> stations[0].name
            '新宿駅'
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the station provider service is available.
        
        Returns:
            True if service is available, False otherwise
            
        Examples:
            >>> provider = ConcreteStationProvider()
            >>> await provider.health_check()
            True
        """
        pass

    def get_provider_name(self) -> str:
        """
        Get the name of this provider.
        
        Returns:
            Provider name string
        """
        return self.__class__.__name__

    async def search_multiple_stations(
        self, 
        station_requests: List[tuple[str, str]]
    ) -> dict[str, List[StationInfo]]:
        """
        Search for multiple stations concurrently.
        
        Args:
            station_requests: List of (station_name, normalized_name) tuples
            
        Returns:
            Dictionary mapping normalized_name to list of StationInfo objects.
            Failed lookups will have empty lists.
            
        Examples:
            >>> provider = ConcreteStationProvider()
            >>> requests = [("新宿", "新宿"), ("東京", "東京")]
            >>> results = await provider.search_multiple_stations(requests)
            >>> len(results)
            2
        """
        results = {}
        
        # Simple sequential implementation - can be overridden for concurrent calls
        for station_name, normalized_name in station_requests:
            try:
                station_info = await self.get_station_info(station_name, normalized_name)
                results[normalized_name] = station_info
            except StationProviderError:
                # Log error but continue with other stations
                results[normalized_name] = []
                
        return results

    def _validate_station_name(self, station_name: str) -> None:
        """
        Validate station name input.
        
        Args:
            station_name: Station name to validate
            
        Raises:
            ValueError: If station name is invalid
        """
        if not station_name or not station_name.strip():
            raise ValueError("Station name cannot be empty")
        
        if len(station_name.strip()) > 100:  # Reasonable limit
            raise ValueError("Station name too long")

    def _filter_duplicate_stations(
        self, 
        stations: List[StationInfo], 
        distance_threshold_m: float = 150
    ) -> List[StationInfo]:
        """
        Filter out duplicate or very close stations.
        
        Args:
            stations: List of stations to filter
            distance_threshold_m: Minimum distance in meters between stations
            
        Returns:
            Filtered list with duplicates removed
        """
        if len(stations) <= 1:
            return stations

        from api.services.distance import haversine_distance
        
        filtered = []
        
        for station in stations:
            is_duplicate = False
            
            for existing in filtered:
                distance = haversine_distance(
                    station.latitude, station.longitude,
                    existing.latitude, existing.longitude
                )
                
                if distance < distance_threshold_m:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                filtered.append(station)
        
        return filtered