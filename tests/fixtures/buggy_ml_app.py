
# buggy_ml_app.py
# This file contains bugs using multiple libraries (requests, matplotlib, scikit-learn)

import requests
import matplotlib.pyplot as plt
from sklearn.linear_model import LinearRegression
import numpy as np

def fetch_data():
    # BUG 1: No error handling for failed HTTP request
    response = requests.get("https://example.com/nonexistent.csv")
    return response.text  # Might be HTML or error page

def train_model():
    # BUG 2: Shape mismatch for scikit-learn
    X = np.array([1, 2, 3, 4])     # Should be 2D
    y = np.array([2, 4, 6, 8])
    
    model = LinearRegression()
    model.fit(X, y)  # Will raise ValueError
    return model

def plot_data():
    # BUG 3: Mismatched dimensions in plotting
    x = [1, 2, 3]
    y = [1, 4]   # Length mismatch
    plt.plot(x, y)
    plt.show()

def main():
    fetch_data()
    train_model()
    plot_data()

if __name__ == "__main__":
    main()
