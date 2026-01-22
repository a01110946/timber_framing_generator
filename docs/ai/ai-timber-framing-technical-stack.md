# Timber Framing Generator Technical Stack

## Overview

The Timber Framing Generator is a Python-based tool that automates the generation of timber framing elements for construction models. It integrates with Building Information Modeling (BIM) software like Revit through Rhino.Inside.Revit, providing a powerful bridge between architectural design and structural framing. The system extracts wall data, analyzes components and openings, and generates appropriate timber framing solutions through a combination of web services and direct CAD/BIM integration.

## Core Backend Framework

### FastAPI
- High-performance Python web framework
- Provides automatic OpenAPI documentation
- Features built-in data validation
- Supports asynchronous request handling
- Used for building our RESTful API endpoints

### Pydantic
- Data validation and settings management
- Schema definition tool integrated with FastAPI
- Powers our data models with runtime type checking
- Handles conversion between JSON and Python objects
- Used for configuration management

### Uvicorn
- ASGI server implementation 
- Powers our API endpoints
- Provides high throughput
- Supports WebSocket connections
- Enables fast development with hot reloading

## Database and Storage

### PostgreSQL via Supabase
- Robust relational database
- Used for persisting wall data and analysis results
- Leverages Supabase for enhanced features
- Supports realtime subscriptions
- Includes built-in authentication

### Supabase SDK
- Python client for Supabase interactions
- Handles database queries and mutations
- Manages authentication and authorization
- Simplifies data access patterns
- Enables realtime data synchronization

## API and Authentication

### API Key Authentication
- Implemented through FastAPI middleware
- Secures API endpoints
- Supports service-to-service authentication
- Enables granular access control
- Simplifies integration with external systems

### Postman
- Used for API testing
- Supports documentation generation
- Enables development workflows
- Facilitates team collaboration
- Allows for environment-specific configuration

## Deployment Infrastructure

### Docker
- Containerization of application
- Ensures consistent environments
- Simplifies deployment process
- Facilitates scaling strategies
- Manages application dependencies

### Render
- Cloud platform for hosting
- Selected for simplicity and predictable pricing
- Supports Docker-based deployments
- Provides managed database options
- Offers continuous deployment from Git

### Environment Variables
- Used for configuration across environments
- Secures sensitive information
- Enables environment-specific settings
- Follows 12-factor app methodology
- Integrated with container orchestration

## Core CAD/BIM Integration

### Rhino 3D
- Foundation for 3D modeling capabilities
- Provides robust geometric operations
- Supports programmatic access
- Offers visualization capabilities
- Enables cross-platform compatibility

### Grasshopper
- Visual scripting platform within Rhino
- Supports parametric modeling workflows
- Facilitates algorithmic design
- Provides real-time feedback
- Enables component-based development

### Revit
- Building Information Modeling (BIM) software
- Source of wall data and building information
- Target for framing element generation
- Provides structured building components
- Enables comprehensive project integration

### Rhino.Inside.Revit
- Technology bridge connecting Rhino and Revit
- Allows Grasshopper operations inside Revit
- Enables geometric data exchange
- Facilitates Revit API access from Rhino
- Supports bidirectional workflow integration

## Development Tools

### Python 3.9+
- Primary programming language
- Extensive ecosystem of libraries
- Strong type annotation support
- Cross-platform compatibility
- Clear syntax for maintainability

### uv
- Modern Python package manager
- Replaces pip for dependency management
- Offers improved performance
- Provides better dependency resolution
- Supports reproducible builds

### Ruff
- Code formatter and linter
- Ensures consistent code style
- Identifies potential errors
- Improves code quality
- Integrates with development workflows

### Type hints/annotations
- Enhances IDE support
- Enables runtime validation
- Documents expected types
- Improves maintainability
- Supports static type checking

### Git
- Version control system
- Follows specific commit message standards
- Enables collaborative development
- Tracks code changes
- Integrates with CI/CD pipelines

## Supporting Libraries

### rhinoinside
- Python library for Rhino integration
- Enables headless Rhino operation
- Provides access to Rhino geometry
- Supports computational design workflows
- Facilitates cross-application integration

### rhino3dm
- Pure Python library for 3D geometry
- Operates without full Rhino installation
- Handles mesh operations
- Supports NURBS geometry
- Enables lightweight geometric operations

### Rhino Geometry (rg)
- Core geometry library
- Provides comprehensive geometric operations
- Supports computational design
- Handles complex 3D operations
- Enables precise geometry creation

### FastMCP
- Framework for implementing Model Context Protocol
- Enables AI agent integration
- Structures tool interactions
- Standardizes resource access
- Facilitates prompt engineering

### Revit API
- Provides programmatic access to Revit
- Enables element creation and modification
- Supports data extraction from BIM models
- Facilitates document management
- Offers comprehensive building element manipulation

### pyRevit
- IronPython framework for Revit customization
- Extends Revit's functionality
- Provides UI integration capabilities
- Enables script organization
- Facilitates Revit plugin development

## Testing Framework

### unittest/pytest
- Testing frameworks for Python code
- Enables unit testing
- Supports integration testing
- Provides test discovery
- Facilitates test-driven development

### httpx
- Modern HTTP client
- Used for testing API endpoints
- Supports async testing
- Facilitates comprehensive API validation

## AI Integration (MCP Components)

### Resources
- Read-only data access layer
- Provides wall data to AI agents
- Exposes framing configurations
- Standardizes data retrieval patterns
- Enables consistent information access

### Tools
- Action execution layer
- Generates framing elements
- Modifies existing structures
- Provides parameterized operations
- Enables AI-driven automation

### Prompts
- Standardized conversation templates
- Guides AI interactions
- Structures common workflows
- Ensures consistent outputs
- Improves AI assistance quality

## Custom Modules

### Wall Data Extraction
- Processes wall geometry from Revit
- Identifies openings and features
- Extracts dimensions and properties
- Handles coordinate transformation
- Prepares data for further analysis

### Cell Decomposition
- Algorithms for wall segmentation
- Divides walls into structural cells
- Identifies regions for framing elements
- Handles complex architectural scenarios
- Supports various opening configurations

### Framing Generation
- Creates parametric timber elements
- Applies framing rules and standards
- Generates studs, plates, headers, etc.
- Respects structural requirements
- Produces constructible solutions

### Coordinate Systems
- Manages UVW space for wall positioning
- Handles wall-relative coordinate transformations
- Provides consistent spatial reference
- Simplifies position calculations
- Ensures accurate element placement

## Best Practices

1. Always use proper type annotations for all functions and classes
2. Document code with comprehensive docstrings following the guidelines
3. Implement proper error handling with appropriate exception classes
4. Use the UVW coordinate system for wall-relative positioning
5. Maintain a clear separation between data extraction and geometry generation
6. Follow established naming conventions for consistency
7. Write tests for all critical functionality
8. Use environment variables for configuration, not hardcoded values
9. Follow the MCP guidelines for AI-compatible tools and resources
10. Ensure all Rhino/Revit operations gracefully handle failure cases

## Architecture Integration

The combination of FastAPI, Supabase, and Rhino integration creates a powerful foundation, allowing both standalone web services and deep integration with existing architectural design workflows. The architecture supports traditional usage through the API and AI-assisted workflows through the MCP implementation.
