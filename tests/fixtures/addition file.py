import logging
from typing import Union

# Configure logging properly
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s"
)

def add_numbers(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
    try:
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
            raise TypeError("Both inputs must be numbers")
        
        result = a + b
        return result

    except TypeError as e:
        logging.error(f"Error adding numbers: {e}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error adding numbers: {e}")
        raise


num1 = 10
num2 = 5

try:
    result = add_numbers(num1, num2)
    logging.info(f"The sum is: {result}")
except Exception as e:
    logging.error(f"Error: {e}")