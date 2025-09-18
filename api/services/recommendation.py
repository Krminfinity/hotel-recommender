"""
Hotel Recommendation Engine for intelligent ranking and scoring.

This module implements sophisticated algorithms to rank and recommend hotels
based on multiple criteria including location, price, amenities, and user preferences.
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any

from api.services.distance import haversine_distance
from api.schemas import HotelInfo, StationInfo
from api.services.distance import haversine_distance


logger = logging.getLogger(__name__)


class RankingCriteria(Enum):
    """Enum for different ranking criteria weights."""
    DISTANCE_FOCUSED = "distance_focused"      # Prioritize proximity to station
    BUDGET_FOCUSED = "budget_focused"          # Prioritize value for money
    COMFORT_FOCUSED = "comfort_focused"        # Prioritize amenities and features
    BALANCED = "balanced"                      # Equal weight to all factors


@dataclass
class RankingWeights:
    """Weights for different ranking factors."""
    distance: float = 0.4          # Weight for distance from station
    price_value: float = 0.3       # Weight for price-to-value ratio
    amenities: float = 0.2         # Weight for hotel amenities/features
    availability: float = 0.1      # Weight for booking availability
    
    def __post_init__(self):
        """Validate that weights sum to 1.0."""
        total = self.distance + self.price_value + self.amenities + self.availability
        if not math.isclose(total, 1.0, rel_tol=1e-6):
            raise ValueError(f"Ranking weights must sum to 1.0, got {total}")


@dataclass
class RecommendationContext:
    """Context information for hotel recommendation."""
    user_budget: int                           # Maximum budget per night (JPY)
    stations: List[StationInfo]               # Target stations
    check_in_date: date                       # Check-in date
    preferred_criteria: RankingCriteria       # User's preference
    max_walking_distance_m: int = 1000        # Maximum acceptable walking distance
    min_acceptable_rating: float = 3.0        # Minimum hotel rating threshold
    preferred_amenities: List[str] = field(default_factory=list)  # Preferred amenities list


@dataclass
class HotelScore:
    """Detailed scoring breakdown for a hotel."""
    hotel_id: str
    total_score: float              # Final composite score (0.0-1.0)
    
    # Component scores (0.0-1.0 each)
    distance_score: float
    price_score: float
    amenities_score: float
    availability_score: float
    
    # Additional metrics
    nearest_station: str            # Name of nearest station
    walking_time_minutes: int       # Walking time to nearest station
    price_rank: int                # Ranking by price (1=cheapest)
    value_rank: int                # Ranking by value (1=best value)
    
    # Explanation for user
    recommendation_reason: str      # Human-readable explanation


class HotelRecommendationEngine:
    """
    Advanced hotel recommendation engine with multi-criteria ranking.
    
    This engine uses a weighted scoring system that considers:
    - Distance from stations (with walking time penalties)
    - Price value optimization (not just cheapest, but best value)
    - Amenities matching user preferences
    - Booking availability and cancellation flexibility
    """
    
    # Predefined ranking weights for different user preferences
    CRITERIA_WEIGHTS = {
        RankingCriteria.DISTANCE_FOCUSED: RankingWeights(0.6, 0.2, 0.1, 0.1),
        RankingCriteria.BUDGET_FOCUSED: RankingWeights(0.2, 0.6, 0.1, 0.1),
        RankingCriteria.COMFORT_FOCUSED: RankingWeights(0.1, 0.2, 0.6, 0.1),
        RankingCriteria.BALANCED: RankingWeights(0.4, 0.3, 0.2, 0.1),
    }
    
    def __init__(self):
        """Initialize the recommendation engine."""
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
    def rank_hotels(
        self, 
        hotels: List[HotelInfo], 
        context: RecommendationContext
    ) -> List[Tuple[HotelInfo, HotelScore]]:
        """
        Rank hotels using multi-criteria scoring algorithm.
        
        Args:
            hotels: List of hotels to rank
            context: Recommendation context with user preferences
            
        Returns:
            List of (hotel, score) tuples sorted by score (descending)
        """
        if not hotels:
            self.logger.warning("No hotels provided for ranking")
            return []
        
        # Get weights for user preference
        weights = self.CRITERIA_WEIGHTS[context.preferred_criteria]
        
        # Calculate all component scores
        scored_hotels = []
        
        for hotel in hotels:
            # Skip hotels outside acceptable criteria
            if not self._meets_minimum_criteria(hotel, context):
                continue
                
            score = self._calculate_hotel_score(hotel, context, weights)
            scored_hotels.append((hotel, score))
        
        # Sort by total score (descending)
        scored_hotels.sort(key=lambda x: x[1].total_score, reverse=True)
        
        # Update ranking-dependent fields (price_rank, value_rank)
        self._update_relative_rankings(scored_hotels)
        
        self.logger.info(f"Ranked {len(scored_hotels)} hotels out of {len(hotels)} candidates")
        return scored_hotels
    
    def _calculate_hotel_score(
        self, 
        hotel: HotelInfo, 
        context: RecommendationContext,
        weights: RankingWeights
    ) -> HotelScore:
        """
        Calculate detailed scoring for a single hotel.
        
        Args:
            hotel: Hotel to score
            context: Recommendation context
            weights: Scoring weights
            
        Returns:
            HotelScore with detailed breakdown
        """
        # Calculate component scores
        distance_score = self._calculate_distance_score(hotel, context.stations)
        price_score = self._calculate_price_score(hotel, context.user_budget)
        amenities_score = self._calculate_amenities_score(hotel, context.preferred_amenities)
        availability_score = self._calculate_availability_score(hotel)
        
        # Calculate weighted total
        total_score = (
            weights.distance * distance_score +
            weights.price_value * price_score +
            weights.amenities * amenities_score +
            weights.availability * availability_score
        )
        
        # Find nearest station
        nearest_station, walking_time = self._find_nearest_station(hotel, context.stations)
        
        # Generate recommendation reason
        reason = self._generate_recommendation_reason(
            hotel, distance_score, price_score, amenities_score, context.preferred_criteria
        )
        
        return HotelScore(
            hotel_id=hotel.hotel_id,
            total_score=total_score,
            distance_score=distance_score,
            price_score=price_score,
            amenities_score=amenities_score,
            availability_score=availability_score,
            nearest_station=nearest_station,
            walking_time_minutes=walking_time,
            price_rank=0,  # Will be updated in _update_relative_rankings
            value_rank=0,  # Will be updated in _update_relative_rankings
            recommendation_reason=reason
        )
    
    def _calculate_distance_score(self, hotel: HotelInfo, stations: List[StationInfo]) -> float:
        """
        Calculate distance score based on proximity to stations.
        
        Closer hotels get higher scores, with exponential decay for far distances.
        Walking time is also considered (hills, barriers, etc.)
        
        Args:
            hotel: Hotel to score
            stations: Target stations
            
        Returns:
            Distance score (0.0-1.0)
        """
        if not stations:
            return 0.5  # Neutral score if no stations
        
        min_distance_m = float('inf')
        
        for station in stations:
            distance_m = haversine_distance(
                hotel.latitude, hotel.longitude,
                station.latitude, station.longitude
            )  # Already returns meters
            
            min_distance_m = min(min_distance_m, distance_m)
        
        # Exponential decay: perfect score at 0m, 0.5 score at 500m, near 0 at 2000m
        if min_distance_m <= 0:
            return 1.0
        elif min_distance_m >= 2000:
            return 0.1  # Minimum score for very far hotels
        else:
            # Exponential decay formula
            return math.exp(-min_distance_m / 600.0) * 0.9 + 0.1
    
    def _calculate_price_score(self, hotel: HotelInfo, max_budget: int) -> float:
        """
        Calculate price score based on value-for-money, not just cheapness.
        
        Best value is around 60-70% of budget, not the absolute cheapest.
        
        Args:
            hotel: Hotel to score
            max_budget: Maximum user budget
            
        Returns:
            Price score (0.0-1.0)
        """
        if hotel.price_total <= 0:
            return 0.0  # Invalid price
        
        if hotel.price_total > max_budget:
            return 0.0  # Over budget
        
        # Calculate budget utilization ratio
        budget_ratio = hotel.price_total / max_budget
        
        # Optimal value is around 0.6-0.7 of budget
        # Too cheap might indicate poor quality, too expensive reduces value
        if budget_ratio <= 0.3:
            # Very cheap - linear increase from 0.5 to 0.8
            return 0.5 + (budget_ratio / 0.3) * 0.3
        elif budget_ratio <= 0.7:
            # Sweet spot - high scores
            return 0.8 + (1 - abs(budget_ratio - 0.6) / 0.1) * 0.2
        else:
            # Expensive - linear decrease from 0.8 to 0.1
            return 0.8 - ((budget_ratio - 0.7) / 0.3) * 0.7
    
    def _calculate_amenities_score(self, hotel: HotelInfo, preferred_amenities: List[str]) -> float:
        """
        Calculate amenities score based on feature matching and quality.
        
        Args:
            hotel: Hotel to score
            preferred_amenities: User's preferred amenities
            
        Returns:
            Amenities score (0.0-1.0)
        """
        if not hotel.highlights:
            return 0.2  # Base score for hotels with no listed amenities
        
        # Base score from number of amenities (more is generally better)
        amenity_count_score = min(len(hotel.highlights) / 10.0, 0.6)  # Max 0.6 for count
        
        # Bonus score for matching user preferences
        preference_score = 0.0
        if preferred_amenities:
            matches = 0
            for amenity in hotel.highlights:
                for preferred in preferred_amenities:
                    if preferred.lower() in amenity.lower():
                        matches += 1
                        break
            
            preference_score = min(matches / len(preferred_amenities), 0.4)  # Max 0.4 for matches
        
        # Special bonus for high-value amenities
        high_value_amenities = [
            "wifi", "parking", "breakfast", "onsen", "spa", "gym", "restaurant",
            "concierge", "business", "meeting", "airport", "shuttle"
        ]
        
        high_value_score = 0.0
        for amenity in hotel.highlights:
            for high_value in high_value_amenities:
                if high_value in amenity.lower():
                    high_value_score += 0.05  # Up to 0.6 total for all high-value amenities
        
        high_value_score = min(high_value_score, 0.4)
        
        return amenity_count_score + preference_score + high_value_score
    
    def _calculate_availability_score(self, hotel: HotelInfo) -> float:
        """
        Calculate availability score based on booking flexibility.
        
        Args:
            hotel: Hotel to score
            
        Returns:
            Availability score (0.0-1.0)
        """
        base_score = 0.7  # Base score assuming hotel is available
        
        # Bonus for cancellable bookings
        if hotel.cancellable is True:
            base_score += 0.3
        elif hotel.cancellable is False:
            base_score -= 0.2
        # If None/unknown, no change to base score
        
        return max(0.0, min(1.0, base_score))
    
    def _meets_minimum_criteria(self, hotel: HotelInfo, context: RecommendationContext) -> bool:
        """
        Check if hotel meets minimum acceptable criteria.
        
        Args:
            hotel: Hotel to check
            context: Recommendation context
            
        Returns:
            True if hotel meets minimum criteria
        """
        # Check price limit
        if hotel.price_total > context.user_budget:
            return False
        
        # Check maximum walking distance
        if context.stations:
            min_distance_m = float('inf')
            for station in context.stations:
                distance_m = haversine_distance(
                    hotel.latitude, hotel.longitude,
                    station.latitude, station.longitude
                )  # Already returns meters
                min_distance_m = min(min_distance_m, distance_m)
            
            if min_distance_m > context.max_walking_distance_m:
                return False
        
        return True
    
    def _find_nearest_station(
        self, 
        hotel: HotelInfo, 
        stations: List[StationInfo]
    ) -> Tuple[str, int]:
        """
        Find nearest station and calculate walking time.
        
        Args:
            hotel: Hotel
            stations: Available stations
            
        Returns:
            Tuple of (station_name, walking_time_minutes)
        """
        if not stations:
            return "Unknown", 0
        
        nearest_station = None
        min_distance_m = float('inf')
        
        for station in stations:
            distance_m = haversine_distance(
                hotel.latitude, hotel.longitude,
                station.latitude, station.longitude
            )  # Already returns meters
            
            if distance_m < min_distance_m:
                min_distance_m = distance_m
                nearest_station = station
        
        # Calculate walking time (assume 80m/minute walking speed)
        walking_time = int(min_distance_m / 80)
        
        return nearest_station.name if nearest_station else "Unknown", walking_time
    
    def _generate_recommendation_reason(
        self, 
        hotel: HotelInfo, 
        distance_score: float,
        price_score: float,
        amenities_score: float,
        criteria: RankingCriteria
    ) -> str:
        """
        Generate human-readable explanation for recommendation.
        
        Args:
            hotel: Hotel being scored
            distance_score: Distance component score
            price_score: Price component score
            amenities_score: Amenities component score
            criteria: User's ranking criteria
            
        Returns:
            Human-readable recommendation reason
        """
        reasons = []
        
        # Analyze strongest factors
        if distance_score > 0.8:
            reasons.append("駅から非常に近い立地")
        elif distance_score > 0.6:
            reasons.append("駅から徒歩圏内の好立地")
        
        if price_score > 0.8:
            reasons.append("優れたコストパフォーマンス")
        elif price_score > 0.6:
            reasons.append("お手頃な価格設定")
        
        if amenities_score > 0.8:
            reasons.append("充実した設備・サービス")
        elif amenities_score > 0.6:
            reasons.append("良質なアメニティ")
        
        # Add criteria-specific reasoning
        if criteria == RankingCriteria.DISTANCE_FOCUSED:
            if distance_score > 0.5:
                reasons.append("アクセス重視の条件に最適")
        elif criteria == RankingCriteria.BUDGET_FOCUSED:
            if price_score > 0.5:
                reasons.append("予算効率を重視した選択")
        elif criteria == RankingCriteria.COMFORT_FOCUSED:
            if amenities_score > 0.5:
                reasons.append("快適性重視の条件に適合")
        
        if not reasons:
            reasons.append("バランスの取れた選択肢")
        
        return "、".join(reasons[:3])  # Limit to top 3 reasons
    
    def _update_relative_rankings(self, scored_hotels: List[Tuple[HotelInfo, HotelScore]]) -> None:
        """
        Update price_rank and value_rank based on relative comparison.
        
        Args:
            scored_hotels: List of (hotel, score) tuples to update
        """
        # Sort by price for price ranking
        price_sorted = sorted(scored_hotels, key=lambda x: x[0].price_total)
        for i, (hotel, score) in enumerate(price_sorted):
            score.price_rank = i + 1
        
        # Value rank is based on price_score (already calculated)
        value_sorted = sorted(scored_hotels, key=lambda x: x[1].price_score, reverse=True)
        for i, (hotel, score) in enumerate(value_sorted):
            score.value_rank = i + 1