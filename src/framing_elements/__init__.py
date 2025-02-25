# src/framing_elements/__init__.py

from .plates import create_plates
from .studs import calculate_stud_locations, generate_stud
from .framing_generator import FramingGenerator  # Add this line

__all__ = [
    'create_plates',
    'calculate_stud_locations',
    'generate_stud',
    'FramingGenerator'
]