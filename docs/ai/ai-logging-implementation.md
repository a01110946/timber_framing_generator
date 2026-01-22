# Understanding Python Logging Levels

Implementing proper logging is crucial for an extensive codebase like yours, especially with complex workflows involving Rhino, Grasshopper, and Revit. A well-structured logging system can make debugging significantly easier by providing visibility into different parts of your program execution.

## Standard Logging Levels in Python

Python's built-in `logging` module provides these standard levels (from highest to lowest severity):

1. **CRITICAL (50)** - For fatal errors that prevent program execution
2. **ERROR (40)** - For errors that allow the program to continue
3. **WARNING (30)** - For potential issues that don't stop execution
4. **INFO (20)** - For general information about program operation
5. **DEBUG (10)** - For detailed information useful during development
6. **NOTSET (0)** - The base logging level

TRACE isn't a built-in level in Python's logging module, but you can create a custom TRACE level (typically between DEBUG and NOTSET) for extremely detailed diagnostics.

## Basic Logging Setup

Here's how to set up a basic logging configuration:

```python
# File: src/timber_framing_generator/utils/logging_config.py

import logging
import os
from datetime import datetime

# Configure the root logger
logging.basicConfig(
    level=logging.INFO,  # Default level
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("timber_framing.log"),
        logging.StreamHandler()  # Console output
    ]
)

# Create a logger for a specific module
logger = logging.getLogger(__name__)

# Use different levels
logger.debug("Detailed information for diagnosing problems")
logger.info("Confirmation that things are working as expected")
logger.warning("An indication that something unexpected happened")
logger.error("The software has not been able to perform some function")
logger.critical("A serious error, program may be unable to continue")
```

## Adding a Custom TRACE Level

To add the TRACE level you mentioned:

```python
# File: src/timber_framing_generator/utils/logging_config.py

import logging

# Define a custom TRACE level (between DEBUG and NOTSET)
TRACE_LEVEL = 5  # Between DEBUG (10) and NOTSET (0)
logging.addLevelName(TRACE_LEVEL, "TRACE")

# Add a trace method to the logger class
def trace(self, message, *args, **kwargs):
    """
    Log a message with level TRACE.
    
    This level provides extremely detailed tracing information beyond DEBUG.
    """
    if self.isEnabledFor(TRACE_LEVEL):
        self._log(TRACE_LEVEL, message, args, **kwargs)

# Add the trace method to the Logger class
logging.Logger.trace = trace

# Now you can use it
logger = logging.getLogger(__name__)
logger.trace("Very detailed diagnostic information")
```

## Specialized Logger for Your Timber Framing Project

Here's a more comprehensive logging setup tailored to your Rhino/Grasshopper/Revit codebase:

```python
# File: src/timber_framing_generator/utils/logging_config.py

import logging
import os
import sys
from datetime import datetime

class TimberFramingLogger:
    """
    Configures logging for the timber framing generator with multiple levels.
    
    Supports:
    - Standard levels (CRITICAL, ERROR, WARNING, INFO, DEBUG)
    - Custom TRACE level for extremely detailed diagnostics
    - File and console output with different formats and levels
    - Module-specific logging configurations
    """
    
    # Define custom TRACE level
    TRACE_LEVEL = 5
    logging.addLevelName(TRACE_LEVEL, "TRACE")
    
    @staticmethod
    def _add_trace_method():
        """Add the TRACE method to the Logger class if not already present."""
        if not hasattr(logging.Logger, 'trace'):
            def trace(self, message, *args, **kwargs):
                if self.isEnabledFor(TimberFramingLogger.TRACE_LEVEL):
                    self._log(TimberFramingLogger.TRACE_LEVEL, message, args, **kwargs)
            logging.Logger.trace = trace
    
    @staticmethod
    def configure(debug_mode=False):
        """
        Configure the logging system for the entire application.
        
        Args:
            debug_mode: If True, sets DEBUG level for all loggers
        """
        # Add TRACE method to Logger class
        TimberFramingLogger._add_trace_method()
        
        # Create logs directory
        log_dir = "logs"
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
        console_formatter = logging.Formatter('%(levelname)s - %(message)s')
        console_handler.setFormatter(console_formatter)
        console_handler.setLevel(logging.INFO)  # Console shows less info by default
        root_logger.addHandler(console_handler)
        
        return log_file
    
    @staticmethod
    def get_logger(name, level=None):
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
```

## Using Logging in Your Code

Here's how you could implement logging in different parts of your codebase:

### 1. Main Entry Point

```python
# File: src/timber_framing_generator/grasshopper-main.py

import sys
from .utils.logging_config import TimberFramingLogger

# Initialize logging system
log_file = TimberFramingLogger.configure(debug_mode=run)
logger = TimberFramingLogger.get_logger(__name__)

def grasshopper_entry_point(walls, run=False):
    """Entry point for Grasshopper execution."""
    if not run:
        return None
    
    logger.info(f"Starting timber framing analysis for {len(walls)} walls")
    logger.info(f"Logging to: {log_file}")
    
    try:
        # Process walls
        all_walls_data = []
        for i, wall in enumerate(walls):
            try:
                logger.info(f"Processing wall {i+1}/{len(walls)} - ID: {wall.Id}")
                wall_data = extract_wall_data_from_revit(wall, doc)
                all_walls_data.append(wall_data)
                logger.debug(f"Wall {i+1} processed successfully")
            except Exception as e:
                logger.error(f"Error processing wall {i+1}: {str(e)}")
                # Trace-level includes traceback
                logger.trace(f"Traceback: {traceback.format_exc()}")
                
        # Create plate system
        logger.info("Creating plate systems for all walls")
        # ... rest of your code ...
        
        return all_walls_data
    except Exception as e:
        logger.critical(f"Critical error in main execution: {str(e)}")
        logger.error(traceback.format_exc())
        return None
```

### 2. Wall Data Extraction

```python
# File: src/timber_framing_generator/wall_data/revit_data_extractor.py

from typing import Dict, Union
from .utils.logging_config import TimberFramingLogger

logger = TimberFramingLogger.get_logger(__name__)

def extract_wall_data_from_revit(revit_wall, doc) -> Dict:
    """Extracts timber framing data from a Revit wall."""
    wall_id = revit_wall.Id.ToString()
    logger.info(f"Extracting data from wall ID: {wall_id}")
    
    try:
        # 1. Compute the wall base curve
        logger.debug("Computing wall base curve")
        wall_base_curve_rhino = get_wall_base_curve(revit_wall)
        logger.trace(f"Wall curve length: {wall_base_curve_rhino.GetLength()}")
        
        # 2. Compute wall base elevation
        logger.debug("Computing wall base elevation")
        wall_base_elevation = compute_wall_base_elevation(revit_wall, doc)
        logger.debug(f"Base elevation: {wall_base_elevation}")
        
        # ... additional extraction code ...
        
        # Get openings
        openings_data = []
        logger.debug("Processing wall openings")
        insert_ids = revit_wall.FindInserts(True, False, True, True)
        logger.debug(f"Found {len(insert_ids)} potential inserts")
        
        for insert_id in insert_ids:
            try:
                insert_element = revit_wall.Document.GetElement(insert_id)
                if isinstance(insert_element, DB.FamilyInstance):
                    # Process opening
                    # ...
                    logger.debug(f"Processed {opening_type} opening: W={opening_width_value}, H={opening_height_value}")
                    openings_data.append(opening_data)
            except Exception as e:
                logger.warning(f"Error processing insert {insert_id}: {str(e)}")
                logger.trace(traceback.format_exc())
                
        # 9. Build and return the wall data dictionary
        logger.info(f"Wall data extraction complete for {wall_id}: {len(openings_data)} openings, {len(cells_list)} cells")
        return wall_input_data_final
        
    except Exception as e:
        logger.error(f"Error extracting wall data: {str(e)}")
        logger.trace(traceback.format_exc())
        raise RuntimeError(f"Wall data extraction failed: {str(e)}") from e
```

### 3. Cell Decomposition

```python
# File: src/timber_framing_generator/cell_decomposition/cell_segmentation.py

from typing import Dict, List
from ..utils.logging_config import TimberFramingLogger

logger = TimberFramingLogger.get_logger(__name__)

def decompose_wall_to_cells(wall_length, wall_height, opening_data_list, base_plane):
    """Decomposes a wall into cells based on openings."""
    logger.info(f"Decomposing wall: L={wall_length}, H={wall_height}, Openings={len(opening_data_list)}")
    
    # 1. Create the wall boundary cell (covers the entire wall)
    logger.debug("Creating wall boundary cell")
    wall_boundary_cell_data = create_wall_boundary_cell_data(
        u_range=[0.0, wall_length], v_range=[0.0, wall_height]
    )
    
    # 2. For each opening, create an opening cell
    opening_cells_data = []
    logger.debug(f"Processing {len(opening_data_list)} openings")
    
    for i, opening_data in enumerate(opening_data_list):
        logger.debug(f"Creating opening cell {i+1}: {opening_data.get('opening_type')}")
        logger.trace(f"Opening data: {opening_data}")
        
        oc_data = create_opening_cell_data(
            u_range=[
                opening_data["start_u_coordinate"],
                opening_data["start_u_coordinate"] + opening_data["rough_width"],
            ],
            v_range=[
                opening_data["base_elevation_relative_to_wall_base"],
                opening_data["base_elevation_relative_to_wall_base"] + opening_data["rough_height"],
            ],
            opening_type=opening_data["opening_type"],
        )
        opening_cells_data.append(oc_data)
        
    # ... rest of your cell decomposition logic ...
    
    logger.info(f"Cell decomposition complete: {len(opening_cells_data)} opening cells, " + 
               f"{len(stud_cells_data)} stud cells, {len(sill_cripple_cells_data)} sill cripples, " +
               f"{len(header_cripple_cells_data)} header cripples")
    
    return cell_data_dict
```

## Logging Configuration for Specific Components

You can set different logging levels for different components of your system:

```python
# Configure logging for specific modules
def configure_component_logging():
    """Configure different logging levels for different system components."""
    components = {
        "wall_data": logging.INFO,
        "cell_decomposition": logging.DEBUG,
        "framing_elements": logging.DEBUG,
        "utils.geometry": logging.INFO,
        "revit_data_extractor": logging.DEBUG,
    }
    
    for component, level in components.items():
        comp_logger = logging.getLogger(f"timber_framing_generator.{component}")
        comp_logger.setLevel(level)
```

## Best Practices for Effective Logging

1. **Be consistent with logging levels:**
   - CRITICAL: Program cannot continue, immediate attention required
   - ERROR: Something failed, but program can continue
   - WARNING: Something unexpected, might cause problems
   - INFO: Normal operation milestones, major processing steps
   - DEBUG: Details useful during development and troubleshooting
   - TRACE: Extremely detailed output for specific code paths

2. **Include context in log messages:**
   - For wall processing: include wall ID, dimensions
   - For openings: include type, size, position
   - For operations: include input parameters, output summary

3. **Use structured logging:**
   - Include identifiers that you can search for
   - Format messages consistently for easier parsing

4. **Enable temporary debugging:**
   ```python
   def process_complex_geometry(geometry, debug=False):
       """Process complex geometry with optional debug logging."""
       temp_level = None
       if debug:
           temp_level = logger.level
           logger.setLevel(logging.DEBUG)
           
       # Process with detailed logging
       
       # Restore original level
       if debug:
           logger.setLevel(temp_level)
   ```

5. **Create a debugging decorator for tracing function calls:**
   ```python
   def trace_function(func):
       """Decorator that logs function entry and exit with parameters."""
       @functools.wraps(func)
       def wrapper(*args, **kwargs):
           logger = logging.getLogger(func.__module__)
           func_name = func.__name__
           logger.trace(f"ENTER {func_name} - Args: {args}, Kwargs: {kwargs}")
           try:
               result = func(*args, **kwargs)
               logger.trace(f"EXIT {func_name} - Result: {result}")
               return result
           except Exception as e:
               logger.trace(f"ERROR {func_name} - Exception: {str(e)}")
               raise
       return wrapper
   ```

By implementing these techniques, you'll have better visibility into your complex program flow, making debugging much more manageable even as your codebase grows.