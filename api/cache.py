"""
TTL-based in-memory cache system for Hotel Recommender API

This module provides a simple but effective caching system with time-to-live (TTL)
functionality for station and hotel data. It helps reduce external API calls
and improve response times.
"""

import asyncio
import time
from typing import Any, Dict, Optional, TypeVar, Generic
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta

T = TypeVar('T')


@dataclass
class CacheEntry(Generic[T]):
    """
    A single cache entry with TTL support.
    """
    value: T
    expiry_time: float
    created_at: float
    access_count: int = 0
    last_accessed: float = 0

    def is_expired(self) -> bool:
        """Check if this cache entry has expired."""
        return time.time() > self.expiry_time

    def access(self) -> T:
        """Mark entry as accessed and return value."""
        self.access_count += 1
        self.last_accessed = time.time()
        return self.value


class TTLCache(Generic[T]):
    """
    Thread-safe TTL cache implementation.
    
    This cache automatically expires entries after a specified time-to-live (TTL)
    and provides statistics for monitoring cache performance.
    """

    def __init__(self, default_ttl_seconds: int = 3600, max_size: int = 1000):
        """
        Initialize TTL cache.
        
        Args:
            default_ttl_seconds: Default TTL in seconds
            max_size: Maximum number of entries to store
        """
        self.default_ttl = default_ttl_seconds
        self.max_size = max_size
        self._cache: Dict[str, CacheEntry[T]] = {}
        self._lock = threading.RLock()
        
        # Statistics
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        
        # Background cleanup
        self._cleanup_task: Optional[asyncio.Task] = None
        self._cleanup_interval = min(300, default_ttl_seconds // 4)  # Every 5 minutes or TTL/4

    async def get(self, key: str) -> Optional[T]:
        """
        Get value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value if exists and not expired, None otherwise
        """
        with self._lock:
            entry = self._cache.get(key)
            
            if entry is None:
                self._misses += 1
                return None
                
            if entry.is_expired():
                del self._cache[key]
                self._misses += 1
                return None
                
            self._hits += 1
            return entry.access()

    async def set(
        self, 
        key: str, 
        value: T, 
        ttl_seconds: Optional[int] = None
    ) -> None:
        """
        Set value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: TTL in seconds (uses default if None)
        """
        ttl = ttl_seconds or self.default_ttl
        current_time = time.time()
        expiry_time = current_time + ttl
        
        with self._lock:
            # Evict if at max size and key doesn't exist
            if len(self._cache) >= self.max_size and key not in self._cache:
                await self._evict_oldest()
                
            entry = CacheEntry(
                value=value,
                expiry_time=expiry_time,
                created_at=current_time,
                last_accessed=current_time
            )
            
            self._cache[key] = entry

    async def delete(self, key: str) -> bool:
        """
        Delete entry from cache.
        
        Args:
            key: Cache key
            
        Returns:
            True if key existed, False otherwise
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    async def clear(self) -> None:
        """Clear all entries from cache."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
            self._evictions = 0

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = (self._hits / total_requests) if total_requests > 0 else 0
            
            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
                "evictions": self._evictions,
                "default_ttl": self.default_ttl,
            }

    async def _evict_oldest(self) -> None:
        """Evict the oldest entry to make room."""
        if not self._cache:
            return
            
        # Find oldest entry by creation time
        oldest_key = min(
            self._cache.keys(),
            key=lambda k: self._cache[k].created_at
        )
        
        del self._cache[oldest_key]
        self._evictions += 1

    async def _cleanup_expired(self) -> None:
        """Remove expired entries from cache."""
        current_time = time.time()
        expired_keys = []
        
        with self._lock:
            for key, entry in self._cache.items():
                if entry.expiry_time <= current_time:
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self._cache[key]

    async def start_cleanup_task(self) -> None:
        """Start background cleanup task."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop_cleanup_task(self) -> None:
        """Stop background cleanup task."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    async def _cleanup_loop(self) -> None:
        """Background cleanup loop."""
        try:
            while True:
                await asyncio.sleep(self._cleanup_interval)
                await self._cleanup_expired()
        except asyncio.CancelledError:
            pass


class CacheManager:
    """
    Manager for multiple caches with different TTL settings.
    
    This provides a centralized way to manage different types of cached data
    with appropriate TTL settings for each type.
    """

    def __init__(self):
        """Initialize cache manager with predefined caches."""
        import os
        
        # Station cache: 24 hours (stations don't change frequently)
        station_ttl = int(os.getenv("STATION_CACHE_TTL", "86400"))  # 24 hours
        self.station_cache = TTLCache[list](
            default_ttl_seconds=station_ttl,
            max_size=500  # Reasonable number of stations
        )
        
        # Hotel cache: 15 minutes (prices/availability change frequently)
        hotel_ttl = int(os.getenv("HOTEL_CACHE_TTL", "900"))  # 15 minutes
        self.hotel_cache = TTLCache[list](
            default_ttl_seconds=hotel_ttl,
            max_size=1000  # More hotel searches
        )
        
        # General purpose cache
        self.general_cache = TTLCache[Any](
            default_ttl_seconds=3600,  # 1 hour
            max_size=200
        )
        
        self._caches = {
            "stations": self.station_cache,
            "hotels": self.hotel_cache,
            "general": self.general_cache,
        }

    async def start_cleanup(self) -> None:
        """Start cleanup tasks for all caches."""
        for cache in self._caches.values():
            await cache.start_cleanup_task()

    async def stop_cleanup(self) -> None:
        """Stop cleanup tasks for all caches."""
        for cache in self._caches.values():
            await cache.stop_cleanup_task()

    async def clear_all(self) -> None:
        """Clear all caches."""
        for cache in self._caches.values():
            await cache.clear()

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """
        Get statistics for all caches.
        
        Returns:
            Dictionary with stats for each cache type
        """
        return {
            cache_name: cache.get_stats()
            for cache_name, cache in self._caches.items()
        }

    async def health_check(self) -> Dict[str, bool]:
        """
        Perform health check on all caches.
        
        Returns:
            Dictionary indicating health status of each cache
        """
        health = {}
        
        for cache_name, cache in self._caches.items():
            try:
                # Test cache operations
                test_key = f"__health_check_{cache_name}_{int(time.time())}"
                await cache.set(test_key, "test_value", 1)
                result = await cache.get(test_key)
                await cache.delete(test_key)
                
                health[cache_name] = result == "test_value"
            except Exception:
                health[cache_name] = False
        
        return health


# Global cache manager instance
cache_manager = CacheManager()


# Convenience functions for common operations
async def get_station_cache(key: str):
    """Get value from station cache."""
    return await cache_manager.station_cache.get(key)


async def set_station_cache(key: str, value, ttl_seconds: Optional[int] = None):
    """Set value in station cache."""
    await cache_manager.station_cache.set(key, value, ttl_seconds)


async def get_hotel_cache(key: str):
    """Get value from hotel cache."""
    return await cache_manager.hotel_cache.get(key)


async def set_hotel_cache(key: str, value, ttl_seconds: Optional[int] = None):
    """Set value in hotel cache."""
    await cache_manager.hotel_cache.set(key, value, ttl_seconds)


async def get_cache_stats() -> Dict[str, Any]:
    """Get comprehensive cache statistics."""
    return {
        "caches": cache_manager.get_all_stats(),
        "health": await cache_manager.health_check(),
        "timestamp": datetime.now().isoformat(),
    }