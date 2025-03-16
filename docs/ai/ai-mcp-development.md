# MCP Server Development Guide for Timber Framing Generator

## Introduction

This guide provides a practical approach to implementing Model Context Protocol (MCP) servers for the Timber Framing Generator project. It covers how to develop servers that allow Claude and other AI assistants to interact with our Rhino, Grasshopper, and Revit environments through standardized Resources, Tools, and Prompts.

## MCP Architecture Overview

The Model Context Protocol (MCP) creates a standardized interface between AI models and software environments. For the Timber Framing Generator, we'll implement:

1. **Resources**: Read-only access to wall data, framing configurations, and model elements
2. **Tools**: Functions for generating and modifying framing elements
3. **Prompts**: Templates for common timber framing analysis and generation workflows

## Setting Up Your MCP Server Environment

### Prerequisites

- Python 3.9+
- FastMCP library
- Rhino.Inside.Revit (for Revit integration)
- Timber Framing Generator core library

### Installation

```bash
# Install dependencies using uv (our preferred package manager)
uv pip install fastmcp rhinoinside rhino3dm

# Install project in development mode
uv pip install -e .
```

### Basic Server Structure

Create a basic MCP server for the Timber Framing Generator:

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Script: timber_framing_mcp_server.py
Location: src/timber_framing_generator/mcp/server.py
Author: [Your Name]
Date Created: [Date]
Last Modified: [Date]

Description:
    MCP server implementation for the Timber Framing Generator.
    Provides Resources, Tools, and Prompts for AI interaction with 
    the timber framing system.

Usage:
    python -m timber_framing_generator.mcp.server

Dependencies:
    - fastmcp
    - rhinoinside
    - timber_framing_generator
"""

from typing import Dict, List, Optional, Any, Union
import os
import json

from fastmcp import FastMCP
from fastmcp.server.types import UserMessage, AssistantMessage

# Import Timber Framing Generator components
from timber_framing_generator.framing_elements import FramingGenerator
from timber_framing_generator.wall_data import extract_wall_data_from_revit
from timber_framing_generator.config.framing import FRAMING_PARAMS

# Initialize the MCP server
server = FastMCP("Timber Framing Generator")

# Your Resources, Tools, and Prompts will be defined below

if __name__ == "__main__":
    # Start the server
    server.run(host="0.0.0.0", port=8000)
```

## Implementing MCP Resources

Resources provide read-only access to data. They're perfect for retrieving wall information, framing configurations, and model elements.

### Wall Data Resource

```python
@server.resource("timber-framing://walls/{wall_id}")
def get_wall_data(wall_id: str) -> str:
    """
    Retrieve information about a specific wall.
    
    Args:
        wall_id: Unique identifier for the wall element
        
    Returns:
        Formatted text describing the wall and its properties
    """
    try:
        # Get the wall element from Revit (or mock data for testing)
        wall_element = get_wall_by_id(wall_id)
        
        # Extract wall data using our existing function
        wall_data = extract_wall_data_from_revit(wall_element, current_document())
        
        # Format the data as text for Claude
        result = f"Wall {wall_id} Information:\n\n"
        result += f"Type: {wall_data['wall_type']}\n"
        result += f"Length: {wall_data['wall_length']:.2f} feet\n"
        result += f"Height: {wall_data['wall_height']:.2f} feet\n"
        result += f"Base Elevation: {wall_data['wall_base_elevation']:.2f} feet\n"
        result += f"Top Elevation: {wall_data['wall_top_elevation']:.2f} feet\n"
        result += f"Exterior Wall: {'Yes' if wall_data['is_exterior_wall'] else 'No'}\n\n"
        
        # Add openings information
        result += f"Openings: {len(wall_data['openings'])}\n"
        for i, opening in enumerate(wall_data['openings'], 1):
            result += f"  Opening {i}: {opening['opening_type'].capitalize()}\n"
            result += f"    Position: {opening['start_u_coordinate']:.2f} feet from wall start\n"
            result += f"    Size: {opening['rough_width']:.2f} x {opening['rough_height']:.2f} feet\n"
            result += f"    Elevation: {opening['base_elevation_relative_to_wall_base']:.2f} feet from wall base\n"
        
        return result
    except Exception as e:
        return f"Error retrieving wall data: {str(e)}"
```

### Framing Parameters Resource

```python
@server.resource("timber-framing://config/framing-parameters")
def get_framing_parameters() -> str:
    """
    Retrieve current framing parameter configurations.
    
    Returns:
        Formatted text describing all framing parameters
    """
    result = "Current Framing Parameters:\n\n"
    
    # Convert parameters to appropriate units and format them
    for key, value in FRAMING_PARAMS.items():
        # Convert from internal units (feet) to inches for display
        if isinstance(value, (int, float)):
            display_value = value * 12  # Convert to inches
            result += f"{key}: {display_value:.2f} inches\n"
        else:
            result += f"{key}: {value}\n"
    
    return result
```

### Multiple Wall Resource

```python
@server.resource("timber-framing://walls")
def get_all_walls() -> str:
    """
    Retrieve a summary of all walls in the current document.
    
    Returns:
        Formatted text listing all walls and their basic properties
    """
    try:
        # Get all walls from the current document
        walls = get_all_walls_from_document()
        
        result = f"Found {len(walls)} walls in the current document:\n\n"
        
        # Create a summary table
        for i, wall in enumerate(walls, 1):
            wall_data = extract_wall_data_from_revit(wall, current_document())
            result += f"{i}. Wall ID: {wall.Id}\n"
            result += f"   Type: {wall_data['wall_type']}\n"
            result += f"   Length: {wall_data['wall_length']:.2f} feet\n"
            result += f"   Height: {wall_data['wall_height']:.2f} feet\n"
            result += f"   Openings: {len(wall_data['openings'])}\n"
            result += "\n"
        
        return result
    except Exception as e:
        return f"Error retrieving walls: {str(e)}"
```

## Implementing MCP Tools

Tools allow Claude to perform actions in your system, like generating framing elements or modifying parameters.

### Generate Framing Tool

```python
@server.tool()
def generate_wall_framing(
    wall_id: str,
    framing_config: Dict[str, Any] = None
) -> str:
    """
    Generate timber framing for a specific wall.
    
    Args:
        wall_id: Unique identifier for the wall element
        framing_config: Optional configuration parameters to override defaults
            - representation_type: "structural" or "schematic"
            - bottom_plate_layers: Number of bottom plate layers (1 or 2)
            - top_plate_layers: Number of top plate layers (1 or 2)
            - stud_spacing: Spacing between studs in inches
        
    Returns:
        Status message about the generated framing
    """
    try:
        # Get the wall element
        wall_element = get_wall_by_id(wall_id)
        
        # Extract wall data
        wall_data = extract_wall_data_from_revit(wall_element, current_document())
        
        # Set default configuration if none provided
        if framing_config is None:
            framing_config = {
                "representation_type": "schematic",
                "bottom_plate_layers": 1,
                "top_plate_layers": 2
            }
        
        # Convert any inch values to feet for internal processing
        if "stud_spacing" in framing_config:
            framing_config["stud_spacing"] = framing_config["stud_spacing"] / 12.0
        
        # Create framing generator
        generator = FramingGenerator(wall_data, framing_config)
        
        # Generate framing
        framing_result = generator.generate_framing()
        
        # Summarize the results
        result = f"Successfully generated framing for Wall {wall_id}:\n\n"
        result += f"- Bottom plates: {len(framing_result['bottom_plates'])}\n"
        result += f"- Top plates: {len(framing_result['top_plates'])}\n"
        result += f"- King studs: {len(framing_result['king_studs'])}\n"
        result += f"- Headers: {len(framing_result['headers'])}\n"
        result += f"- Sills: {len(framing_result['sills'])}\n"
        result += f"- Studs: {len(framing_result.get('studs', []))}\n"
        
        # Add visualization data for Rhino
        # This creates visualization data that can be displayed in Rhino
        visualization_data = create_visualization_data(framing_result)
        store_visualization_data(wall_id, visualization_data)
        
        return result
    except Exception as e:
        return f"Error generating framing: {str(e)}"
```

### Update Framing Parameters Tool

```python
@server.tool()
def update_framing_parameter(parameter_name: str, value: Union[float, int, str, bool]) -> str:
    """
    Update a specific framing parameter.
    
    Args:
        parameter_name: Name of the parameter to update
        value: New value for the parameter
        
    Returns:
        Status message about the parameter update
    """
    try:
        # Validate parameter name
        if parameter_name not in FRAMING_PARAMS:
            return f"Error: Parameter '{parameter_name}' not found in FRAMING_PARAMS"
        
        # Get the current value for comparison
        current_value = FRAMING_PARAMS[parameter_name]
        
        # Convert numeric values to feet if they represent dimensions
        # This assumes all dimensional parameters use feet internally
        if isinstance(value, (int, float)) and isinstance(current_value, (int, float)):
            # If the value is substantially larger than the current value,
            # it might be in inches and need conversion to feet
            if value > current_value * 10:
                value = value / 12.0
        
        # Update the parameter
        FRAMING_PARAMS[parameter_name] = value
        
        # Format the response
        if isinstance(value, (int, float)) and isinstance(current_value, (int, float)):
            # Convert to inches for display
            display_value = value * 12
            display_current = current_value * 12
            return f"Updated {parameter_name} from {display_current:.2f} inches to {display_value:.2f} inches"
        else:
            return f"Updated {parameter_name} from {current_value} to {value}"
    except Exception as e:
        return f"Error updating parameter: {str(e)}"
```

### Export Framing to Revit Tool

```python
@server.tool()
def export_framing_to_revit(wall_id: str) -> str:
    """
    Export generated framing elements to Revit as family instances.
    
    Args:
        wall_id: Wall ID for which framing should be exported
        
    Returns:
        Status message about the export operation
    """
    try:
        # Check if framing has been generated for this wall
        if not has_generated_framing(wall_id):
            return f"No framing data found for Wall {wall_id}. Please generate framing first."
        
        # Get the framing data
        framing_data = get_framing_data(wall_id)
        
        # Get the wall element
        wall_element = get_wall_by_id(wall_id)
        
        # Initialize counters
        elements_created = {
            "plates": 0,
            "studs": 0,
            "headers": 0,
            "sills": 0,
            "other": 0
        }
        
        # Export to Revit using the export_geometry_to_revit function
        for element_type, elements in framing_data.items():
            if element_type in ["bottom_plates", "top_plates"]:
                for plate in elements:
                    export_geometry_to_revit(plate, element_type, wall_element)
                    elements_created["plates"] += 1
            elif element_type in ["king_studs", "studs"]:
                for stud in elements:
                    export_geometry_to_revit(stud, element_type, wall_element)
                    elements_created["studs"] += 1
            elif element_type == "headers":
                for header in elements:
                    export_geometry_to_revit(header, element_type, wall_element)
                    elements_created["headers"] += 1
            elif element_type == "sills":
                for sill in elements:
                    export_geometry_to_revit(sill, element_type, wall_element)
                    elements_created["sills"] += 1
            else:
                for element in elements:
                    export_geometry_to_revit(element, element_type, wall_element)
                    elements_created["other"] += 1
        
        # Create result message
        result = f"Successfully exported framing elements to Revit for Wall {wall_id}:\n\n"
        result += f"- Plates: {elements_created['plates']}\n"
        result += f"- Studs: {elements_created['studs']}\n"
        result += f"- Headers: {elements_created['headers']}\n"
        result += f"- Sills: {elements_created['sills']}\n"
        result += f"- Other elements: {elements_created['other']}\n"
        
        return result
    except Exception as e:
        return f"Error exporting framing to Revit: {str(e)}"
```

## Implementing MCP Prompts

Prompts provide templated conversations for specific workflows.

### Framing Analysis Prompt

```python
@server.prompt()
def framing_analysis(wall_id: str) -> List[Union[UserMessage, AssistantMessage]]:
    """
    Generate a structured conversation for analyzing timber framing of a wall.
    
    Args:
        wall_id: Unique identifier for the wall to analyze
        
    Returns:
        A list of messages forming a conversation template
    """
    return [
        UserMessage(f"""
        Please analyze the timber framing for Wall {wall_id}. I'd like you to:

        1. Review the wall data and dimensions
        2. Analyze the framing requirements based on openings
        3. Suggest optimal framing configurations
        4. Identify any potential issues or optimization opportunities
        """),
        
        AssistantMessage("""
        I'll analyze the timber framing for this wall. Let me start by reviewing the wall data.

        I'll examine:
        1. The wall dimensions and type
        2. Any openings and their impact on framing
        3. The current framing parameters
        4. Optimization possibilities

        First, let me get the wall data...
        """)
    ]
```

### Framing Generation Prompt

```python
@server.prompt()
def generate_framing_workflow(
    wall_id: str, 
    plate_layers: int = 2,
    stud_spacing: float = 16.0
) -> List[Union[UserMessage, AssistantMessage]]:
    """
    Generate a structured conversation for creating timber framing.
    
    Args:
        wall_id: Unique identifier for the wall
        plate_layers: Number of top plate layers (1 or 2)
        stud_spacing: Spacing between studs in inches
        
    Returns:
        A list of messages forming a conversation template
    """
    return [
        UserMessage(f"""
        I need to generate timber framing for Wall {wall_id}. Please use these specifications:

        - Top plate layers: {plate_layers}
        - Stud spacing: {stud_spacing} inches

        Please walk me through the process, generate the framing, and explain what's being created.
        """),
        
        AssistantMessage("""
        I'll help you generate the timber framing for this wall with your specifications. First, let me review the wall data to understand what we're working with.
        """),
        
        UserMessage("""
        After generating the framing, can you explain how the openings are handled in the framing system?
        """),
        
        AssistantMessage("""
        I'll definitely explain how openings are handled in the framing. After generating the framing, I'll cover:

        1. How king studs and trimmers support the openings
        2. How headers transfer loads above openings
        3. How sills are implemented for windows
        4. How cripple studs are positioned
        """)
    ]
```

## Advanced MCP Server Configuration

### Integrating with Rhino.Inside.Revit

For a production server that connects to Revit:

```python
import rhinoinside
rhinoinside.load()
import Rhino.Geometry as rg
from RhinoInside.Revit import Revit
import Autodesk.Revit.DB as DB

# Initialize Revit API access
def initialize_revit():
    """Set up Revit API access."""
    try:
        # Get current Revit application and document
        app = Revit.ActiveUIApplication.Application
        doc = Revit.ActiveDBDocument
        
        print(f"Connected to Revit: {app.VersionName}")
        print(f"Current document: {doc.Title}")
        
        return True
    except Exception as e:
        print(f"Failed to initialize Revit: {str(e)}")
        return False

# Call this before starting the MCP server
if __name__ == "__main__":
    if initialize_revit():
        # Start the server
        server.run(host="0.0.0.0", port=8000)
    else:
        print("Failed to initialize Revit connection. MCP server not started.")
```

### Handling File Resources

For accessing and processing Rhino or Revit files:

```python
@server.resource("timber-framing://files/{file_path}")
def get_file_information(file_path: str) -> str:
    """
    Retrieve information about a Rhino or Revit file.
    
    Args:
        file_path: Path to the file, relative to the server's file root
        
    Returns:
        Formatted text with file information
    """
    try:
        # Resolve the file path
        full_path = os.path.join(FILE_ROOT, file_path)
        
        if not os.path.exists(full_path):
            return f"Error: File not found: {file_path}"
        
        # Check file type
        if file_path.lower().endswith(".rvt"):
            # Revit file
            return get_revit_file_info(full_path)
        elif file_path.lower().endswith(".3dm"):
            # Rhino file
            return get_rhino_file_info(full_path)
        else:
            return f"Unsupported file type: {os.path.splitext(file_path)[1]}"
    except Exception as e:
        return f"Error accessing file: {str(e)}"
```

### Authentication and Authorization

For securing your MCP server:

```python
# Add authentication middleware
from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

API_KEYS = {
    "user1": "key1",
    "user2": "key2"
}

api_key_header = APIKeyHeader(name="X-API-Key")

def verify_api_key(api_key: str = Depends(api_key_header)):
    """Verify API key for authenticated access."""
    for username, key in API_KEYS.items():
        if api_key == key:
            return username
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API Key"
    )

# Then use this in your server initialization
server = FastMCP(
    "Timber Framing Generator",
    dependencies=[Depends(verify_api_key)]
)
```

## Best Practices for MCP Server Development

### Resource Design Guidelines

1. **Clear resource naming**:
   - Use intuitive URI patterns (`timber-framing://walls/{wall_id}`)
   - Be consistent with pluralization and case
   - Consider namespacing for different subsystems

2. **Comprehensive error handling**:
   - Validate all parameters
   - Catch and handle exceptions gracefully
   - Return clear error messages

3. **Performance considerations**:
   - Cache frequently accessed data when appropriate
   - Implement timeouts for long-running operations
   - Consider pagination for large data sets

### Tool Design Guidelines

1. **Input validation**:
   - Validate all parameters before use
   - Provide clear error messages for invalid inputs
   - Use appropriate type hints for parameters

2. **Operation safety**:
   - Use transactions for Revit operations
   - Implement rollback capability for failures
   - Limit scope of modifications

3. **Clear feedback**:
   - Return detailed status messages
   - Include summary of changes made
   - Provide guidance on next steps

### Prompt Design Guidelines

1. **Workflow structure**:
   - Break complex tasks into logical steps
   - Include follow-up questions for common scenarios
   - Provide clear starting points for the assistant

2. **Context provision**:
   - Include relevant context in the initial messages
   - Reference resources that should be accessed
   - Anticipate needed information

3. **User guidance**:
   - Clearly explain what users should provide
   - Include examples of expected inputs
   - Offer options for different paths

## Testing Your MCP Server

### Unit Testing Resources

```python
def test_get_wall_data():
    """Test the wall data resource."""
    # Set up test environment
    setup_test_environment()
    
    # Create a mock wall
    wall_id = create_mock_wall()
    
    # Call the resource function directly
    result = get_wall_data(wall_id)
    
    # Validate the result
    assert "Wall" in result
    assert "Type:" in result
    assert "Length:" in result
    assert "Height:" in result
    
    # Verify the content
    assert str(wall_id) in result
    assert "feet" in result
```

### Integration Testing

```python
def test_full_workflow():
    """Test a complete workflow with resources and tools."""
    # Set up test environment
    setup_test_environment()
    
    # Create a mock wall
    wall_id = create_mock_wall()
    
    # Get wall data via resource
    wall_data_response = get_wall_data(wall_id)
    assert "Wall" in wall_data_response
    
    # Generate framing via tool
    framing_config = {
        "representation_type": "schematic",
        "bottom_plate_layers": 1,
        "top_plate_layers": 2
    }
    framing_response = generate_wall_framing(wall_id, framing_config)
    assert "Successfully generated framing" in framing_response
    
    # Export to Revit via tool
    export_response = export_framing_to_revit(wall_id)
    assert "Successfully exported" in export_response
```

### Mock Data for Testing

```python
def create_mock_wall():
    """Create a mock wall for testing."""
    # Create a unique ID
    wall_id = f"mock-{uuid.uuid4()}"
    
    # Create a dictionary with test wall data
    wall_data = {
        "wall_id": wall_id,
        "wall_type": "2x4 EXT",
        "wall_length": 10.0,
        "wall_height": 8.0,
        "wall_base_elevation": 0.0,
        "wall_top_elevation": 8.0,
        "is_exterior_wall": True,
        "openings": [
            {
                "opening_type": "window",
                "start_u_coordinate": 3.0,
                "rough_width": 3.0,
                "rough_height": 4.0,
                "base_elevation_relative_to_wall_base": 3.0
            }
        ]
    }
    
    # Store in the test database
    mock_database[wall_id] = wall_data
    
    return wall_id
```

## Deployment Considerations

### Docker Deployment

Docker simplifies deployment of your MCP server:

```dockerfile
FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project code
COPY . .

# Expose port for MCP server
EXPOSE 8000

# Run the server
CMD ["python", "-m", "timber_framing_generator.mcp.server"]
```

### Environment Variables

Use environment variables for configuration:

```python
import os

# Load configuration from environment variables
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
PORT = int(os.environ.get("PORT", "8000"))
HOST = os.environ.get("HOST", "0.0.0.0")
FILE_ROOT = os.environ.get("FILE_ROOT", "./files")

# Configure server based on environment
server_config = {
    "debug": DEBUG,
    "file_root": FILE_ROOT
}

server = FastMCP("Timber Framing Generator", **server_config)

if __name__ == "__main__":
    server.run(host=HOST, port=PORT)
```

## Conclusion

Implementing an MCP server for the Timber Framing Generator provides a powerful way to enable AI interactions with your architectural and engineering tools. By following this guide, you can create a robust server that exposes Resources for data access, Tools for actions, and Prompts for guided workflows.

Remember to maintain clear separation between read-only Resources and action-oriented Tools, provide comprehensive documentation, and implement thorough testing. With a well-designed MCP server, you can create rich, interactive experiences that combine Claude's intelligence with your specialized timber framing functionality.
