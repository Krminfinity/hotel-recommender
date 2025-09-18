"""
Abstract base class for hotel information providers.

This module defines the interface that all hotel providers must implement,
along with common exception classes for error handling.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import date

from ..schemas import HotelInfo, StationInfo


class HotelProviderError(Exception):
    """Base exception for hotel provider errors"""
    pass


class HotelNotFoundError(HotelProviderError):
    """Raised when no hotels are found for the given criteria"""
    pass


class HotelProviderTimeoutError(HotelProviderError):
    """Raised when the hotel provider times out"""
    pass


class HotelProviderRateLimitError(HotelProviderError):
    """Raised when rate limited by the hotel provider"""
    pass


class HotelProviderUnavailableError(HotelProviderError):
    """Raised when the hotel provider service is unavailable"""
    pass


class HotelProviderQuotaExceededError(HotelProviderError):
    """Raised when API quota is exceeded"""
    pass


class HotelProvider(ABC):
    """
    Abstract base class for hotel information providers.
    
    Hotel providers are responsible for searching and retrieving hotel information
    based on location, dates, and price criteria. All implementations must handle
    geospatial searches and price filtering.
    """

    @abstractmethod
    async def find_hotels_near_stations(
        self,
        stations: List[StationInfo],
        max_price_per_night: int,
        check_in_date: date,
        search_radius_m: int = 800,
        max_results: int = 50,
    ) -> List[HotelInfo]:
        """
        Find hotels near the given stations within specified criteria.
        
        Args:
            stations: List of station information
            max_price_per_night: Maximum price per night in JPY
            check_in_date: Check-in date for availability
            search_radius_m: Search radius in meters from each station
            max_results: Maximum number of hotels to return
            
        Returns:
            List of HotelInfo objects sorted by relevance
            
        Raises:
            HotelNotFoundError: When no hotels found matching criteria
            HotelProviderTimeoutError: When request times out
            HotelProviderRateLimitError: When rate limited
            HotelProviderUnavailableError: When service unavailable
            HotelProviderQuotaExceededError: When API quota exceeded
        """
        pass

    @abstractmethod
    async def get_hotel_details(self, hotel_id: str) -> Optional[HotelInfo]:
        """
        Get detailed information for a specific hotel.
        
        Args:
            hotel_id: Unique hotel identifier
            
        Returns:
            HotelInfo object if found, None otherwise
            
        Raises:
            HotelProviderTimeoutError: When request times out
            HotelProviderUnavailableError: When service unavailable
        """
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """
        Get the name of this hotel provider.
        
        Returns:
            Provider name string
        """
        pass

    @abstractmethod
    def supports_location_search(self) -> bool:
        """
        Check if this provider supports geospatial location searches.
        
        Returns:
            True if location search is supported
        """
        pass

    @abstractmethod
    def supports_price_filtering(self) -> bool:
        """
        Check if this provider supports server-side price filtering.
        
        Returns:
            True if price filtering is supported
        """
        pass

    @abstractmethod
    def get_max_search_radius_m(self) -> int:
        """
        Get the maximum supported search radius in meters.
        
        Returns:
            Maximum search radius in meters
        """
        pass

    @abstractmethod
    def get_rate_limit_per_second(self) -> float:
        """
        Get the rate limit for API requests per second.
        
        Returns:
            Maximum requests per second
        """
        pass

    def validate_search_params(
        self,
        stations: List[StationInfo],
        max_price_per_night: int,
        check_in_date: date,
        search_radius_m: int,
        max_results: int,
    ) -> None:
        """
        Validate search parameters.
        
        Args:
            stations: List of station information
            max_price_per_night: Maximum price per night in JPY
            check_in_date: Check-in date for availability
            search_radius_m: Search radius in meters
            max_results: Maximum number of results
            
        Raises:
            ValueError: When parameters are invalid
        """
        if not stations:
            raise ValueError("At least one station must be provided")
        
        if max_price_per_night <= 0:
            raise ValueError("Maximum price must be positive")
        
        if max_price_per_night < 1000:
            raise ValueError("Maximum price must be at least 1000 JPY")
        
        if max_price_per_night > 100000:
            raise ValueError("Maximum price must not exceed 100000 JPY")
        
        if search_radius_m <= 0:
            raise ValueError("Search radius must be positive")
        
        if search_radius_m > self.get_max_search_radius_m():
            raise ValueError(
                f"Search radius {search_radius_m}m exceeds maximum "
                f"{self.get_max_search_radius_m()}m"
            )
        
        if max_results <= 0:
            raise ValueError("Maximum results must be positive")
        
        if max_results > 200:
            raise ValueError("Maximum results must not exceed 200")
        
        # Validate check-in date
        from datetime import date as date_type
        
        if not isinstance(check_in_date, date_type):
            raise ValueError("Check-in date must be a date object")
        
        today = date_type.today()
        if check_in_date < today:
            raise ValueError("Check-in date cannot be in the past")
        
        # Check if date is too far in the future (1 year max)
        from datetime import timedelta
        max_future_date = today + timedelta(days=365)
        if check_in_date > max_future_date:
            raise ValueError("Check-in date cannot be more than 1 year in the future")

    def calculate_hotel_priority_score(
        self, 
        hotel: HotelInfo, 
        stations: List[StationInfo]
    ) -> float:
        """
        Calculate a priority score for hotel ranking.
        
        This is a default implementation that can be overridden by providers.
        Factors include distance from stations and price value.
        
        Args:
            hotel: Hotel information
            stations: List of nearby stations
            
        Returns:
            Priority score (higher is better)
        """
        if not hotel.distance_m or not hotel.price_total:
            return 0.0
        
        # Distance score (closer is better, max 1.0)
        # Normalize to 0-1 where 0m = 1.0, 1000m = 0.0
        max_distance = 1000  # meters
        distance_score = max(0.0, 1.0 - (hotel.distance_m / max_distance))
        
        # Price score (cheaper is better, max 1.0)
        # Normalize to 0-1 where lower prices score higher
        min_reasonable_price = 3000  # JPY
        max_reasonable_price = 20000  # JPY
        
        if hotel.price_total <= min_reasonable_price:
            price_score = 1.0
        elif hotel.price_total >= max_reasonable_price:
            price_score = 0.1
        else:
            # Linear interpolation between min and max
            price_range = max_reasonable_price - min_reasonable_price
            price_offset = hotel.price_total - min_reasonable_price
            price_score = 1.0 - (price_offset / price_range) * 0.9
        
        # Amenities bonus
        amenities_bonus = min(0.2, len(hotel.highlights) * 0.02)
        
        # Combine scores with weights
        total_score = (
            distance_score * 0.5 +  # 50% weight on distance
            price_score * 0.4 +     # 40% weight on price
            amenities_bonus         # up to 20% bonus for amenities
        )
        
        return total_score