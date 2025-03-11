# api/utils/logging.py
import logging
import sys
import os
from logging.handlers import RotatingFileHandler

# Determine if we're in production based on environment variable
IS_PRODUCTION = os.environ.get("ENVIRONMENT", "development") == "production"

# Configure logging
def setup_logger(name):
    """Set up a logger with proper formatting and handlers."""
    logger = logging.getLogger(name)
    
    # Set default level
    logger.setLevel(logging.INFO if IS_PRODUCTION else logging.DEBUG)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Console handler for immediate feedback
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger

# Create loggers for different modules
api_logger = setup_logger("timber_framing.api")
db_logger = setup_logger("timber_framing.db")