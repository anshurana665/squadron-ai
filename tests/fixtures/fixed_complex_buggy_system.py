```python
import json
import logging
import threading
import time
import requests
import numpy as np
from typing import List, Dict, Optional

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_URL = "https://example.com/data.json"

class DataProcessor:
    def __init__(self):
        self.cache = None
        self.lock = threading.Lock()

    def fetch(self) -> Optional[Dict]:
        try:
            response = requests.get(DATA_URL, timeout=5)
            response.raise_for_status()
            return json.loads(response.text)
        except requests.RequestException as e:
            logger.error(f"Request failed: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Malformed JSON payload: {e}")
            return None

    def process(self, data: Dict) -> Optional[List[float]]:
        values = data.get("values")
        if values is None or not isinstance(values, list) or not all(isinstance(x, (int, float)) for x in values):
            logger.error("Invalid 'values' key or value")
            return None
        try:
            arr = np.array(values, dtype=np.float64)
            return list(arr * 2)
        except Exception as e:
            logger.error(f"Error processing data: {e}")
            return None

class Worker(threading.Thread):
    def __init__(self, processor: DataProcessor):
        super().__init__()
        self.processor = processor
        self.result = None

    def run(self):
        try:
            data = self.processor.fetch()
            if data is not None:
                self.result = self.processor.process(data)
        except Exception as e:
            logger.error(f"Error in worker thread: {e}")

def compute_average(values: List[float]) -> Optional[float]:
    if not values:
        logger.warning("Cannot calculate average of empty list")
        return None
    return sum(values) / len(values)

def save_results(results: List[float], path: str) -> None:
    try:
        with open(path, "w") as f:
            json.dump(results, f)
    except Exception as e:
        logger.error(f"Error saving results: {e}")

def main():
    processor = DataProcessor()
    worker = Worker(processor)
    
    worker.start()
    worker.join()

    if worker.result is not None:
        avg = compute_average(worker.result)
        if avg is not None:
            logger.info(f"Average: {avg}")
        save_results(worker.result, "output.json")
    else:
        logger.error("Worker result is None")

if __name__ == "__main__":
    main()
```