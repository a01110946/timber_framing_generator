# API Documentation - Timber Framing Generator

## Introduction

The Timber Framing Generator provides a RESTful API that allows external systems to interact with the framing generation functionality. This API enables submitting wall data for analysis, retrieving analysis results, and managing wall analysis jobs.

This document provides comprehensive information about the API endpoints, request/response formats, authentication, error handling, and integration patterns.

## API Overview

### Base URL

The API is accessible at:

- Development: `http://localhost:8000`
- Production: `https://api.timber-framing-generator.example.com` (replace with actual production URL)

### API Versioning

The API follows semantic versioning. The current version is v1, which is included in the URL path:

```
https://api.timber-framing-generator.example.com/v1/
```

### Authentication

All API endpoints require authentication using an API key. The key must be included in the `X-API-Key` header:

```
X-API-Key: your-api-key-here
```

API keys can be obtained from the API administrator. Different API keys may have different permission levels and rate limits.

## Core Endpoints

### Wall Analysis

#### 1. Submit Wall for Analysis

Submit wall data for analysis and initiate the framing generation process.

**Endpoint:** `POST /walls/analyze`

**Request:**

```json
{
  "wall_type": "2x4 EXT",
  "wall_base_elevation": 0.0,
  "wall_top_elevation": 8.0,
  "wall_length": 10.0,
  "wall_height": 8.0,
  "is_exterior_wall": true,
  "openings": [
    {
      "opening_type": "window",
      "start_u_coordinate": 3.0,
      "rough_width": 2.0,
      "rough_height": 3.0,
      "base_elevation_relative_to_wall_base": 3.0
    }
  ]
}
```

**Response:**

```json
{
  "job_id": "950ee934-0e2d-44a0-9cb5-f4ae0304d1ce",
  "status": "pending",
  "created_at": "2025-03-11T02:08:02.711653",
  "updated_at": "2025-03-11T02:08:02.711655",
  "wall_data": {
    "wall_type": "2x4 EXT",
    "wall_base_elevation": 0.0,
    "wall_top_elevation": 8.0,
    "wall_length": 10.0,
    "wall_height": 8.0,
    "is_exterior_wall": true,
    "openings": [
      {
        "opening_type": "window",
        "start_u_coordinate": 3.0,
        "rough_width": 2.0,
        "rough_height": 3.0,
        "base_elevation_relative_to_wall_base": 3.0
      }
    ]
  },
  "result": null,
  "error": null
}
```

**Status Codes:**
- `200 OK`: Wall data accepted, analysis started
- `400 Bad Request`: Invalid wall data
- `401 Unauthorized`: Missing or invalid API key
- `500 Internal Server Error`: Server error

#### 2. Get Wall Analysis Status and Results

Retrieve the status and results of a wall analysis job.

**Endpoint:** `GET /walls/job/{job_id}`

**Path Parameters:**
- `job_id`: UUID of the analysis job

**Response:**

```json
{
  "job_id": "950ee934-0e2d-44a0-9cb5-f4ae0304d1ce",
  "status": "completed",
  "created_at": "2025-03-11T02:08:02.711653",
  "updated_at": "2025-03-11T02:08:05.943210",
  "wall_data": {
    "wall_type": "2x4 EXT",
    "wall_base_elevation": 0.0,
    "wall_top_elevation": 8.0,
    "wall_length": 10.0,
    "wall_height": 8.0,
    "is_exterior_wall": true,
    "openings": [
      {
        "opening_type": "window",
        "start_u_coordinate": 3.0,
        "rough_width": 2.0,
        "rough_height": 3.0,
        "base_elevation_relative_to_wall_base": 3.0
      }
    ]
  },
  "result": {
    "wall_data": {
      "wall_type": "2x4 EXT",
      "wall_base_elevation": 0.0,
      "wall_top_elevation": 8.0,
      "wall_length": 10.0,
      "wall_height": 8.0,
      "is_exterior_wall": true,
      "openings": [
        {
          "opening_type": "window",
          "start_u_coordinate": 3.0,
          "rough_width": 2.0,
          "rough_height": 3.0,
          "base_elevation_relative_to_wall_base": 3.0
        }
      ]
    },
    "base_plane": {
      "origin": {"x": 0, "y": 0, "z": 0},
      "x_axis": {"x": 1, "y": 0, "z": 0},
      "y_axis": {"x": 0, "y": 0, "z": 1},
      "z_axis": {"x": 0, "y": 1, "z": 0}
    },
    "cells": [
      {
        "cell_type": "WBC",
        "u_start": 0,
        "u_end": 10.0,
        "v_start": 0,
        "v_end": 8.0,
        "corner_points": [
          {"x": 0, "y": 0, "z": 0},
          {"x": 10.0, "y": 0, "z": 0},
          {"x": 10.0, "y": 0, "z": 8.0},
          {"x": 0, "y": 0, "z": 8.0}
        ]
      },
      {
        "cell_type": "OC",
        "opening_type": "window",
        "u_start": 3.0,
        "u_end": 5.0,
        "v_start": 3.0,
        "v_end": 6.0,
        "corner_points": [
          {"x": 3.0, "y": 0, "z": 3.0},
          {"x": 5.0, "y": 0, "z": 3.0},
          {"x": 5.0, "y": 0, "z": 6.0},
          {"x": 3.0, "y": 0, "z": 6.0}
        ]
      }
    ],
    "analysis_timestamp": "2025-03-11T02:08:05.943210Z"
  },
  "error": null
}
```

**Status Codes:**
- `200 OK`: Job found, status and any available results returned
- `400 Bad Request`: Invalid job ID format
- `401 Unauthorized`: Missing or invalid API key
- `404 Not Found`: Job not found
- `500 Internal Server Error`: Server error

#### 3. List Wall Analysis Jobs

List all wall analysis jobs with optional filtering and pagination.

**Endpoint:** `GET /walls/`

**Query Parameters:**
- `limit` (optional): Maximum number of jobs to return (default: 10, max: 100)
- `offset` (optional): Number of jobs to skip (default: 0)
- `status` (optional): Filter by job status ("pending", "processing", "completed", "failed")

**Response:**

```json
[
  {
    "job_id": "950ee934-0e2d-44a0-9cb5-f4ae0304d1ce",
    "status": "completed",
    "created_at": "2025-03-11T02:08:02.711653",
    "updated_at": "2025-03-11T02:08:05.943210",
    "wall_data": {
      "wall_type": "2x4 EXT",
      "wall_base_elevation": 0.0,
      "wall_top_elevation": 8.0,
      "wall_length": 10.0,
      "wall_height": 8.0,
      "is_exterior_wall": true,
      "openings": [
        {
          "opening_type": "window",
          "start_u_coordinate": 3.0,
          "rough_width": 2.0,
          "rough_height": 3.0,
          "base_elevation_relative_to_wall_base": 3.0
        }
      ]
    },
    "result": null,
    "error": null
  },
  {
    "job_id": "a2b3c4d5-e6f7-8g9h-0i1j-2k3l4m5n6o7p",
    "status": "pending",
    "created_at": "2025-03-11T02:10:15.123456",
    "updated_at": "2025-03-11T02:10:15.123456",
    "wall_data": {
      "wall_type": "2x6 EXT",
      "wall_base_elevation": 0.0,
      "wall_top_elevation": 10.0,
      "wall_length": 12.0,
      "wall_height": 10.0,
      "is_exterior_wall": true,
      "openings": []
    },
    "result": null,
    "error": null
  }
]
```

**Status Codes:**
- `200 OK`: Jobs list returned (may be empty)
- `401 Unauthorized`: Missing or invalid API key
- `500 Internal Server Error`: Server error

### Status and Health

#### 1. API Health Check

Check if the API service is operating normally.

**Endpoint:** `GET /health`

**Response:**

```json
{
  "status": "healthy",
  "message": "Timber Framing API is running"
}
```

**Status Codes:**
- `200 OK`: API is healthy
- `500 Internal Server Error`: API is experiencing issues

#### 2. Open Test Endpoint (No Auth Required)

Simple test endpoint that does not require authentication.

**Endpoint:** `GET /walls/open/open-test`

**Response:**

```json
{
  "status": "success",
  "message": "This endpoint doesn't require authentication"
}
```

**Status Codes:**
- `200 OK`: API is accessible

## Data Models

### WallDataInput

Input data model for wall analysis.

```json
{
  "wall_type": "string",           // Wall type code (e.g., "2x4 EXT")
  "wall_base_elevation": 0.0,      // Base elevation in feet
  "wall_top_elevation": 0.0,       // Top elevation in feet
  "wall_length": 0.0,              // Length in feet
  "wall_height": 0.0,              // Height in feet
  "is_exterior_wall": true,        // Whether the wall is exterior
  "openings": [                    // Optional array of openings
    {
      "opening_type": "string",    // "door" or "window"
      "start_u_coordinate": 0.0,   // Position along wall length
      "rough_width": 0.0,          // Width of rough opening
      "rough_height": 0.0,         // Height of rough opening
      "base_elevation_relative_to_wall_base": 0.0  // Height from wall base
    }
  ]
}
```

#### Validation Rules:
- `wall_type`: String min length 3, max length 50
- `wall_length`: Must be positive
- `wall_height`: Must be positive
- `wall_height`: Must match (wall_top_elevation - wall_base_elevation)
- `opening_type`: Must be "door" or "window"
- `rough_width`: Must be positive
- `rough_height`: Must be positive
- `start_u_coordinate + rough_width`: Must not exceed wall_length
- `base_elevation_relative_to_wall_base + rough_height`: Must not exceed wall_height
- Openings must not overlap with each other
- Doors should typically start at wall base (base_elevation_relative_to_wall_base ≈ 0)

### WallAnalysisJob

Model for wall analysis job data.

```json
{
  "job_id": "string",              // UUID for the job
  "status": "string",              // "pending", "processing", "completed", or "failed"
  "created_at": "string",          // ISO 8601 timestamp
  "updated_at": "string",          // ISO 8601 timestamp
  "wall_data": {                   // The input wall data (WallDataInput model)
    // See WallDataInput above
  },
  "result": {                      // Optional result data, present when status is "completed"
    "wall_data": {                 // Original wall data
      // See WallDataInput above
    },
    "base_plane": {                // Wall base plane
      "origin": {"x": 0, "y": 0, "z": 0},
      "x_axis": {"x": 0, "y": 0, "z": 0},
      "y_axis": {"x": 0, "y": 0, "z": 0},
      "z_axis": {"x": 0, "y": 0, "z": 0}
    },
    "cells": [                     // Array of cell data
      {
        "cell_type": "string",     // "WBC", "OC", "SC", "SCC", or "HCC"
        "u_start": 0.0,
        "u_end": 0.0,
        "v_start": 0.0,
        "v_end": 0.0,
        "corner_points": [
          {"x": 0, "y": 0, "z": 0},
          {"x": 0, "y": 0, "z": 0},
          {"x": 0, "y": 0, "z": 0},
          {"x": 0, "y": 0, "z": 0}
        ]
      }
    ],
    "analysis_timestamp": "string" // ISO 8601 timestamp
  },
  "error": "string"                // Optional error message, present when status is "failed"
}
```

## Error Handling

The API uses standard HTTP status codes and returns detailed error information in the response body.

### Error Response Format

```json
{
  "detail": "Error message describing the issue",
  "code": "error_code",
  "extra": {
    "field_errors": [
      {
        "loc": ["path", "to", "field"],
        "msg": "Error message for field",
        "type": "validation_error"
      }
    ],
    "additional_info": "Other relevant error information"
  }
}
```

### Common Error Codes

- `validation_error`: Input data failed validation
- `resource_not_found`: Requested resource not found
- `database_error`: Error interacting with the database
- `internal_server_error`: Unspecified server error

### Validation Errors

For validation errors, the response includes details about which fields failed validation:

```json
{
  "detail": "Validation error",
  "code": "validation_error",
  "extra": {
    "field_errors": [
      {
        "loc": ["body", "wall_height"],
        "msg": "Wall height must be positive",
        "type": "value_error"
      },
      {
        "loc": ["body", "openings", 0, "rough_width"],
        "msg": "Opening extends beyond wall length",
        "type": "value_error"
      }
    ]
  }
}
```

## Rate Limiting

The API implements rate limiting to ensure fair usage and system stability.

### Rate Limit Headers

Rate limit information is included in response headers:

```
X-Rate-Limit-Limit: 100       // Maximum requests per time window
X-Rate-Limit-Remaining: 99    // Remaining requests in current window
X-Rate-Limit-Reset: 1615477200 // Unix timestamp when limit resets
```

### Rate Limit Tiers

Different API keys may have different rate limit tiers:

| Tier | Requests per minute | Requests per day |
|------|---------------------|------------------|
| Basic | 30 | 1,000 |
| Standard | 60 | 5,000 |
| Professional | 120 | 20,000 |

### Rate Limit Exceeded Response

When rate limits are exceeded, the API returns:

```json
{
  "detail": "Rate limit exceeded",
  "code": "rate_limit_exceeded",
  "extra": {
    "rate_limit_reset": 1615477200
  }
}
```

With status code `429 Too Many Requests`.

## Advanced Usage

### Supabase Integration

The API integrates with Supabase for data storage. If you're using Supabase directly with your application, you can configure the following environment variables:

```
SUPABASE_URL=https://your-supabase-url.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key_here
```

### Processing Large Wall Sets

For processing multiple walls, submit each wall individually and track the jobs. This allows for better progress monitoring and error handling.

Example Python code for processing multiple walls:

```python
import requests
import time

API_KEY = "your-api-key"
API_URL = "https://api.timber-framing-generator.example.com/v1"

def process_walls(walls):
    """Process multiple walls and wait for results."""
    job_ids = []
    
    # Submit all walls
    for wall in walls:
        response = requests.post(
            f"{API_URL}/walls/analyze",
            json=wall,
            headers={"X-API-Key": API_KEY}
        )
        response.raise_for_status()
        job_ids.append(response.json()["job_id"])
    
    # Poll for results
    results = []
    for job_id in job_ids:
        while True:
            response = requests.get(
                f"{API_URL}/walls/job/{job_id}",
                headers={"X-API-Key": API_KEY}
            )
            response.raise_for_status()
            job = response.json()
            
            if job["status"] in ["completed", "failed"]:
                results.append(job)
                break
                
            time.sleep(1)  # Wait before polling again
    
    return results
```

### Long-Running Jobs

For walls with complex analysis requirements, jobs may take longer to complete. Implement exponential backoff in your polling logic:

```python
def get_job_with_backoff(job_id, max_attempts=10):
    """Get job status with exponential backoff."""
    attempt = 0
    while attempt < max_attempts:
        response = requests.get(
            f"{API_URL}/walls/job/{job_id}",
            headers={"X-API-Key": API_KEY}
        )
        response.raise_for_status()
        job = response.json()
        
        if job["status"] in ["completed", "failed"]:
            return job
            
        # Exponential backoff: wait longer between attempts
        wait_time = 2 ** attempt
        time.sleep(min(wait_time, 60))  # Cap at 60 seconds
        attempt += 1
        
    raise TimeoutError(f"Job {job_id} did not complete within the allowed time")
```

## Client Libraries

### Python Client

The Timber Framing Generator provides an official Python client library:

```python
from timber_api_client import TimberFramingClient

# Initialize client
client = TimberFramingClient(
    base_url="https://api.timber-framing-generator.example.com/v1",
    api_key="your-api-key-here"
)

# Check connection
success, message = client.check_connection()
print(f"Connection: {success}, Message: {message}")

# Analyze wall
wall_data = {
    "wall_type": "2x4 EXT",
    "wall_base_elevation": 0.0,
    "wall_top_elevation": 8.0,
    "wall_length": 10.0,
    "wall_height": 8.0,
    "is_exterior_wall": True,
    "openings": [
        {
            "opening_type": "window",
            "start_u_coordinate": 3.0,
            "rough_width": 2.0,
            "rough_height": 3.0,
            "base_elevation_relative_to_wall_base": 3.0
        }
    ]
}

# Analyze and wait for results
result = client.analyze_wall(wall_data, polling=True)

# List jobs
jobs = client.list_jobs(limit=5, status="completed")
for job in jobs:
    print(f"Job {job['job_id']}: {job['status']}")
```

### Javascript Client

A Javascript client is also available:

```javascript
import { TimberFramingClient } from 'timber-framing-api';

// Initialize client
const client = new TimberFramingClient({
  baseUrl: 'https://api.timber-framing-generator.example.com/v1',
  apiKey: 'your-api-key-here'
});

// Analyze wall
const wallData = {
  wall_type: '2x4 EXT',
  wall_base_elevation: 0.0,
  wall_top_elevation: 8.0,
  wall_length: 10.0,
  wall_height: 8.0,
  is_exterior_wall: true,
  openings: [
    {
      opening_type: 'window',
      start_u_coordinate: 3.0,
      rough_width: 2.0,
      rough_height: 3.0,
      base_elevation_relative_to_wall_base: 3.0
    }
  ]
};

// Submit for analysis
client.analyzeWall(wallData)
  .then(job => {
    console.log(`Job submitted: ${job.job_id}`);
    return client.pollJobUntilComplete(job.job_id);
  })
  .then(result => {
    console.log('Analysis complete!');
    console.log(`Cells: ${result.result.cells.length}`);
  })
  .catch(error => {
    console.error('Error:', error);
  });
```

## Practical Examples

### Example 1: Simple Wall with No Openings

```python
import requests

API_KEY = "your-api-key"
API_URL = "https://api.timber-framing-generator.example.com/v1"

# Create a simple wall with no openings
wall_data = {
    "wall_type": "2x4 EXT",
    "wall_base_elevation": 0.0,
    "wall_top_elevation": 8.0,
    "wall_length": 10.0,
    "wall_height": 8.0,
    "is_exterior_wall": True,
    "openings": []
}

# Submit for analysis
response = requests.post(
    f"{API_URL}/walls/analyze",
    json=wall_data,
    headers={"X-API-Key": API_KEY}
)
response.raise_for_status()
job = response.json()
job_id = job["job_id"]

# Poll for results
while True:
    response = requests.get(
        f"{API_URL}/walls/job/{job_id}",
        headers={"X-API-Key": API_KEY}
    )
    response.raise_for_status()
    job = response.json()
    
    if job["status"] == "completed":
        # Process completed job
        result = job["result"]
        # Count cells by type
        cell_types = {}
        for cell in result["cells"]:
            cell_type = cell["cell_type"]
            cell_types[cell_type] = cell_types.get(cell_type, 0) + 1
        
        print(f"Wall analysis complete!")
        print(f"Cell types: {cell_types}")
        break
    elif job["status"] == "failed":
        print(f"Job failed: {job.get('error', 'Unknown error')}")
        break
        
    # Wait before polling again
    time.sleep(1)
```

### Example 2: Wall with Door and Window

```python
import requests

# Create a wall with door and window
wall_data = {
    "wall_type": "2x6 EXT",
    "wall_base_elevation": 0.0,
    "wall_top_elevation": 10.0,
    "wall_length": 20.0,
    "wall_height": 10.0,
    "is_exterior_wall": True,
    "openings": [
        {
            "opening_type": "door",
            "start_u_coordinate": 3.0,
            "rough_width": 3.0,
            "rough_height": 7.0,
            "base_elevation_relative_to_wall_base": 0.0
        },
        {
            "opening_type": "window",
            "start_u_coordinate": 10.0,
            "rough_width": 4.0,
            "rough_height": 3.0,
            "base_elevation_relative_to_wall_base": 4.0
        }
    ]
}

# Submit and process as in Example 1
```

### Example 3: Error Handling

```python
import requests

# Invalid wall data with overlapping openings
wall_data = {
    "wall_type": "2x4 EXT",
    "wall_base_elevation": 0.0,
    "wall_top_elevation": 8.0,
    "wall_length": 10.0,
    "wall_height": 8.0,
    "is_exterior_wall": True,
    "openings": [
        {
            "opening_type": "window",
            "start_u_coordinate": 3.0,
            "rough_width": 4.0,
            "rough_height": 3.0,
            "base_elevation_relative_to_wall_base": 3.0
        },
        {
            "opening_type": "window",
            "start_u_coordinate": 5.0,
            "rough_width": 4.0,
            "rough_height": 3.0,
            "base_elevation_relative_to_wall_base": 3.0
        }
    ]
}

try:
    response = requests.post(
        f"{API_URL}/walls/analyze",
        json=wall_data,
        headers={"X-API-Key": API_KEY}
    )
    # Check for error responses
    response.raise_for_status()
    job = response.json()
    print(f"Job submitted: {job['job_id']}")
except requests.exceptions.HTTPError as e:
    if e.response.status_code == 400:
        # Validation error
        error_data = e.response.json()
        print(f"Validation error: {error_data['detail']}")
        # Print field errors if available
        if "extra" in error_data and "field_errors" in error_data["extra"]:
            for field_error in error_data["extra"]["field_errors"]:
                print(f"Field error: {'.'.join(field_error['loc'])}: {field_error['msg']}")
    elif e.response.status_code == 401:
        print("Authentication error: Invalid API key")
    elif e.response.status_code == 429:
        # Rate limit exceeded
        error_data = e.response.json()
        reset_time = error_data["extra"]["rate_limit_reset"]
        print(f"Rate limit exceeded. Try again after {reset_time}")
    else:
        print(f"HTTP error: {e}")
```

### Example 4: Python Client with Batch Processing

```python
from timber_api_client import TimberFramingClient
import concurrent.futures

# Initialize client
client = TimberFramingClient(
    base_url="https://api.timber-framing-generator.example.com/v1",
    api_key="your-api-key-here"
)

# Batch of walls to process
walls = [
    {
        "wall_type": "2x4 INT",
        "wall_base_elevation": 0.0,
        "wall_top_elevation": 8.0,
        "wall_length": 12.0,
        "wall_height": 8.0,
        "is_exterior_wall": False,
        "openings": []
    },
    {
        "wall_type": "2x6 EXT",
        "wall_base_elevation": 0.0,
        "wall_top_elevation": 10.0,
        "wall_length": 15.0,
        "wall_height": 10.0,
        "is_exterior_wall": True,
        "openings": [
            {
                "opening_type": "window",
                "start_u_coordinate": 5.0,
                "rough_width": 3.0,
                "rough_height": 4.0,
                "base_elevation_relative_to_wall_base": 3.0
            }
        ]
    }
]

# Submit all walls without polling
jobs = []
for wall in walls:
    job_data = client.analyze_wall(wall, polling=False)
    jobs.append(job_data)

print(f"Submitted {len(jobs)} walls for analysis")

# Process jobs in parallel
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
    # Create future for each job
    futures = {
        executor.submit(client.get_analysis_result, job["job_id"]): job["job_id"]
        for job in jobs
    }
    
    # Process results as they complete
    for future in concurrent.futures.as_completed(futures):
        job_id = futures[future]
        try:
            result = future.result()
            print(f"Job {job_id} completed with status: {result['status']}")
            if result["status"] == "completed":
                cell_count = len(result["result"]["cells"])
                print(f"Job {job_id} has {cell_count} cells")
        except Exception as e:
            print(f"Job {job_id} generated an exception: {str(e)}")
```

## Security Considerations

### API Key Management

- Store API keys securely as environment variables
- Rotate API keys periodically
- Use different keys for development and production
- Never expose API keys in client-side code

### Input Validation

- Always validate and sanitize API inputs
- Use the API's validation features as a second line of defense, not the primary validation

### HTTPS

- Always use HTTPS for API communication
- Verify SSL certificates in client code

## Troubleshooting

### Common Issues and Solutions

#### Issue: Authentication Failure

**Symptoms:**
- 401 Unauthorized responses
- "Invalid API key" error messages

**Solutions:**
- Verify API key is included in the X-API-Key header
- Check for leading/trailing whitespace in the API key
- Ensure you're using the correct API key for the environment

#### Issue: Timeout on Job Polling

**Symptoms:**
- Job remains in "pending" or "processing" state for a long time
- Client timeouts when waiting for results

**Solutions:**
- Implement exponential backoff for polling
- Set reasonable timeout limits for your application
- Check API status for system-wide issues

#### Issue: Validation Errors

**Symptoms:**
- 400 Bad Request responses
- Detailed validation errors in response

**Solutions:**
- Check the validation errors for specific fields
- Review wall data for inconsistencies (e.g., height doesn't match top - base)
- Ensure opening dimensions and positions are valid

### Getting Help

For assistance with API issues:

1. Check the API status at `https://status.timber-framing-generator.example.com`
2. Review the error response details for specific information
3. Contact support at `api-support@timber-framing-generator.example.com`

When reporting issues, please include:
- API endpoint being called
- Request data (with sensitive information removed)
- Full error response
- Time of the request (with timezone)

## Conclusion

The Timber Framing Generator API provides a powerful interface for automating timber framing analysis and generation. By following the guidelines and examples in this documentation, you can effectively integrate the API into your applications and workflows.

For the latest updates and additional information, refer to the online documentation at `https://docs.timber-framing-generator.example.com/api`.
