# Rosemount OA–PO Checker

## What It Does
Checks a Rosemount Order Acknowledgement (OA) against a Factory Purchase Order (PO) line-by-line.

## How to Use
1. Upload your PO.csv and OA.csv in the app.
2. Click “Run Check”.
3. View the numbered discrepancy list.
4. Click “Save Report” to export the results to `/output/`.

## How to Run It
```
pip install -r requirements.txt
streamlit run app.py
```

## Example Files
- `example_files/` folder has sample PO and OA files to test.
