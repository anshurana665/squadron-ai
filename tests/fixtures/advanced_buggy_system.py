
"""
advanced_buggy_system.py

This file contains difficult, non-trivial bugs:
- race conditions
- hidden data corruption
- subtle numpy misuse
- improper locking
- async/thread interaction issues
- incorrect caching logic
"""

import threading
import time
import numpy as np
from typing import Dict

class SharedCache:
    def __init__(self):
        self.data: Dict[str, np.ndarray] = {}

    def get(self, key):
        # BUG 1: No synchronization (race condition)
        return self.data.get(key)

    def set(self, key, value):
        # BUG 2: Mutable object stored without copy
        self.data[key] = value


class Processor:

    def compute(self, arr: np.ndarray) -> np.ndarray:
        # BUG 3: In-place modification of input (side effect)
        arr *= 2
        return arr


class Worker(threading.Thread):

    def __init__(self, cache: SharedCache, key: str):
        super().__init__()
        self.cache = cache
        self.key = key

    def run(self):
        data = self.cache.get(self.key)

        if data is None:
            return

        processor = Processor()

        # BUG 4: Data is shared and mutated across threads
        result = processor.compute(data)

        # BUG 5: Overwrites cache with partially computed data
        self.cache.set(self.key, result)


class Pipeline:

    def __init__(self):
        self.cache = SharedCache()

    def load_data(self):
        # BUG 6: dtype causes overflow silently
        arr = np.array([100, 150, 200], dtype=np.uint8)
        self.cache.set("data", arr)

    def run(self):
        self.load_data()

        threads = []

        for _ in range(5):
            t = Worker(self.cache, "data")
            t.start()
            threads.append(t)

        # BUG 7: Missing join → nondeterministic behavior
        # for t in threads:
        #     t.join()

        final = self.cache.get("data")

        # BUG 8: Assumes computation finished
        return np.sum(final)


def main():
    pipeline = Pipeline()
    result = pipeline.run()
    print("Result:", result)


if __name__ == "__main__":
    main()
