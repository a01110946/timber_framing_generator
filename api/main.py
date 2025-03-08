from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from api.utils.auth import get_api_key

# Create FastAPI application
app = FastAPI(
    title="Timber Framing API",
    description="API for automated timber framing generation and analysis",
    version="0.1.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root endpoint
@app.get("/", tags=["Status"])
async def root():
    return {"status": "online", "message": "Timber Framing API is running"}

# Health check endpoint
@app.get("/health", tags=["Status"])
async def health_check():
    return {"status": "healthy"}

# Import and include API routers
from api.endpoints.walls import router as walls_router
# Add more routers as you develop them

# Include routers with dependencies
app.include_router(
    walls_router,
    prefix="/walls",
    tags=["Walls"],
    dependencies=[Depends(get_api_key)]
)

# Run with: uvicorn api.main:app --reload