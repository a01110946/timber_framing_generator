# api/utils/errors.py
from fastapi import HTTPException, status
from typing import Optional, Dict, Any, Type
import logging
import traceback

logger = logging.getLogger("timber_framing.api")

class APIError(Exception):
    """
    Base class for API-specific exceptions.
    
    This class extends the standard Exception to include HTTP status codes
    and structured error details for API responses.
    """
    def __init__(
        self, 
        status_code: int, 
        detail: str, 
        internal_code: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the APIError with HTTP status and details.
        
        Args:
            status_code: HTTP status code to return
            detail: Human-readable error message
            internal_code: Optional internal error code for client reference
            extra: Optional additional error context
        """
        self.status_code = status_code
        self.detail = detail
        self.internal_code = internal_code
        self.extra = extra or {}
        super().__init__(detail)
    
    def to_http_exception(self) -> HTTPException:
        """
        Convert to FastAPI HTTPException.
        
        Returns:
            HTTPException with appropriate status code and details
        """
        error_response = {
            "detail": self.detail,
        }
        
        if self.internal_code:
            error_response["code"] = self.internal_code
            
        if self.extra:
            error_response["extra"] = self.extra
            
        return HTTPException(
            status_code=self.status_code,
            detail=error_response
        )

class ResourceNotFoundError(APIError):
    """Error raised when a requested resource doesn't exist."""
    def __init__(
        self, 
        resource_type: str, 
        resource_id: str,
        extra: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize with resource details.
        
        Args:
            resource_type: Type of resource (e.g., "job", "wall")
            resource_id: ID of the missing resource
            extra: Optional additional context
        """
        detail = f"{resource_type.capitalize()} with ID '{resource_id}' not found"
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
            internal_code="resource_not_found",
            extra=extra
        )

class DatabaseError(APIError):
    """Error raised when database operations fail."""
    def __init__(
        self,
        operation: str,
        detail: str,
        extra: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize with operation details.
        
        Args:
            operation: Database operation that failed
            detail: Error details
            extra: Optional additional context
        """
        message = f"Database error during {operation}: {detail}"
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=message,
            internal_code="database_error",
            extra=extra
        )

class ValidationError(APIError):
    """Error raised for input validation failures."""
    def __init__(
        self,
        detail: str,
        field: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize with validation details.
        
        Args:
            detail: Validation error details
            field: Optional field that failed validation
            extra: Optional additional context
        """
        message = f"Validation error"
        if field:
            message += f" for field '{field}'"
        message += f": {detail}"
        
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
            internal_code="validation_error",
            extra=extra
        )

def handle_exception(e: Exception, resource_type: str = "resource", resource_id: Optional[str] = None) -> HTTPException:
    """
    Handle exceptions and convert to appropriate HTTPExceptions.
    
    This utility function processes various exception types and converts them
    to consistent HTTP responses with appropriate status codes.
    
    Args:
        e: The exception to handle
        resource_type: Type of resource being accessed (for context)
        resource_id: ID of the resource (for context)
        
    Returns:
        HTTPException with appropriate status code and details
    """
    # If it's already an APIError, just convert it
    if isinstance(e, APIError):
        return e.to_http_exception()
        
    # If it's already an HTTPException, return it
    if isinstance(e, HTTPException):
        return e
        
    # Log the full error
    error_detail = traceback.format_exc()
    logger.error(f"Unhandled exception: {str(e)}\n{error_detail}")
    
    # Return a generic 500 error
    error_response = {
        "detail": f"An unexpected error occurred: {str(e)}",
        "code": "internal_server_error"
    }
    
    if resource_id:
        error_response["resource_id"] = resource_id
        
    if resource_type:
        error_response["resource_type"] = resource_type
        
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=error_response
    )