import pandas as pd
import numpy as np
from difflib import ndiff

def diff_chars(a, b):
    return ''.join(x for x in ndiff(a, b) if x.startswith('+ ') or x.startswith('- ')).replace('+ ', '[').replace('- ', '][').replace('][', '][')

def compare_oa_po(po_df, oa_df):
    discrepancies = []
    date_discrepancies = []

    # Extract order total for reference
    oa_total_row = oa_df[oa_df['Model Number'] == 'ORDER TOTAL']
    po_total_row = po_df[po_df['Model Number'] == 'ORDER TOTAL']
    oa_total = oa_total_row['Total Price'].values[0] if not oa_total_row.empty else ''
    po_total = po_total_row['Total Price'].values[0] if not po_total_row.empty else ''

    # Clean for comparison
    po_lines = po_df[po_df['Model Number'] != 'ORDER TOTAL'].copy()
    oa_lines = oa_df[oa_df['Model Number'] != 'ORDER TOTAL'].copy()

    po_lines['Line No'] = po_lines['Line No'].astype(str).str.lstrip('0')
    oa_lines['Line No'] = oa_lines['Line No'].astype(str).str.lstrip('0')

    # Separate TARIFF lines
    oa_tariff = oa_lines[oa_lines['Model Number'].str.contains('TARIFF', case=False, na=False)]
    po_tariff = po_lines[po_lines['Model Number'].str.contains('TARIFF', case=False, na=False)]

    # Remove tariff lines from main set
    oa_main = oa_lines[~oa_lines.index.isin(oa_tariff.index)]
    po_main = po_lines[~po_lines.index.isin(po_tariff.index)]

    # ─────────────────────────────
    # Handle TARIFF charges
    # ─────────────────────────────
    for _, row in oa_tariff.iterrows():
        oa_price = row['Total Price']
        if not oa_price:
            continue

        # Look for PO line with same price and TARIFF in model
        found = po_tariff[
            (po_tariff['Total Price'] == oa_price)
        ]
        if found.empty:
            discrepancies.append({
                "Line": "",
                "Issue": f"OA includes tariff charge ${oa_price} but PO does not."
            })

    # ─────────────────────────────
    # Compare all line numbers
    # ─────────────────────────────
    for _, oa_row in oa_main.iterrows():
        ln = oa_row['Line No']
        po_row = po_main[po_main['Line No'] == ln]
        if po_row.empty:
            discrepancies.append({
                "Line": ln,
                "Issue": "Line exists in OA but not in PO."
            })
            continue

        po_row = po_row.iloc[0]

        # Dates
        if oa_row['Ship Date'] and po_row['Ship Date'] and oa_row['Ship Date'] != po_row['Ship Date']:
            date_discrepancies.append({
                "Line": ln,
                "OA Expected Date": oa_row['Ship Date'],
                "Factory PO Requested Date": po_row['Ship Date']
            })

        # Model mismatch
        if oa_row['Model Number'] and po_row['Model Number'] and oa_row['Model Number'] != po_row['Model Number']:
            diff = diff_chars(oa_row['Model Number'], po_row['Model Number'])
            discrepancies.append({
                "Line": ln,
                "Issue": f"Model Number mismatch → OA: '{oa_row['Model Number']}' vs PO: '{po_row['Model Number']}' | Diff: {diff}"
            })

        # Qty mismatch
        if oa_row['Qty'] and po_row['Qty'] and oa_row['Qty'] != po_row['Qty']:
            discrepancies.append({
                "Line": ln,
                "Issue": f"Quantity mismatch → OA: {oa_row['Qty']} vs PO: {po_row['Qty']}"
            })

        # Price mismatch
        if oa_row['Total Price'] and po_row['Total Price'] and oa_row['Total Price'] != po_row['Total Price']:
            discrepancies.append({
                "Line": ln,
                "Issue": f"Total Price mismatch → OA: {oa_row['Total Price']} vs PO: {po_row['Total Price']}"
            })

        # Tag logic
        oa_tagged = oa_row['Has Tag?'] == 'Y'
        po_tagged = po_row['Has Tag?'] == 'Y'
        if oa_tagged and not po_tagged:
            discrepancies.append({
                "Line": ln,
                "Issue": "OA has tag but PO does not."
            })
        elif not oa_tagged and po_tagged:
            discrepancies.append({
                "Line": ln,
                "Issue": "PO has tag but OA does not."
            })
        elif oa_row['Tags'] and po_row['Tags'] and oa_row['Tags'] != po_row['Tags']:
            discrepancies.append({
                "Line": ln,
                "Issue": f"Tag mismatch → OA: {oa_row['Tags']} vs PO: {po_row['Tags']}"
            })

        # Calibration
        if oa_row['Calib Data?'] == 'Y' and po_row['Calib Data?'] != 'Y':
            discrepancies.append({
                "Line": ln,
                "Issue": "OA has calibration data but PO does not."
            })
        elif po_row['Calib Data?'] == 'Y' and oa_row['Calib Data?'] != 'Y':
            discrepancies.append({
                "Line": ln,
                "Issue": "PO has calibration data but OA does not."
            })
        elif oa_row['Calib Details'] and po_row['Calib Details'] and oa_row['Calib Details'] != po_row['Calib Details']:
            discrepancies.append({
                "Line": ln,
                "Issue": f"Calibration detail mismatch → OA: {oa_row['Calib Details']} vs PO: {po_row['Calib Details']}"
            })

    # Missing PO lines
    for _, po_row in po_main.iterrows():
        ln = po_row['Line No']
        if oa_main[oa_main['Line No'] == ln].empty:
            discrepancies.append({
                "Line": ln,
                "Issue": "Line exists in PO but not in OA."
            })

    # Final order total check
    if oa_total and po_total and oa_total != po_total:
        discrepancies.append({
            "Line": "",
            "Issue": f"ORDER TOTAL mismatch → OA: {oa_total} vs PO: {po_total}"
        })

    # Return DataFrames
    return pd.DataFrame(discrepancies), pd.DataFrame(date_discrepancies)
