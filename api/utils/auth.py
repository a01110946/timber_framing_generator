# File: api/utils/auth.py

import os
from fastapi import Header, HTTPException, status

# In a real application, store these securely and not in code
API_KEYS = {
    "dev_key": "development",
    os.environ.get("PRODUCTION_API_KEY", "invalid"): "production"
}

async def get_api_key(x_api_key: str = Header(...)):
    """Validate API key from header."""
    if x_api_key not in API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key"
        )
    return {"key": x_api_key, "environment": API_KEYS[x_api_key]}