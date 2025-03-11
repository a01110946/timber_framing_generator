# Create a new file: api/endpoints/debug.py

from fastapi import APIRouter

debug_router = APIRouter()

@debug_router.get("/simple")
async def simple_test():
    return {"message": "Simple test endpoint working"}