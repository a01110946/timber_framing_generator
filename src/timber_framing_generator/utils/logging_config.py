"""
Logging configuration for the timber framing generator.

This module provides a comprehensive logging setup with multiple levels including a custom TRACE level.
It supports file and console output with different formats and configurations for different modules.
"""

import logging
import os
import sys
from datetime import datetime
from typing import Optional

class TimberFramingLogger:
    """
    Configures logging for the timber framing generator with multiple levels.
    
    Supports:
    - Standard levels (CRITICAL, ERROR, WARNING, INFO, DEBUG)
    - Custom TRACE level for extremely detailed diagnostics
    - File and console output with different formats and levels
    - Module-specific logging configurations
    """
    
    # Define custom TRACE level (between DEBUG and NOTSET)
    TRACE_LEVEL = 5
    logging.addLevelName(TRACE_LEVEL, "TRACE")
    
    @staticmethod
    def _add_trace_method():
        """Add the TRACE method to the Logger class if not already present."""
        if not hasattr(logging.Logger, 'trace'):
            def trace(self, message, *args, **kwargs):
                """
                Log a message with level TRACE.
                
                This level provides extremely detailed tracing information beyond DEBUG.
                """
                if self.isEnabledFor(TimberFramingLogger.TRACE_LEVEL):
                    self._log(TimberFramingLogger.TRACE_LEVEL, message, args, **kwargs)
            logging.Logger.trace = trace
    
    @staticmethod
    def configure(debug_mode: bool = False, log_dir: str = "logs", rhino_mode: bool = True) -> str:
        """
        Configure the logging system for the entire application.
        
        Args:
            debug_mode: If True, sets DEBUG level for all loggers
            log_dir: Directory to store log files
            rhino_mode: If True, adjusts logging for Rhino/Grasshopper environment
            
        Returns:
            Path to the created log file
        """
        # Add TRACE method to Logger class
        TimberFramingLogger._add_trace_method()
        
        # Create logs directory
        os.makedirs(log_dir, exist_ok=True)
        
        # Generate a timestamp for this run
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(log_dir, f"timber_framing_{timestamp}.log")
        
        # Configure the root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG if debug_mode else logging.INFO)
        
        # Clear any existing handlers
        if root_logger.handlers:
            root_logger.handlers.clear()
        
        # Create file handler that logs everything
        file_handler = logging.FileHandler(log_file)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(logging.DEBUG if debug_mode else logging.INFO)
        root_logger.addHandler(file_handler)
        
        # Create console handler with a higher log level
        console_handler = logging.StreamHandler(sys.stdout)
        
        # Simplified console format for Rhino/Grasshopper environment
        if rhino_mode:
            console_formatter = logging.Formatter('%(levelname)s: %(message)s')
        else:
            console_formatter = logging.Formatter('%(name)s - %(levelname)s: %(message)s')
            
        console_handler.setFormatter(console_formatter)
        console_handler.setLevel(logging.INFO)  # Console shows less info by default
        root_logger.addHandler(console_handler)
        
        return log_file
    
    @staticmethod
    def get_logger(name: str, level: Optional[int] = None):
        """
        Get a configured logger for a specific module.
        
        Args:
            name: Logger name, typically __name__
            level: Optional specific level for this logger
            
        Returns:
            A configured logger
        """
        logger = logging.getLogger(name)
        if level:
            logger.setLevel(level)
        return logger

# For direct import convenience
def get_logger(name: str, level: Optional[int] = None):
    """
    Get a configured logger for a specific module.
    
    Convenience function that delegates to TimberFramingLogger.get_logger.
    
    Args:
        name: Logger name, typically __name__
        level: Optional specific level for this logger
        
    Returns:
        A configured logger
    """
    return TimberFramingLogger.get_logger(name, level)
