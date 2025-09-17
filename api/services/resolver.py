"""
Data resolution utilities for Hotel Recommender API

This module provides utilities for resolving and normalizing data:
- Weekday to next occurrence date conversion
- Station name normalization
- Date/time handling with Asia/Tokyo timezone
"""

import re
import unicodedata
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from api.schemas import WeekdayEnum


def resolve_date_from_weekday(
    weekday: WeekdayEnum,
    base_date: date | None = None
) -> date:
    """
    Resolve a weekday to the next occurrence of that weekday.

    Args:
        weekday: Weekday enum (mon, tue, wed, thu, fri, sat, sun)
        base_date: Base date to calculate from (defaults to today in JST)

    Returns:
        Date object representing the next occurrence of the weekday

    Examples:
        >>> resolve_date_from_weekday(WeekdayEnum.MONDAY)  # If today is Wed
        date(2025, 9, 22)  # Next Monday

        >>> resolve_date_from_weekday(WeekdayEnum.FRIDAY)  # If today is Friday
        date(2025, 9, 24)  # Next Friday (7 days later)
    """
    if base_date is None:
        # Get current date in JST
        jst = ZoneInfo("Asia/Tokyo")
        base_date = datetime.now(jst).date()

    # Map weekday enum to Python weekday (0=Monday, 6=Sunday)
    weekday_map = {
        WeekdayEnum.MONDAY: 0,
        WeekdayEnum.TUESDAY: 1,
        WeekdayEnum.WEDNESDAY: 2,
        WeekdayEnum.THURSDAY: 3,
        WeekdayEnum.FRIDAY: 4,
        WeekdayEnum.SATURDAY: 5,
        WeekdayEnum.SUNDAY: 6,
    }

    target_weekday = weekday_map[weekday]
    current_weekday = base_date.weekday()

    # Calculate days until next occurrence
    days_ahead = target_weekday - current_weekday

    # If the target day is today, move to next week
    if days_ahead <= 0:
        days_ahead += 7

    return base_date + timedelta(days=days_ahead)


def resolve_date_from_input(
    date_str: str | None = None,
    weekday: WeekdayEnum | None = None,
    base_date: date | None = None
) -> date:
    """
    Resolve date from either date string or weekday input.
    Date string takes priority over weekday.

    Args:
        date_str: Date string in YYYY-MM-DD format
        weekday: Weekday enum
        base_date: Base date for weekday calculation

    Returns:
        Resolved date object

    Raises:
        ValueError: If neither date_str nor weekday is provided
    """
    if date_str:
        return date.fromisoformat(date_str)
    elif weekday:
        return resolve_date_from_weekday(weekday, base_date)
    else:
        raise ValueError("Either date_str or weekday must be provided")


def normalize_station_name(station_name: str) -> str:
    """
    Normalize station name for consistent caching and comparison.

    Normalization steps:
    1. Strip whitespace
    2. Convert to full-width characters (zenkaku)
    3. Remove common suffixes like "駅" if present
    4. Normalize Unicode (NFC form)
    5. Convert to lowercase for ASCII characters

    Args:
        station_name: Raw station name input

    Returns:
        Normalized station name

    Examples:
        >>> normalize_station_name("新宿駅")
        '新宿'

        >>> normalize_station_name(" Shibuya Eki ")
        'shibuya'

        >>> normalize_station_name("東京 駅")
        '東京'
    """
    if not station_name or not station_name.strip():
        raise ValueError("Station name cannot be empty")

    # Strip whitespace
    normalized = station_name.strip()

    # Convert to full-width (for mixed input handling)
    # This helps standardize input like "ｼﾝｼﾞｭｸ" -> "シンジュク"
    normalized = unicodedata.normalize('NFKC', normalized)

    # Remove common station suffixes
    suffixes_to_remove = ['駅', 'えき', 'eki', 'station', 'sta.']
    for suffix in suffixes_to_remove:
        # Case-insensitive removal for ASCII
        if normalized.lower().endswith(suffix.lower()):
            normalized = normalized[:-len(suffix)].rstrip()
            break

    # Additional normalization for Unicode
    normalized = unicodedata.normalize('NFC', normalized)

    # Convert ASCII characters to lowercase for consistency
    result = ""
    for char in normalized:
        if ord(char) < 128:  # ASCII character
            result += char.lower()
        else:
            result += char

    # Remove extra whitespace
    result = re.sub(r'\s+', '', result)

    if not result:
        raise ValueError("Station name cannot be empty after normalization")

    return result


def format_distance_text(distance_m: int, station_name: str) -> str:
    """
    Format distance as human-readable Japanese text.

    Args:
        distance_m: Distance in meters
        station_name: Station name (will be denormalized for display)

    Returns:
        Formatted distance text in Japanese

    Examples:
        >>> format_distance_text(320, "新宿")
        '新宿駅から徒歩4分'

        >>> format_distance_text(80, "渋谷")
        '渋谷駅から徒歩1分'

        >>> format_distance_text(1200, "東京")
        '東京駅から徒歩15分'
    """
    # Convert distance to walking minutes (80m/min)
    walking_minutes = max(1, round(distance_m / 80))

    # Add "駅" suffix if not present in the original name
    station_display = station_name
    if not station_display.endswith('駅'):
        station_display += '駅'

    return f"{station_display}から徒歩{walking_minutes}分"


def get_current_jst_datetime() -> datetime:
    """
    Get current datetime in JST timezone.

    Returns:
        Current datetime object with JST timezone
    """
    jst = ZoneInfo("Asia/Tokyo")
    return datetime.now(jst)


def get_current_jst_date() -> date:
    """
    Get current date in JST timezone.

    Returns:
        Current date object in JST
    """
    return get_current_jst_datetime().date()


def format_reason_text(distance_m: int, price_total: int, price_max: int) -> str:
    """
    Generate a brief reason text explaining why this hotel was recommended.

    Args:
        distance_m: Distance from station in meters
        price_total: Hotel price
        price_max: Maximum price from request

    Returns:
        Brief reason text in Japanese

    Examples:
        >>> format_reason_text(320, 9800, 12000)
        '駅近(徒歩4分) × 予算内(¥9,800)'

        >>> format_reason_text(150, 11500, 12000)
        '駅近(徒歩2分) × 予算内(¥11,500)'
    """
    walking_minutes = max(1, round(distance_m / 80))

    distance_desc = f"徒歩{walking_minutes}分"
    if walking_minutes <= 3:
        distance_desc = f"駅近({distance_desc})"
    elif walking_minutes <= 7:
        distance_desc = f"好立地({distance_desc})"
    else:
        distance_desc = f"徒歩{walking_minutes}分"

    price_desc = f"予算内(¥{price_total:,})"

    return f"{distance_desc} × {price_desc}"
