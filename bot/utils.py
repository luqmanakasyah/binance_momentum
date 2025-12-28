import math
from decimal import Decimal, ROUND_FLOOR, ROUND_DOWN

def round_step(value: float, step_size: float) -> float:
    """
    Rounds a value to the nearest step_size.
    Uses Decimal for precision.
    """
    if step_size == 0:
        return value
    
    # We use Decimal to avoid floating point issues
    d_value = Decimal(str(value))
    d_step = Decimal(str(step_size))
    
    # Calculate how many steps fit into the value
    steps = d_value / d_step
    
    # Floor to the nearest step to be safe (never round UP for qty/stops)
    rounded = math.floor(float(steps)) * d_step
    
    return float(rounded)

def format_precision(value: float, precision: int) -> float:
    """
    Formats a value to a specific number of decimal places.
    """
    return float(Decimal(str(value)).quantize(
        Decimal('1.' + '0' * precision), 
        rounding=ROUND_DOWN
    ))
