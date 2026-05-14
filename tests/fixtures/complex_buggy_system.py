
# complex_buggy_system.py
# Intentionally complex script with multiple logical, runtime, and design bugs

import json
import threading
import time
import requests
import numpy as np
from typing import List, Dict

DATA_URL = "https://example.com/data.json"

class DataProcessor:
    def __init__(self):
        self.cache = None

    def fetch(self) -> Dict:
        # BUG 1: No timeout, no status check
        response = requests.get(DATA_URL)
        return json.loads(response.text)  # May crash if not JSON

    def process(self, data: Dict) -> List[float]:
        # BUG 2: Assumes 'values' key exists and is numeric
        values = data["values"]
        arr = np.array(values, dtype=np.uint8)  # BUG 3: Possible overflow
        return list(arr * 2)

class Worker(threading.Thread):
    def __init__(self, processor: DataProcessor):
        super().__init__()
        self.processor = processor
        self.result = None

    def run(self):
        # BUG 4: No exception handling inside thread
        data = self.processor.fetch()
        self.result = self.processor.process(data)

def compute_average(values: List[float]) -> float:
    # BUG 5: Division by zero if list empty
    return sum(values) / len(values)

def save_results(results: List[float], path: str):
    # BUG 6: Writes list directly to file (not JSON or text-safe)
    with open(path, "w") as f:
        f.write(results)

def main():
    processor = DataProcessor()
    worker = Worker(processor)
    
    worker.start()
    worker.join()

    # BUG 7: worker.result may be None if thread failed
    avg = compute_average(worker.result)
    print("Average:", avg)

    save_results(worker.result, "output.txt")

if __name__ == "__main__":
    main()
