# comparer.py
import pandas as pd
from collections import Counter

def compare_oa_po(po_df, oa_df):
    discrepancies = []
    date_mismatches = []

    def normalize_line_no(val):
        return str(val).lstrip('0') or '0'

    # 1) Normalize line numbers
    po_df['Line No'] = po_df['Line No'].astype(str).apply(normalize_line_no)
    oa_df['Line No'] = oa_df['Line No'].astype(str).apply(normalize_line_no)

    # 2) Separate out ORDER TOTAL
    po_main = po_df[po_df['Model Number'] != 'ORDER TOTAL'].copy()
    oa_main = oa_df[oa_df['Model Number'] != 'ORDER TOTAL'].copy()

    po_groups = po_main.groupby('Line No')
    oa_groups = oa_main.groupby('Line No')
    all_lines = set(po_main['Line No']) | set(oa_main['Line No'])

    def clean_tags(val):
        return [t.strip() for t in val.split(',') if t.strip()] if isinstance(val, str) else []

    def safe_sort_key(x):
        s = str(x).strip()
        return ("~" + s) if not s.isdigit() else s.zfill(5)

    # 3) Your existing per-line comparisons
    for line in sorted(all_lines, key=safe_sort_key):
        po_rows = po_groups.get_group(line) if line in po_groups.groups else None
        oa_rows = oa_groups.get_group(line) if line in oa_groups.groups else None

        if po_rows is not None and oa_rows is not None:
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
            # Tags multiset
            expected_tags = clean_tags(po['Tags']) * int(po['Qty'])
            if Counter(expected_tags) != Counter(oa_tags):
                discrepancies.append([line, 'Tags', f"{Counter(expected_tags)}", f"{Counter(oa_tags)}", 'Tag counts mismatch'])
            # Wire-on vs Tags
            if set(oa_wire) != set(oa_tags):
                discrepancies.append([line, 'OA Wire-on Mismatch', '', '', 'Wire-on tags ≠ Tags'])
            # Calibration
            po_calib = set(c.strip() for c in po['Calib Details'].split(',') if c.strip())
            if po_calib and po_calib != oa_calib:
                discrepancies.append([line, 'Calib Details', ", ".join(po_calib), ", ".join(oa_calib), 'Calibration info mismatch'])
            # **Collect only true date mismatches**
            if po['Ship Date'] and po['Ship Date'] not in oa_dates:
                date_mismatches.append([line, oa_dates.pop(), po['Ship Date']])

        elif po_rows is not None:
            discrepancies.append([line, 'Line Status', 'Present in PO', 'Missing in OA', 'Line missing in OA'])
        else:
            oa_model = oa_rows.iloc[0]['Model Number']
            if 'TARIFF' in oa_model.upper():
                discrepancies.append([line, 'Tariff', '', oa_model, 'Tariff missing in PO'])
            else:
                discrepancies.append([line, 'Line Status', 'Missing in PO', 'Present in OA', 'Unexpected line in OA'])

    # 4) ORDER TOTAL + tariff logic (unchanged)
    po_tot = po_df.loc[po_df['Model Number'] == 'ORDER TOTAL', 'Total Price']
    oa_tot = oa_df.loc[oa_df['Model Number'] == 'ORDER TOTAL', 'Total Price']
    if not po_tot.empty and not oa_tot.empty:
        po_val = float(po_tot.iloc[0].replace(',', ''))
        oa_val = float(oa_tot.iloc[0].replace(',', ''))
        if round(po_val, 2) != round(oa_val, 2):
            tariff_amt = oa_main.loc[oa_main['Model Number'].str.contains('TARIFF', na=False),
                                     'Total Price'] \
                            .str.replace(',', '').astype(float).sum()
            note = ' (**note: differs by exactly the amount of the tariff charge**)' \
                   if abs(po_val + tariff_amt - oa_val) < 0.01 else ''
            discrepancies.append(['', 'Order Total', f"{po_val:,.2f}", f"{oa_val:,.2f}", 'Order total mismatch' + note])

    # 5) Build the discrepancy table
    disc_df = pd.DataFrame(discrepancies, columns=['Line No', 'Field', 'PO Value', 'OA Value', 'Comment'])

    # 6) Build the **new** grouped date-mismatch table
    date_df = build_date_discrepancy_table(oa_main, po_main)

    return disc_df, date_df


def build_date_discrepancy_table(oa_df, po_df):
    """
    1. Group OA lines by identical Ship Date in ascending order.
    2. Within each OA group, split whenever the PO Ship Date changes.
    3. Keep only segments where OA Date != PO Date.
    """
    # Helper to normalize and sort
    def norm_line(x):
        return int(str(x))

    # Build maps
    oa_map = {int(str(r['Line No'])): r['Ship Date'] for _, r in oa_df.iterrows()}
    po_map = {int(str(r['Line No'])): r['Ship Date'] for _, r in po_df.iterrows()}

    # Only consider lines present in both
    lines = sorted(set(oa_map) & set(po_map), key=lambda x: x)

    # Step A: group by OA date
    date_segments = []
    curr_lines = [lines[0]]
    curr_oa = oa_map[lines[0]]
    for ln in lines[1:]:
        if oa_map[ln] == curr_oa:
            curr_lines.append(ln)
        else:
            date_segments.append((curr_lines[:], curr_oa))
            curr_lines = [ln]
            curr_oa = oa_map[ln]
    date_segments.append((curr_lines[:], curr_oa))

    # Step B: within each OA segment, split on PO date changes
    final_rows = []
    for segment_lines, oa_date in date_segments:
        subgroup = [segment_lines[0]]
        curr_po = po_map[segment_lines[0]]
        for ln in segment_lines[1:]:
            if po_map[ln] == curr_po:
                subgroup.append(ln)
            else:
                final_rows.append((subgroup[:], oa_date, curr_po))
                subgroup = [ln]
                curr_po = po_map[ln]
        final_rows.append((subgroup[:], oa_date, curr_po))

    # Step C: filter out where OA and PO dates match
    filtered = [(grp, oa, po) for grp, oa, po in final_rows if oa != po]

    # Step D: format into DataFrame
    rows = []
    for grp, oa, po in filtered:
        if len(grp) == 1:
            label = f"Line {grp[0]}"
        else:
            label = f"Lines {grp[0]}–{grp[-1]}"
        rows.append([label, oa, po])

    return pd.DataFrame(rows, columns=["Line(s)", "OA Expected Dates", "Factory PO requested dates"])
