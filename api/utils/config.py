# api/utils/config.py
import os
import logging

logger = logging.getLogger("timber_framing.api")

class Config:
    """Application configuration loaded from environment variables"""
    
    # API authentication
    API_KEY = os.environ.get("API_KEY", "dev_key")
    
    # Database connection
    SUPABASE_URL = os.environ.get("SUPABASE_URL")
    SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    
    # Application settings
    DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
    
    @classmethod
    def validate(cls):
        """Validate critical configuration values"""
        if not cls.API_KEY or cls.API_KEY == "dev_key":
            logger.warning("Using development API key - not secure for production!")
            
        if not cls.SUPABASE_URL:
            logger.error("SUPABASE_URL environment variable not set")
            
        if not cls.SUPABASE_SERVICE_ROLE_KEY:
            logger.error("SUPABASE_SERVICE_ROLE_KEY environment variable not set")