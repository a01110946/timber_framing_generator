# api/utils/logging.py
import logging
import sys
import os
from logging.handlers import RotatingFileHandler
import time

# Determine if we're in production based on environment variable
IS_PRODUCTION = os.environ.get("ENVIRONMENT", "development") == "production"

class TimezoneFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        # Use local time for log timestamps
        return time.strftime(datefmt or self.default_time_format, 
                            time.localtime(record.created))

# Configure logging
def setup_logger(name):
    """Set up a logger with proper formatting and handlers."""
    # Create logger
    logger = logging.getLogger("timber_framing")
    handler = logging.StreamHandler()
    formatter = TimezoneFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)
    
    # Add file handler for production
    logger.addHandler(handler)
    logger = logging.getLogger(name)
    
    # Set default level
    logger.setLevel(logging.INFO if IS_PRODUCTION else logging.DEBUG)

    # Console handler for immediate feedback
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger

# Create loggers for different modules
api_logger = setup_logger("timber_framing.api")
db_logger = setup_logger("timber_framing.db")