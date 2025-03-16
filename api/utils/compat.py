# api/utils/compat.py
"""
Compatibility utilities for cross-version Python support.
Provides fallbacks for features not available in all Python versions.
"""

import sys
import contextlib

# Try to import timeout from contextlib (should be available in Python 3.11+)
try:
    from contextlib import timeout
except ImportError:
    # Create our own timeout context manager
    import threading
    import time
    
    class TimeoutError(Exception):
        """Raised when a function times out."""
        pass
    
    @contextlib.contextmanager
    def timeout(seconds):
        """
        Context manager for timing out operations.
        
        Simple implementation for environments where contextlib.timeout
        is not available.
        
        Args:
            seconds: Timeout duration in seconds
            
        Raises:
            TimeoutError: If the operation times out
        """
        timer = threading.Timer(seconds, lambda: (_ for _ in ()).throw(TimeoutError()))
        timer.daemon = True
        
        try:
            timer.start()
            yield
        finally:
            timer.cancel()