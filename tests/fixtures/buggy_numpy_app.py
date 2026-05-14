
# buggy_numpy_app.py
# This file contains subtle NumPy-related bugs

import numpy as np

def main():
    arr = np.array([1, 2, 3])

    # BUG 1: Broadcasting shape mismatch
    b = np.array([1, 2])
    print(arr + b)   # ValueError

    # BUG 2: Invalid axis
    mat = np.array([[1, 2], [3, 4]])
    print(np.sum(mat, axis=2))  # AxisError

    # BUG 3: Integer overflow
    big = np.array([300], dtype=np.uint8)
    print(big * 2)  # wraps around to 88 instead of 600

if __name__ == "__main__":
    main()
