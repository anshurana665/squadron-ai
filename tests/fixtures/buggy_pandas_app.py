
# buggy_pandas_app.py
# This file contains a realistic library-related bug

import pandas as pd

def main():
    data = {"name": ["A", "B"], "score": [10, 20]}
    df = pd.DataFrame(data)

    # BUG: .append() was removed in pandas 2.0
    new_row = {"name": "C", "score": 30}
    df = df.append(new_row, ignore_index=True)

    print(df)

if __name__ == "__main__":
    main()
