"""
Hotel Recommender API - Main FastAPI Application

This module contains the main FastAPI application with hotel suggestion endpoints.
"""

import os
import logging
from datetime import datetime
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.schemas import SuggestionRequest, SuggestionResponse, ErrorResponse
from api.services.hotel_service import HotelRecommendationService
from api.providers.hotel_rakuten import RakutenHotelProvider
from api.providers.station_google import GooglePlacesStationProvider
from api.providers.station_base import StationNotFoundError
from api.providers.hotel_base import HotelNotFoundError

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI application
app = FastAPI(
    title="Hotel Recommender API",
    description="API for hotel recommendation based on station names, price, and date",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize providers and services
_station_provider = None
_hotel_provider = None
_recommendation_service = None


def get_recommendation_service() -> HotelRecommendationService:
    """Get or create the recommendation service."""
    global _station_provider, _hotel_provider, _recommendation_service
    
    if _recommendation_service is None:
        _station_provider = GooglePlacesStationProvider()
        _hotel_provider = RakutenHotelProvider()
        _recommendation_service = HotelRecommendationService(
            station_provider=_station_provider,
            hotel_provider=_hotel_provider
        )
    
    return _recommendation_service


@app.get("/health")
async def health_check() -> dict[str, Any]:
    """
    Health check endpoint to verify the API is running.

    Returns:
        Dict containing status and timestamp information
    """
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "hotel-recommender",
        "version": "0.1.0",
        "environment": {
            "google_places_configured": bool(os.getenv("GOOGLE_PLACES_API_KEY")),
            "rakuten_app_configured": bool(os.getenv("RAKUTEN_APP_ID")),
            "rakuten_affiliate_configured": bool(os.getenv("RAKUTEN_AFFILIATE_ID")),
        },
    }


@app.post("/api/suggest", response_model=SuggestionResponse)
async def suggest_hotels(request: SuggestionRequest) -> SuggestionResponse:
    """
    Get hotel recommendations based on user input.
    
    This is the main MVP endpoint that provides hotel suggestions based on:
    - Station names (1-10 stations)
    - Maximum price per night (JPY)
    - Check-in date or weekday
    
    Args:
        request: Hotel suggestion request containing user preferences
        
    Returns:
        SuggestionResponse: Up to 3 recommended hotels with booking links
        
    Raises:
        HTTPException: 
            - 400: Invalid request parameters
            - 404: No stations or hotels found
            - 500: Internal server error
            - 503: External service unavailable
    """
    try:
        logger.info(f"Processing hotel suggestion request: {len(request.stations)} stations, max price: {request.price_max} JPY")
        
        # Use the hotel recommendation service
        recommendation_service = get_recommendation_service()
        response = await recommendation_service.get_hotel_recommendations(request)
        
        logger.info(f"Successfully returned {len(response.results)} hotel recommendations")
        return response
        
    except StationNotFoundError as e:
        logger.warning(f"Stations not found: {e}")
        raise HTTPException(
            status_code=404,
            detail={
                "error": "STATIONS_NOT_FOUND",
                "message": str(e),
                "timestamp": datetime.now().isoformat()
            }
        )
    
    except HotelNotFoundError as e:
        logger.info(f"No hotels found: {e}")
        # Return empty results instead of error for better UX
        from api.services.resolver import resolve_date_from_input
        resolved_date = resolve_date_from_input(request.date, request.weekday)
        return SuggestionResponse(
            resolved_date=resolved_date.isoformat(),
            results=[]
        )
    
    except ValueError as e:
        logger.error(f"Invalid request parameters: {e}")
        raise HTTPException(
            status_code=400,
            detail={
                "error": "INVALID_REQUEST",
                "message": f"Invalid request parameters: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
        )
    
    except Exception as e:
        logger.error(f"Unexpected error in suggest_hotels: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred while processing your request",
                "timestamp": datetime.now().isoformat()
            }
        )


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler for unhandled exceptions."""
    return JSONResponse(
        status_code=500,
        content={
            "error": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected error occurred",
            "timestamp": datetime.now().isoformat(),
        },
    )


@app.get("/", response_class=FileResponse)
async def read_root():
    """Serve the main HTML page."""
    return FileResponse("static/index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app", host="127.0.0.1", port=8000, reload=True, log_level="info"
    )
