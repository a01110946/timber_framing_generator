# Main FastAPI application file
# File: api/main.py

import os
from fastapi import FastAPI, Depends, HTTPException, status, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
from api.utils.auth import get_api_key
from api.utils.db import check_supabase_connection
from api.endpoints.debug import debug_router
from api.endpoints.walls import router as walls_router
from typing import Dict

# Set up logging
logger = logging.getLogger("timber_framing.api")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

# Define lifespan context manager (replaces on_event)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup code (runs before application starts)
    logger.info("Run on application startup.")
    
    # Test database connection
    if not check_supabase_connection():
        logger.error("Failed to connect to Supabase database. API may not function correctly.")
    
    yield  # This is where the application runs
    
    # Shutdown code (runs when application is shutting down)
    logger.info("Application shutting down.")

# Log startup information
logger.info("==== API INITIALIZATION STARTING ====")

# Create FastAPI application with lifespan
app = FastAPI(
    title="Timber Framing API",
    description="""
    # Timber Framing Generator API
    
    This API provides access to automated timber framing generation and analysis tools.
    
    ## Features
    
    - Wall data extraction and analysis
    - Timber framing generation based on wall data
    - Cell decomposition for detailed framing
    - Visualization data for integration with CAD systems
    
    ## Authentication
    
    All API endpoints require an API key to be provided in the `X-API-Key` header.
    Contact the API administrator to obtain an API key.
    
    ## Workflow
    
    1. Submit wall data for analysis using the `POST /walls/analyze` endpoint
    2. Receive a job ID for the analysis task
    3. Check the status of the analysis using the `GET /walls/job/{job_id}` endpoint
    4. When the status is `completed`, retrieve the results from the same endpoint
    
    ## Data Models
    
    - `WallDataInput`: Input data for wall analysis
    - `WallAnalysisJob`: Job status and results for wall analysis
    """,
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {
            "name": "Walls",
            "description": "Operations with wall data and timber framing analysis"
        },
        {
            "name": "Status",
            "description": "API status and health check endpoints"
        },
        {
            "name": "Debug",
            "description": "Debugging and testing endpoints"
        }
    ],
    lifespan=lifespan,
)

# Create a subset router for auth-free endpoints
open_router = APIRouter()

# Root endpoint
@app.get("/", tags=["Status"])
async def root():
    logger.info("Root endpoint called")
    return {"status": "online", "message": "Timber Framing API is running"}

# Basic debug endpoint in main.py
@app.get("/app-routes", tags=["Debug"])
async def app_routes():
    """Simple endpoint to list routes."""
    logger.info("App routes endpoint called")
    routes_info = []
    for route in app.routes:
        routes_info.append({
            "path": route.path,
            "name": route.name,
            "methods": list(route.methods) if hasattr(route, "methods") else []
        })
    return {"routes": routes_info}

@app.get("/debug/routes", tags=["Debug"])
async def debug_routes():
    """List all registered routes for debugging."""
    routes = []
    
    for route in app.routes:
        route_info = {
            "path": getattr(route, "path", None),
            "name": getattr(route, "name", None),
            "methods": list(getattr(route, "methods", [])),
            "endpoint": str(getattr(route, "endpoint", None)),
            "path_regex": str(getattr(route, "path_regex", None)) if hasattr(route, "path_regex") else None,
        }
        routes.append(route_info)
    
    # Add router information
    mounted_routes = []
    for router in app.routes:
        if hasattr(router, "routes"):
            for r in router.routes:
                mounted_info = {
                    "router": router.prefix,
                    "path": getattr(r, "path", None),
                    "methods": list(getattr(r, "methods", [])),
                    "name": getattr(r, "name", None),
                    "endpoint": str(getattr(r, "endpoint", None)),
                }
                mounted_routes.append(mounted_info)
    
    return {
        "app_routes": routes,
        "mounted_routes": mounted_routes
    }

# Health check endpoint (general API health)
@app.get("/health", tags=["Status"], response_model=Dict[str, str])
async def health_check():
    """Check if the API service is healthy."""
    logger.info("Health check requested")
    return {"status": "healthy", "message": "Timber Framing API is running"}

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and include API routers
# Add more routers as you develop them
# Add to main.py - outside of any router
@app.get("/env-test", tags=["Debug"])
async def test_environment_variables():
    """Test access to environment variables directly."""
    env_vars = {}
    
    # Test specific environment variables (mask sensitive values)
    api_key = os.environ.get("API_KEY")
    if api_key:
        masked_key = api_key[:4] + "..." + api_key[-4:] if len(api_key) > 8 else "***masked***"
        env_vars["API_KEY"] = f"Set: {masked_key}"
    else:
        env_vars["API_KEY"] = "Not set"
        
    supabase_url = os.environ.get("SUPABASE_URL")
    if supabase_url:
        env_vars["SUPABASE_URL"] = f"Set: {supabase_url[:10]}..."
    else:
        env_vars["SUPABASE_URL"] = "Not set"
    
    # Get other environment variables (non-sensitive ones only)
    env_vars["ENVIRONMENT"] = os.environ.get("ENVIRONMENT", "Not set")
    env_vars["PORT"] = os.environ.get("PORT", "Not set")
    
    return {
        "environment_check": "success",
        "variables": env_vars,
        "total_env_vars": len(os.environ)
    }

# Add specific routes from walls_router to open_router
@open_router.get("/open-test")
async def open_test():
    return {"status": "success", "message": "This endpoint doesn't require authentication"}

# Include the open router without auth requirements
app.include_router(
    open_router,
    prefix="/walls/open",
    tags=["Walls - No Auth"],
)

# Include routers with dependencies
app.include_router(
    walls_router,
    prefix="/walls",
    tags=["Walls"],
    dependencies=[Depends(get_api_key)]
)
logger.info("Included walls router with prefix /walls")

app.include_router(
    debug_router,
    prefix="/debug",
    tags=["Debugging"],
    dependencies=[Depends(get_api_key)]
)

@app.get("/debug-config")
async def debug_config():
    """Debug endpoint to check configuration."""
    return {
        "supabase_url_set": bool(os.environ.get("SUPABASE_URL")),
        "supabase_key_set": bool(os.environ.get("SUPABASE_SERVICE_ROLE_KEY")),
        "api_key_set": bool(os.environ.get("API_KEY")), 
        "app_version": "1.0.1"  # Increment this to confirm deployment
    }

# In api/main.py (add at the end)
from api.endpoints.debug import debug_router
app.include_router(debug_router, prefix="/debug", tags=["Debug"])

# Log completion
logger.info("==== API INITIALIZATION COMPLETE ====")

# Run with: uvicorn api.main:app --reload