"""
Pydantic models for Hotel Recommender API

This module defines the request/response schemas for the API endpoints,
including hotel information, station information, and recommendation requests.
"""

from datetime import UTC, date
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class WeekdayEnum(str, Enum):
    """Enumeration for weekdays"""
    MONDAY = "mon"
    TUESDAY = "tue"
    WEDNESDAY = "wed"
    THURSDAY = "thu"
    FRIDAY = "fri"
    SATURDAY = "sat"
    SUNDAY = "sun"


class StationInfo(BaseModel):
    """Station information schema"""
    name: str = Field(..., description="Station name")
    normalized_name: str = Field(..., description="Normalized station name for caching")
    latitude: float = Field(..., ge=-90, le=90, description="Latitude")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude")
    place_id: str | None = Field(None, description="Google Places place_id")
    address: str | None = Field(None, description="Formatted address")


class HotelInfo(BaseModel):
    """Hotel information schema"""
    hotel_id: str = Field(..., description="Unique hotel identifier")
    name: str = Field(..., description="Hotel name")
    latitude: float = Field(..., ge=-90, le=90, description="Hotel latitude")
    longitude: float = Field(..., ge=-180, le=180, description="Hotel longitude")
    price_total: int = Field(..., ge=0, description="Total price for one night (JPY)")
    cancellable: bool | None = Field(None, description="Whether booking is cancellable")
    highlights: list[str] = Field(default_factory=list, description="Hotel amenities/features")
    booking_url: str = Field(..., description="Rakuten Travel booking URL with affiliate ID")

    # Distance information (calculated later)
    distance_m: int | None = Field(None, ge=0, description="Distance from station in meters")
    distance_text: str | None = Field(None, description="Human-readable distance text")
    
    # Priority scoring (calculated during search)
    priority_score: float | None = Field(None, description="Priority score for ranking")


class SuggestionRequest(BaseModel):
    """Request schema for hotel suggestions"""
    stations: list[str] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="List of station names (1-10 stations)"
    )
    price_max: int = Field(
        ...,
        ge=1000,
        le=100000,
        description="Maximum price per night in JPY (1000-100000)"
    )
    date: str | None = Field(
        None,
        pattern=r'^\d{4}-\d{2}-\d{2}$',
        description="Check-in date in YYYY-MM-DD format"
    )
    weekday: WeekdayEnum | None = Field(
        None,
        description="Weekday for check-in (overridden by date if both provided)"
    )

    @field_validator('stations')
    @classmethod
    def validate_stations(cls, v: list[str]) -> list[str]:
        """Validate station names"""
        if not v:
            raise ValueError("At least one station must be provided")

        # Remove empty strings and strip whitespace
        cleaned = [station.strip() for station in v if station.strip()]

        if not cleaned:
            raise ValueError("At least one non-empty station name must be provided")

        # Check for duplicates
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("Duplicate station names are not allowed")

        return cleaned

    @field_validator('date')
    @classmethod
    def validate_date(cls, v: str | None) -> str | None:
        """Validate date format"""
        if v is None:
            return v

        try:
            # Parse date to validate format
            parsed_date = date.fromisoformat(v)

            # Check if date is not too far in the past (allow some flexibility for testing)
            from datetime import datetime
            today = datetime.now(UTC).date()

            if parsed_date < today:
                raise ValueError("Date cannot be in the past")

            return v
        except ValueError as e:
            if "Invalid isoformat string" in str(e):
                raise ValueError("Date must be in YYYY-MM-DD format") from e
            raise


class HotelResult(BaseModel):
    """Individual hotel result in the response"""
    hotel_id: str = Field(..., description="Unique hotel identifier")
    name: str = Field(..., description="Hotel name")
    distance_text: str = Field(..., description="Distance from nearest station (e.g., '新宿駅から徒歩4分')")
    distance_m: int = Field(..., ge=0, description="Distance in meters from nearest station")
    price_total: int = Field(..., ge=0, description="Total price for one night (JPY)")
    cancellable: bool | None = Field(None, description="Whether booking is cancellable")
    highlights: list[str] = Field(default_factory=list, description="Key amenities/features")
    booking_url: str = Field(..., description="Rakuten Travel booking URL with affiliate ID")
    reason: str = Field(..., description="Brief explanation why this hotel was recommended")


class SuggestionResponse(BaseModel):
    """Response schema for hotel suggestions"""
    resolved_date: str = Field(
        ...,
        pattern=r'^\d{4}-\d{2}-\d{2}$',
        description="Resolved check-in date in YYYY-MM-DD format"
    )
    results: list[HotelResult] = Field(
        ...,
        max_length=3,
        description="List of recommended hotels (max 3)"
    )


class ErrorResponse(BaseModel):
    """Error response schema"""
    error: str = Field(..., description="Error code")
    message: str = Field(..., description="Human-readable error message")
    timestamp: str = Field(..., description="Error timestamp in ISO format")
    details: dict | None = Field(None, description="Additional error details")


class NoResultsError(ErrorResponse):
    """Error response when no hotels are found"""
    error: str = Field(default="NO_CANDIDATES", description="Error code")
    suggestions: dict | None = Field(None, description="Suggestions to improve search")


class UpstreamError(ErrorResponse):
    """Error response when external APIs are unavailable"""
    error: str = Field(default="UPSTREAM_UNAVAILABLE", description="Error code")
    affected_services: list[str] = Field(default_factory=list, description="List of affected services")


# Cache key schemas for internal use
class CacheKey(BaseModel):
    """Base class for cache keys"""
    pass


class StationCacheKey(CacheKey):
    """Cache key for station lookup results"""
    normalized_name: str

    def __str__(self) -> str:
        return f"station:{self.normalized_name}"


class HotelCacheKey(CacheKey):
    """Cache key for hotel search results"""
    latitude: float
    longitude: float
    date: str  # YYYY-MM-DD format
    price_max: int
    radius_m: int

    def __str__(self) -> str:
        return f"hotel:{self.latitude}:{self.longitude}:{self.date}:{self.price_max}:{self.radius_m}"
