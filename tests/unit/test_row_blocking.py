# File: tests/unit/test_row_blocking.py

"""
Unit tests for row blocking generation.

Tests the functionality of the BlockingParameters and RowBlockingGenerator classes.
"""

import pytest
import math
import Rhino.Geometry as rg
from typing import Dict, List, Any

from src.timber_framing_generator.framing_elements.blocking_parameters import (
    BlockingParameters,
    BlockingLayerConfig
)
from src.timber_framing_generator.framing_elements.row_blocking import RowBlockingGenerator
from src.timber_framing_generator.config.framing import BlockingPattern, FRAMING_PARAMS


class TestBlockingParameters:
    """Test cases for the BlockingParameters class."""

    def test_default_parameters(self) -> None:
        """Test that default parameters are properly initialized."""
        params = BlockingParameters()
        
        assert params.include_blocking == FRAMING_PARAMS.get("include_blocking", True)
        assert params.block_spacing == FRAMING_PARAMS.get("block_spacing", 48.0/12.0)
        assert params.first_block_height == FRAMING_PARAMS.get("first_block_height", 24.0/12.0)
        assert params.layers == []
    
    def test_calculate_block_heights_defaults(self) -> None:
        """Test block height calculation with default parameters."""
        params = BlockingParameters()
        wall_height = 8.0  # 8 feet
        
        heights = params.calculate_block_heights(wall_height)
        
        # With default configuration (first at 2', spacing 4'),
        # we should get heights at approximately 2' and 6'
        assert len(heights) == 1
        assert math.isclose(heights[0], 2.0, abs_tol=0.01)
    
    def test_calculate_block_heights_custom(self) -> None:
        """Test block height calculation with custom parameters."""
        params = BlockingParameters(
            first_block_height=1.0,  # 1 foot
            block_spacing=2.0,       # 2 feet
        )
        wall_height = 8.0  # 8 feet
        
        heights = params.calculate_block_heights(wall_height)
        
        # With custom configuration (first at 1', spacing 2')
        # we should get heights at 1', 3', 5'
        assert len(heights) == 3
        assert math.isclose(heights[0], 1.0, abs_tol=0.01)
        assert math.isclose(heights[1], 3.0, abs_tol=0.01)
        assert math.isclose(heights[2], 5.0, abs_tol=0.01)
    
    def test_calculate_block_heights_custom_layers(self) -> None:
        """Test block height calculation with custom layer configuration."""
        custom_layers = [
            BlockingLayerConfig(height=1.5),
            BlockingLayerConfig(height=4.0),
            BlockingLayerConfig(height=6.5),
        ]
        params = BlockingParameters(layers=custom_layers)
        wall_height = 8.0  # 8 feet
        
        heights = params.calculate_block_heights(wall_height)
        
        # Should use the custom layer heights instead of calculating
        assert len(heights) == 3
        assert math.isclose(heights[0], 1.5, abs_tol=0.01)
        assert math.isclose(heights[1], 4.0, abs_tol=0.01)
        assert math.isclose(heights[2], 6.5, abs_tol=0.01)
    
    def test_get_block_profile(self) -> None:
        """Test profile selection logic."""
        # Default (use wall profile)
        params = BlockingParameters()
        assert params.get_block_profile("2x4") == "2x4"
        
        # Custom override
        params = BlockingParameters(profile="2x6")
        assert params.get_block_profile("2x4") == "2x6"


class TestRowBlockingGenerator:
    """Test cases for the RowBlockingGenerator class."""
    
    @pytest.fixture
    def wall_data(self) -> Dict[str, Any]:
        """Create a simple wall data fixture."""
        return {
            "wall_type": "2x4",
            "height": 8.0,
            "length": 10.0,
            "base_plane": rg.Plane.WorldXY,
        }
    
    @pytest.fixture
    def simple_studs(self) -> List[rg.Brep]:
        """Create a simple list of stud breps for testing."""
        studs = []
        
        # Create 4 studs at 0', 2', 6', and 9' along wall
        positions = [0.0, 2.0, 6.0, 9.0]
        for pos in positions:
            # Create a simple box to represent a stud
            # 1.5" wide, 3.5" deep, 8' tall at the specified position
            stud_width = 1.5/12.0
            stud_depth = 3.5/12.0
            stud_height = 8.0
            
            origin = rg.Point3d(pos, 0, 0)
            x_dir = rg.Vector3d(stud_width, 0, 0)
            y_dir = rg.Vector3d(0, stud_depth, 0) 
            z_dir = rg.Vector3d(0, 0, stud_height)
            
            box = rg.Box(rg.Plane(origin, rg.Vector3d.XAxis, rg.Vector3d.YAxis), 
                         x_dir, y_dir, z_dir)
            studs.append(box.ToBrep())
        
        return studs
    
    def test_extract_stud_positions(self, wall_data: Dict[str, Any], simple_studs: List[rg.Brep]) -> None:
        """Test extraction of stud positions."""
        generator = RowBlockingGenerator(wall_data, simple_studs)
        
        # Check that stud positions were extracted correctly
        assert len(generator.stud_positions) == 4
        assert math.isclose(generator.stud_positions[0], 0.0, abs_tol=0.01)
        assert math.isclose(generator.stud_positions[1], 2.0, abs_tol=0.01)
        assert math.isclose(generator.stud_positions[2], 6.0, abs_tol=0.01)
        assert math.isclose(generator.stud_positions[3], 9.0, abs_tol=0.01)
    
    def test_generate_blocking(self, wall_data: Dict[str, Any], simple_studs: List[rg.Brep]) -> None:
        """Test generation of blocking elements."""
        # Custom parameters for predictable results
        params = BlockingParameters(
            include_blocking=True,
            first_block_height=2.0,
            block_spacing=4.0,
        )
        
        generator = RowBlockingGenerator(wall_data, simple_studs, blocking_params=params)
        blocks = generator.generate_blocking()
        
        # Should create blocks between studs at position 1-2, 2-3, 3-4
        # at the specified height
        assert len(blocks) == 3
    
    def test_blocking_disabled(self, wall_data: Dict[str, Any], simple_studs: List[rg.Brep]) -> None:
        """Test that no blocks are generated when disabled."""
        params = BlockingParameters(include_blocking=False)
        
        generator = RowBlockingGenerator(wall_data, simple_studs, blocking_params=params)
        blocks = generator.generate_blocking()
        
        # Should not create any blocks
        assert len(blocks) == 0
