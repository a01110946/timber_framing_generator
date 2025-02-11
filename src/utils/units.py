# File: src/utils/units.py

def inches_to_mm(inches: float) -> float:
    return inches * 25.4

def mm_to_inches(mm: float) -> float:
    return mm / 25.4

def feet_to_inches(feet: float) -> float:
    return feet * 12.0

# def inches_to_feet(inches: float) -> float:
#    return inches / 12.0