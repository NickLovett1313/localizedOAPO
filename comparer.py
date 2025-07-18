# comparer.py
import pandas as pd
from collections import Counter

def compare_oa_po(po_df, oa_df):
    discrepancies = []
    date_mismatches = []

    # Helper to strip leading zeros
    def normalize_line_no(val):
        return str(val).lstrip('0') or '0'

    # 1) Normalize Line No
    po_df['Line No'] = po_df['Line No'].astype(str).apply(normalize_line_no)
    oa_df['Line No'] = oa_df['Line No'].astype(str).apply(normalize_line_no)

    # 2) Exclude ORDER TOTAL for per-line logic
    po_main = po_df[po_df['Model Number'] != 'ORDER TOTAL'].copy()
    oa_main = oa_df[oa_df['Model Number'] != 'ORDER TOTAL'].copy()

    po_groups = po_main.groupby('Line No')
    oa_groups = oa_main.groupby('Line No')
    all_lines = sorted(
        set(po_main['Line No']) | set(oa_main['Line No']),
        key=lambda x: int(x) if x.isdigit() else 99999
    )

    # Tag parser
    def clean_tags(val):
        return [t.strip() for t in val.split(',') if t.strip()] if isinstance(val, str) else []

    # 3) Per-line comparisons (models, qty, price, tags, calib, etc.)
    for line in all_lines:
        po_rows = po_groups.get_group(line) if line in po_groups.groups else None
        oa_rows = oa_groups.get_group(line) if line in oa_groups.groups else None

        # Both exist
        if po_rows is not None and oa_rows is not None:
            po = po_rows.iloc[0]
            oa_date = oa_rows['Ship Date'].iloc[0]
            po_date = po['Ship Date']

            # collect only when dates differ
            if po_date and po_date != oa_date:
                date_mismatches.append((int(line), oa_date.strip(), po_date.strip()))

            # ... your existing discrepancy logic here ...
            # e.g. model mismatch, qty, total, tags, wire-on, calib, etc.

        # missing-in-OA
        elif po_rows is not None:
            discrepancies.append([line, 'Line missing in OA'])

        # missing-in-PO / tariff
        else:
            model = oa_rows['Model Number'].iloc[0]
            if 'TARIFF' in model.upper():
                discrepancies.append([line, 'Tariff missing in PO'])
            else:
                discrepancies.append([line, 'Line missing in PO'])

    # 4) ORDER TOTAL + tariff‐aware total‐mismatch logic (unchanged)
    #    ... your existing code here ...

    # 5) Build main discrepancy DataFrame
    disc_df = pd.DataFrame(
        discrepancies,
        columns=['Line No', 'Field', 'PO Value', 'OA Value', 'Comment']
    )

    # 6) Build condensed date‐discrepancy table
    date_df = build_date_discrepancy_table(date_mismatches)

    return disc_df, date_df


def build_date_discrepancy_table(mismatches):
    """
    Input: list of (line:int, oa_date:str, po_date:str) where oa_date != po_date
    Output: DataFrame grouping contiguous runs into Line X or Lines X–Y
    """
    if not mismatches:
        return pd.DataFrame(columns=['Line(s)', 'OA Expected Dates', 'Factory PO requested dates'])

    # 1) Sort by line
    mismatches.sort(key=lambda x: x[0])

    # 2) Collapse into segments of identical (oa_date, po_date)
    segments = []
    curr_lines, curr_oa, curr_po = [mismatches[0][0]], mismatches[0][1], mismatches[0][2]

    for line, oa_date, po_date in mismatches[1:]:
        if oa_date == curr_oa and po_date == curr_po:
            curr_lines.append(line)
        else:
            segments.append((curr_lines, curr_oa, curr_po))
            curr_lines, curr_oa, curr_po = [line], oa_date, po_date
    segments.append((curr_lines, curr_oa, curr_po))

    # 3) Format rows
    rows = []
    for grp, oa_date, po_date in segments:
        if len(grp) == 1:
            label = f"Line {grp[0]}"
        else:
            label = f"Lines {grp[0]}–{grp[-1]}"
        rows.append([label, oa_date, po_date])

    return pd.DataFrame(rows, columns=[
        'Line(s)', 'OA Expected Dates', 'Factory PO requested dates'
    ])
