# File: api/utils/auth.py
import os
from fastapi import Header, HTTPException, status
import logging

logger = logging.getLogger("timber_framing.api")

# Get the API key from environment variable
API_KEY = os.environ.get("API_KEY")

# Log all environment variables names (not values) for debugging
logger.info(f"Available environment variables: {', '.join(os.environ.keys())}")
logger.info(f"API_KEY environment variable {'IS' if API_KEY else 'IS NOT'} set")
if API_KEY:
    # Safely log part of the API key
    masked_key = API_KEY[:4] + "..." + API_KEY[-4:] if len(API_KEY) > 8 else "***masked***"
    logger.info(f"API_KEY from environment: {masked_key}")

# Fallback development key
DEV_KEY = "dev_key"

async def get_api_key(x_api_key: str = Header(...)):
    """Validate API key from header."""
    # Log received API key (safely)
    if x_api_key:
        masked_input = x_api_key[:4] + "..." + x_api_key[-4:] if len(x_api_key) > 8 else "***masked***"
        logger.info(f"Received API key: {masked_input}")
    
    # Temporary debugging - print the exact comparison
    logger.info(f"API_KEY environment variable is: {API_KEY is not None}")
    if API_KEY:
        logger.info(f"Keys match: {x_api_key == API_KEY}")
        logger.info(f"Key lengths - Env: {len(API_KEY)}, Received: {len(x_api_key)}")
    
    # In production, check against environment variable
    if API_KEY and x_api_key == API_KEY:
        logger.info("Authentication successful with production API key")
        return {"key": x_api_key, "environment": "production"}
    
    # In development, allow dev_key as fallback
    if not API_KEY and x_api_key == DEV_KEY:
        logger.info("Authentication successful with development API key")
        return {"key": x_api_key, "environment": "development"}
    
    # Log authentication failure
    logger.warning(f"Invalid API key provided")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API Key"
    )