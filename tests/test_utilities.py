"""
Test cases for utility functions in services modules
"""

from datetime import date

import pytest

from api.schemas import HotelInfo, StationInfo, WeekdayEnum
from api.services.distance import (
    calculate_search_radius,
    calculate_walking_time_minutes,
    distance_between_station_and_hotel,
    find_nearest_station,
    haversine_distance,
    is_within_walking_distance,
    normalize_coordinates,
)
from api.services.resolver import (
    format_distance_text,
    format_reason_text,
    normalize_station_name,
    resolve_date_from_input,
    resolve_date_from_weekday,
)


class TestResolver:
    """Test cases for resolver utility functions"""

    def test_resolve_date_from_weekday_next_occurrence(self):
        """Test resolving weekday to next occurrence"""
        # Test with a known date (Wednesday, 2025-09-17)
        base_date = date(2025, 9, 17)  # Wednesday

        # Next Monday should be 2025-09-22
        result = resolve_date_from_weekday(WeekdayEnum.MONDAY, base_date)
        assert result == date(2025, 9, 22)

        # Next Friday should be 2025-09-19
        result = resolve_date_from_weekday(WeekdayEnum.FRIDAY, base_date)
        assert result == date(2025, 9, 19)

        # Next Wednesday should be next week (2025-09-24)
        result = resolve_date_from_weekday(WeekdayEnum.WEDNESDAY, base_date)
        assert result == date(2025, 9, 24)

    def test_resolve_date_from_input_date_priority(self):
        """Test that date string takes priority over weekday"""
        date_str = "2025-12-25"
        weekday = WeekdayEnum.MONDAY

        result = resolve_date_from_input(date_str=date_str, weekday=weekday)
        assert result == date(2025, 12, 25)

    def test_resolve_date_from_input_weekday_fallback(self):
        """Test using weekday when date_str is None"""
        base_date = date(2025, 9, 17)  # Wednesday

        result = resolve_date_from_input(
            date_str=None,
            weekday=WeekdayEnum.SATURDAY,
            base_date=base_date
        )
        assert result == date(2025, 9, 20)

    def test_resolve_date_from_input_error(self):
        """Test error when neither date nor weekday provided"""
        with pytest.raises(ValueError, match="Either date_str or weekday must be provided"):
            resolve_date_from_input(date_str=None, weekday=None)

    def test_normalize_station_name_japanese(self):
        """Test normalization of Japanese station names"""
        assert normalize_station_name("新宿駅") == "新宿"
        assert normalize_station_name("  東京駅  ") == "東京"
        assert normalize_station_name("渋谷") == "渋谷"

    def test_normalize_station_name_english(self):
        """Test normalization of English station names"""
        assert normalize_station_name("Shinjuku Station") == "shinjuku"
        assert normalize_station_name("Tokyo Eki") == "tokyo"
        assert normalize_station_name("  SHIBUYA  ") == "shibuya"

    def test_normalize_station_name_mixed(self):
        """Test normalization of mixed input"""
        assert normalize_station_name("新宿 Station") == "新宿"
        assert normalize_station_name("Tokyo 駅") == "tokyo"

    def test_normalize_station_name_empty_error(self):
        """Test error for empty station names"""
        with pytest.raises(ValueError, match="Station name cannot be empty"):
            normalize_station_name("")

        with pytest.raises(ValueError, match="Station name cannot be empty"):
            normalize_station_name("   ")

    def test_format_distance_text(self):
        """Test distance text formatting"""
        assert format_distance_text(320, "新宿") == "新宿駅から徒歩4分"
        assert format_distance_text(80, "渋谷駅") == "渋谷駅から徒歩1分"
        assert format_distance_text(1200, "東京") == "東京駅から徒歩15分"

    def test_format_reason_text(self):
        """Test reason text generation"""
        # Short walking distance
        result = format_reason_text(240, 9800, 12000)  # 3 minutes
        assert "駅近" in result
        assert "¥9,800" in result

        # Medium walking distance
        result = format_reason_text(400, 11500, 12000)  # 5 minutes
        assert "好立地" in result
        assert "¥11,500" in result

        # Longer walking distance
        result = format_reason_text(800, 8000, 12000)  # 10 minutes
        assert "徒歩10分" in result
        assert "¥8,000" in result


class TestDistance:
    """Test cases for distance calculation functions"""

    def test_haversine_distance_known_points(self):
        """Test Haversine distance calculation with known points"""
        # Tokyo Station to Shinjuku Station (approximately 6.1km)
        tokyo_lat, tokyo_lng = 35.6812, 139.7671
        shinjuku_lat, shinjuku_lng = 35.6896, 139.7006

        distance = haversine_distance(tokyo_lat, tokyo_lng, shinjuku_lat, shinjuku_lng)

        # Should be approximately 6080 meters (allow reasonable tolerance)
        assert 6000 <= distance <= 6200

    def test_haversine_distance_same_point(self):
        """Test distance calculation for same point"""
        lat, lng = 35.6812, 139.7671
        distance = haversine_distance(lat, lng, lat, lng)
        assert distance == 0.0

    def test_haversine_distance_invalid_coordinates(self):
        """Test error handling for invalid coordinates"""
        with pytest.raises(ValueError, match="Latitude must be between -90 and 90"):
            haversine_distance(95, 139, 35, 139)  # Invalid latitude

        with pytest.raises(ValueError, match="Longitude must be between -180 and 180"):
            haversine_distance(35, 185, 35, 139)  # Invalid longitude

    def test_calculate_walking_time_minutes(self):
        """Test walking time calculation"""
        assert calculate_walking_time_minutes(320) == 4  # 320m / 80m/min = 4min
        assert calculate_walking_time_minutes(80) == 1   # 80m / 80m/min = 1min
        assert calculate_walking_time_minutes(50) == 1   # Minimum 1 minute
        assert calculate_walking_time_minutes(160) == 2  # 160m / 80m/min = 2min

    def test_calculate_walking_time_negative_distance(self):
        """Test error for negative distance"""
        with pytest.raises(ValueError, match="Distance cannot be negative"):
            calculate_walking_time_minutes(-100)

    def test_distance_between_station_and_hotel(self):
        """Test distance calculation between station and hotel objects"""
        station = StationInfo(
            name="新宿駅",
            normalized_name="新宿",
            latitude=35.6896,
            longitude=139.7006,
            place_id="place_123"
        )

        hotel = HotelInfo(
            hotel_id="12345",
            name="ホテル新宿",
            latitude=35.6900,  # Slightly north
            longitude=139.7010,  # Slightly east
            price_total=10000,
            booking_url="https://example.com"
        )

        distance = distance_between_station_and_hotel(station, hotel)

        # Should be a small distance (few tens of meters)
        assert 40 <= distance <= 60

    def test_find_nearest_station(self):
        """Test finding nearest station from a list"""
        hotel = HotelInfo(
            hotel_id="12345",
            name="Test Hotel",
            latitude=35.6896,  # Near Shinjuku
            longitude=139.7006,
            price_total=10000,
            booking_url="https://example.com"
        )

        stations = [
            StationInfo(name="新宿駅", normalized_name="新宿", latitude=35.6896, longitude=139.7006, place_id="place_1"),
            StationInfo(name="東京駅", normalized_name="東京", latitude=35.6812, longitude=139.7671, place_id="place_2"),
            StationInfo(name="渋谷駅", normalized_name="渋谷", latitude=35.6598, longitude=139.7036, place_id="place_3"),
        ]

        nearest_station, distance = find_nearest_station(hotel, stations)

        assert nearest_station.name == "新宿駅"
        assert distance < 100  # Should be very close

    def test_find_nearest_station_empty_list(self):
        """Test error when stations list is empty"""
        hotel = HotelInfo(
            hotel_id="12345",
            name="Test Hotel",
            latitude=35.6896,
            longitude=139.7006,
            price_total=10000,
            booking_url="https://example.com"
        )

        with pytest.raises(ValueError, match="Stations list cannot be empty"):
            find_nearest_station(hotel, [])

    def test_is_within_walking_distance(self):
        """Test walking distance check"""
        assert is_within_walking_distance(800) is True   # 10 minutes
        assert is_within_walking_distance(1200) is True  # 15 minutes
        assert is_within_walking_distance(1500) is False # ~19 minutes
        assert is_within_walking_distance(1500, max_walking_minutes=20) is True

    def test_calculate_search_radius(self):
        """Test search radius calculation"""
        assert calculate_search_radius(10) == 800  # 10 min * 80 m/min
        assert calculate_search_radius(5) == 400   # 5 min * 80 m/min
        assert calculate_search_radius(15) == 1200 # 15 min * 80 m/min

    def test_normalize_coordinates(self):
        """Test coordinate normalization and validation"""
        # Valid coordinates
        lat, lng = normalize_coordinates(35.681236, 139.767125)
        assert lat == 35.681236
        assert lng == 139.767125

        # Invalid latitude
        with pytest.raises(ValueError, match="Invalid latitude"):
            normalize_coordinates(95.0, 139.0)

        # Invalid longitude
        with pytest.raises(ValueError, match="Invalid longitude"):
            normalize_coordinates(35.0, 185.0)
