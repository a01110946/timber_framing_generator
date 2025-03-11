# File: api/utils/auth.py
import os
from fastapi import Header, HTTPException, status, Depends
from api.utils.config import Config
import logging

logger = logging.getLogger("timber_framing.api")

# Get the API key from environment variable
API_KEY = os.environ.get("API_KEY", "dev_key")

# Log all environment variables names (not values) for debugging
logger.info(f"Available environment variables: {', '.join(os.environ.keys())}")
logger.info(f"API_KEY environment variable {'IS' if API_KEY else 'IS NOT'} set")
if API_KEY:
    # Safely log part of the API key
    masked_key = API_KEY[:4] + "..." + API_KEY[-4:] if len(API_KEY) > 8 else "***masked***"
    logger.info(f"API_KEY from environment: {masked_key}")

async def get_api_key(x_api_key: str = Header(...)):
    """Validate API key from header."""
    # Log received API key (safely)
    if x_api_key:
        masked_input = x_api_key[:4] + "..." + x_api_key[-4:] if len(x_api_key) > 8 else "***masked***"
        logger.info(f"Received API key: {masked_input}")
    
    # Check against configured API key
    if x_api_key == Config.API_KEY:
        logger.info("Authentication successful")
        return {"key": x_api_key, "environment": "production" if Config.API_KEY != "dev_key" else "development"}
    
    # Log authentication failure
    logger.warning(f"Invalid API key provided")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API Key"
    )

# Use this at the router level to ensure auth comes first
def auth_dependency():
    """Creates a dependency that requires authentication."""
    return Depends(get_api_key)