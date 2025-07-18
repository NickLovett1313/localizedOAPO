# comparer.py
import pandas as pd
from collections import Counter

def compare_oa_po(po_df, oa_df):
    discrepancies = []
    date_mismatches = []

    def normalize_line_no(val):
        return str(val).lstrip('0') or '0'

    # Normalize line numbers
    po_df['Line No'] = po_df['Line No'].astype(str).apply(normalize_line_no)
    oa_df['Line No'] = oa_df['Line No'].astype(str).apply(normalize_line_no)

    # Separate out ORDER TOTAL so we only group the main lines
    po_main = po_df[po_df['Model Number'] != 'ORDER TOTAL']
    oa_main = oa_df[oa_df['Model Number'] != 'ORDER TOTAL']

    po_groups = po_main.groupby('Line No')
    oa_groups = oa_main.groupby('Line No')
    all_lines = set(po_main['Line No']) | set(oa_main['Line No'])

    def clean_tags(val):
        return [t.strip() for t in val.split(',') if t.strip()] if isinstance(val, str) else []

    def safe_sort_key(x):
        s = str(x).strip()
        return ("~" + s) if not s.isdigit() else s.zfill(5)

    # Compare each line
    for line in sorted(all_lines, key=safe_sort_key):
        po_rows = po_groups.get_group(line) if line in po_groups.groups else None
        oa_rows = oa_groups.get_group(line) if line in oa_groups.groups else None

        # Both present
        if po_rows is not None and oa_rows is not None:
            # Aggregate OA values
            oa_model_set = set(oa_rows['Model Number'])
            oa_qty       = oa_rows['Qty'].astype(int).sum()
            oa_total     = oa_rows['Total Price'].str.replace(',', '').astype(float).sum()
            oa_tags      = sum([clean_tags(t) for t in oa_rows['Tags']], [])
            oa_wire      = sum([clean_tags(t) for t in oa_rows['Wire-on Tag']], [])
            oa_calib     = set(c.strip() for c in ",".join(oa_rows['Calib Details']).split(',') if c.strip())
            oa_dates     = set(oa_rows['Ship Date'])

            po = po_rows.iloc[0]

            # Model Number
            if po['Model Number'] not in oa_model_set:
                discrepancies.append([line, 'Model Number', po['Model Number'], ", ".join(oa_model_set), 'Model number mismatch'])
            # Qty
            if int(po['Qty']) != oa_qty:
                discrepancies.append([line, 'Qty', po['Qty'], str(oa_qty), 'Quantity mismatch'])
            # Total Price
            if float(po['Total Price'].replace(',', '')) != round(oa_total, 2):
                discrepancies.append([line, 'Total Price', po['Total Price'], f"{oa_total:,.2f}", 'Total price mismatch'])
            # Tags (multiset)
            expected_tags = clean_tags(po['Tags']) * int(po['Qty'])
            if Counter(expected_tags) != Counter(oa_tags):
                discrepancies.append([line, 'Tags', f"{Counter(expected_tags)}", f"{Counter(oa_tags)}", 'Tag counts mismatch'])
            # Wire-on vs Tags
            if set(oa_wire) != set(oa_tags):
                discrepancies.append([line, 'OA Wire-on Mismatch', '', '', 'Wire-on tags ≠ Tags'])
            # Calib Details
            po_calib = set(c.strip() for c in po['Calib Details'].split(',') if c.strip())
            if po_calib and po_calib != oa_calib:
                discrepancies.append([line, 'Calib Details', ", ".join(po_calib), ", ".join(oa_calib), 'Calibration info mismatch'])
            # Date mismatch → collect only if different
            if po['Ship Date'] and po['Ship Date'] not in oa_dates:
                date_mismatches.append([f"Line {line}", ", ".join(sorted(oa_dates)), po['Ship Date']])

        # PO-only line
        elif po_rows is not None:
            discrepancies.append([line, 'Line Status', 'Present in PO', 'Missing in OA', 'Line missing in OA'])
        # OA-only line
        else:
            oa_model = oa_rows.iloc[0]['Model Number']
            if 'TARIFF' in oa_model.upper():
                discrepancies.append([line, 'Tariff', '', oa_model, 'Tariff missing in PO'])
            else:
                discrepancies.append([line, 'Line Status', 'Missing in PO', 'Present in OA', 'Unexpected line in OA'])

    # ORDER TOTAL logic
    po_tot = po_df.loc[po_df['Model Number'] == 'ORDER TOTAL', 'Total Price']
    oa_tot = oa_df.loc[oa_df['Model Number'] == 'ORDER TOTAL', 'Total Price']
    if not po_tot.empty and not oa_tot.empty:
        po_val = float(po_tot.iloc[0].replace(',', ''))
        oa_val = float(oa_tot.iloc[0].replace(',', ''))
        if round(po_val, 2) != round(oa_val, 2):
            tariff_amt = oa_main.loc[oa_main['Model Number'].str.contains('TARIFF', na=False), 'Total Price']\
                            .str.replace(',', '').astype(float).sum()
            note = ' (**note: differs by exactly the amount of the tariff charge**)' \
                   if abs(po_val + tariff_amt - oa_val) < 0.01 else ''
            discrepancies.append(['', 'Order Total', f"{po_val:,.2f}", f"{oa_val:,.2f}", 'Order total mismatch' + note])

    # Build DataFrames
    disc_df = pd.DataFrame(discrepancies, columns=['Line No', 'Field', 'PO Value', 'OA Value', 'Comment'])
    date_df = pd.DataFrame(date_mismatches, columns=['Line(s)', 'OA Expected Dates', 'Factory PO requested dates'])

    return disc_df, date_df
