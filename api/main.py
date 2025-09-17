"""
Hotel Recommender API - Main FastAPI Application

This module contains the main FastAPI application with health check endpoint.
"""

import os
from datetime import datetime
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse

# Load environment variables from .env file
load_dotenv()

# Create FastAPI application
app = FastAPI(
    title="Hotel Recommender API",
    description="API for hotel recommendation based on station names, price, and date",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app", host="127.0.0.1", port=8000, reload=True, log_level="info"
    )
