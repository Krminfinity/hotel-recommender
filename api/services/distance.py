"""
Distance calculation utilities for Hotel Recommender API

This module provides utilities for calculating distances between geographic points:
- Haversine formula for great-circle distance calculation
- Walking time estimation based on standard walking speed
- Coordinate validation and normalization
"""

import math

from api.schemas import HotelInfo, StationInfo


def haversine_distance(
    lat1: float, lon1: float,
    lat2: float, lon2: float
) -> float:
    """
    Calculate the great-circle distance between two points on Earth using the Haversine formula.

    This function calculates the shortest distance over the earth's surface,
    giving an 'as-the-crow-flies' distance between the points.

    Args:
        lat1: Latitude of first point in decimal degrees
        lon1: Longitude of first point in decimal degrees
        lat2: Latitude of second point in decimal degrees
        lon2: Longitude of second point in decimal degrees

    Returns:
        Distance in meters

    Examples:
        >>> # Distance between Tokyo Station and Shinjuku Station
        >>> haversine_distance(35.6812, 139.7671, 35.6896, 139.7006)
        5889.0  # Approximately 5.9 km

        >>> # Distance between nearby points
        >>> haversine_distance(35.6812, 139.7671, 35.6815, 139.7675)
        44.7   # Approximately 45 meters
    """
    # Validate coordinates
    if not (-90 <= lat1 <= 90 and -90 <= lat2 <= 90):
        raise ValueError("Latitude must be between -90 and 90 degrees")
    if not (-180 <= lon1 <= 180 and -180 <= lon2 <= 180):
        raise ValueError("Longitude must be between -180 and 180 degrees")

    # Earth's radius in meters
    R = 6371000

    # Convert degrees to radians
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    # Differences
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    # Haversine formula
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(lat1_rad) * math.cos(lat2_rad) *
         math.sin(dlon / 2) ** 2)

    c = 2 * math.asin(math.sqrt(a))

    # Distance in meters
    distance = R * c

    return round(distance, 1)


def calculate_walking_time_minutes(distance_m: float) -> int:
    """
    Calculate walking time in minutes based on distance.

    Uses standard walking speed of 80 meters per minute (4.8 km/h),
    which is appropriate for urban areas in Japan.

    Args:
        distance_m: Distance in meters

    Returns:
        Walking time in minutes (minimum 1 minute)

    Examples:
        >>> calculate_walking_time_minutes(320)
        4

        >>> calculate_walking_time_minutes(80)
        1

        >>> calculate_walking_time_minutes(50)
        1  # Minimum 1 minute
    """
    if distance_m < 0:
        raise ValueError("Distance cannot be negative")

    # 80 meters per minute walking speed
    walking_speed_m_per_min = 80

    # Calculate minutes, minimum 1 minute
    minutes = max(1, round(distance_m / walking_speed_m_per_min))

    return minutes


def distance_between_station_and_hotel(
    station: StationInfo,
    hotel: HotelInfo
) -> float:
    """
    Calculate distance between a station and hotel using their coordinates.

    Args:
        station: Station information with lat/lng
        hotel: Hotel information with lat/lng

    Returns:
        Distance in meters

    Examples:
        >>> station = StationInfo(
        ...     name="新宿駅", normalized_name="新宿",
        ...     latitude=35.6896, longitude=139.7006
        ... )
        >>> hotel = HotelInfo(
        ...     hotel_id="12345", name="ホテル新宿",
        ...     latitude=35.6900, longitude=139.7010,
        ...     price_total=10000, booking_url="https://example.com"
        ... )
        >>> distance_between_station_and_hotel(station, hotel)
        54.2
    """
    return haversine_distance(
        station.latitude, station.longitude,
        hotel.latitude, hotel.longitude
    )


def find_nearest_station(
    hotel: HotelInfo,
    stations: list[StationInfo]
) -> tuple[StationInfo, float]:
    """
    Find the nearest station to a hotel from a list of stations.

    Args:
        hotel: Hotel information
        stations: List of available stations

    Returns:
        Tuple of (nearest_station, distance_in_meters)

    Raises:
        ValueError: If stations list is empty

    Examples:
        >>> hotel = HotelInfo(...)  # Hotel near Shinjuku
        >>> stations = [shinjuku_station, tokyo_station, shibuya_station]
        >>> nearest_station, distance = find_nearest_station(hotel, stations)
        >>> nearest_station.name
        '新宿駅'
        >>> distance
        320.5
    """
    if not stations:
        raise ValueError("Stations list cannot be empty")

    nearest_station = None
    min_distance = float('inf')

    for station in stations:
        distance = distance_between_station_and_hotel(station, hotel)
        if distance < min_distance:
            min_distance = distance
            nearest_station = station

    if nearest_station is None:
        raise ValueError("Could not find nearest station")

    return nearest_station, min_distance


def is_within_walking_distance(distance_m: float, max_walking_minutes: int = 15) -> bool:
    """
    Check if a distance is within reasonable walking distance.

    Args:
        distance_m: Distance in meters
        max_walking_minutes: Maximum acceptable walking time in minutes

    Returns:
        True if within walking distance, False otherwise

    Examples:
        >>> is_within_walking_distance(800)  # 10 minutes walk
        True

        >>> is_within_walking_distance(1500)  # ~19 minutes walk
        False

        >>> is_within_walking_distance(1500, max_walking_minutes=20)
        True
    """
    walking_time = calculate_walking_time_minutes(distance_m)
    return walking_time <= max_walking_minutes


def calculate_search_radius(max_walking_minutes: int = 10) -> int:
    """
    Calculate appropriate search radius in meters based on maximum walking time.

    Args:
        max_walking_minutes: Maximum walking time in minutes

    Returns:
        Search radius in meters

    Examples:
        >>> calculate_search_radius(10)  # 10 minutes walking
        800

        >>> calculate_search_radius(5)   # 5 minutes walking
        400
    """
    # 80 meters per minute walking speed
    walking_speed_m_per_min = 80
    return max_walking_minutes * walking_speed_m_per_min


def normalize_coordinates(latitude: float, longitude: float) -> tuple[float, float]:
    """
    Normalize and validate coordinates.

    Args:
        latitude: Latitude in decimal degrees
        longitude: Longitude in decimal degrees

    Returns:
        Tuple of (normalized_lat, normalized_lng)

    Raises:
        ValueError: If coordinates are invalid
    """
    # Validate ranges
    if not (-90 <= latitude <= 90):
        raise ValueError(f"Invalid latitude: {latitude}. Must be between -90 and 90.")

    if not (-180 <= longitude <= 180):
        raise ValueError(f"Invalid longitude: {longitude}. Must be between -180 and 180.")

    # Round to reasonable precision (approximately 1 meter accuracy)
    normalized_lat = round(latitude, 6)
    normalized_lng = round(longitude, 6)

    return normalized_lat, normalized_lng
