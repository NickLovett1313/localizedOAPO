# comparer.py
import pandas as pd
from collections import Counter, defaultdict


def compare_oa_po(po_df, oa_df):
    discrepancies = []
    date_mismatches = []

    def normalize_line_no(val):
        return str(val).lstrip('0') or '0'

    # Normalize Line No
    po_df['Line No'] = po_df['Line No'].astype(str).apply(normalize_line_no)
    oa_df['Line No'] = oa_df['Line No'].astype(str).apply(normalize_line_no)

    # Exclude ORDER TOTAL
    po_main = po_df[po_df['Model Number'] != 'ORDER TOTAL'].copy()
    oa_main = oa_df[oa_df['Model Number'] != 'ORDER TOTAL'].copy()

    po_groups = po_main.groupby('Line No')
    oa_groups = oa_main.groupby('Line No')
    all_lines = sorted(
        set(po_main['Line No']) | set(oa_main['Line No']),
        key=lambda x: int(x) if x.isdigit() else 99999
    )

    def clean_tags(val):
        return [t.strip() for t in val.split(',') if t.strip()] if isinstance(val, str) else []

    # Per-line comparisons
    for line in all_lines:
        po_rows = po_groups.get_group(line) if line in po_groups.groups else None
        oa_rows = oa_groups.get_group(line) if line in oa_groups.groups else None

        if po_rows is not None and oa_rows is not None:
            po = po_rows.iloc[0]
            oa_date = oa_rows['Ship Date'].iloc[0]
            po_date = po['Ship Date']

            # Collect date mismatch only when different
            if po_date and po_date != oa_date:
                date_mismatches.append((int(line), oa_date.strip(), po_date.strip()))

            # ... existing discrepancy logic for model, qty, price, tags, calib ...
            oa_model_set = set(oa_rows['Model Number'])
            oa_qty = oa_rows['Qty'].astype(int).sum()
            oa_total = oa_rows['Total Price'].str.replace(',', '').astype(float).sum()
            oa_tags = sum([clean_tags(t) for t in oa_rows['Tags']], [])
            oa_wire = sum([clean_tags(t) for t in oa_rows['Wire-on Tag']], [])
            oa_calib = set(c.strip() for c in ",".join(oa_rows['Calib Details']).split(',') if c.strip())

            # Model number mismatch
            if po['Model Number'] not in oa_model_set:
                discrepancies.append([line, 'Model Number', po['Model Number'], ", ".join(oa_model_set), 'Model number mismatch'])
            # Quantity mismatch
            if int(po['Qty']) != oa_qty:
                discrepancies.append([line, 'Qty', po['Qty'], str(oa_qty), 'Quantity mismatch'])
            # Total price mismatch
            if float(po['Total Price'].replace(',', '')) != round(oa_total, 2):
                discrepancies.append([line, 'Total Price', po['Total Price'], f"{oa_total:,.2f}", 'Total price mismatch'])
            # Tags multiset mismatch
            expected_tags = clean_tags(po['Tags']) * int(po['Qty'])
            if Counter(expected_tags) != Counter(oa_tags):
                discrepancies.append([line, 'Tags', f"{Counter(expected_tags)}", f"{Counter(oa_tags)}", 'Tag counts mismatch'])
            # Wire-on vs Tags
            if set(oa_wire) != set(oa_tags):
                discrepancies.append([line, 'OA Wire-on Mismatch', '', '', 'Wire-on tags not in Tags'])
            # Calibration mismatch
            po_calib = set(c.strip() for c in po['Calib Details'].split(',') if c.strip())
            if po_calib and po_calib != oa_calib:
                discrepancies.append([line, 'Calib Details', ", ".join(po_calib), ", ".join(oa_calib), 'Calibration info mismatch'])

        elif po_rows is not None:
            # Present in PO only
            discrepancies.append([line, 'Line Status', 'Present in PO', '', 'Line missing in OA'])
        else:
            # Present in OA only or tariff
            model = oa_rows['Model Number'].iloc[0]
            if 'TARIFF' in model.upper():
                discrepancies.append([line, 'Tariff', '', model, 'Tariff missing in PO'])
            else:
                discrepancies.append([line, 'Line Status', '', 'Present in OA', 'Line missing in PO'])

    # ORDER TOTAL logic (unchanged)
    po_tot = po_df.loc[po_df['Model Number'] == 'ORDER TOTAL', 'Total Price']
    oa_tot = oa_df.loc[oa_df['Model Number'] == 'ORDER TOTAL', 'Total Price']
    if not po_tot.empty and not oa_tot.empty:
        po_val = float(po_tot.iloc[0].replace(',', ''))
        oa_val = float(oa_tot.iloc[0].replace(',', ''))
        if round(po_val, 2) != round(oa_val, 2):
            tariff_amt = oa_main.loc[
                oa_main['Model Number'].str.contains('TARIFF', na=False),
                'Total Price'
            ].str.replace(',', '').astype(float).sum()
            note = ''
            if abs(po_val + tariff_amt - oa_val) < 0.01:
                note = ' (**note: differs by exactly the amount of the tariff charge**)'  
            discrepancies.append(['', 'Order Total', f"{po_val:,.2f}", f"{oa_val:,.2f}", 'Order total mismatch' + note])

    # Build DataFrames and enforce string for Line No
    disc_df = pd.DataFrame(
        discrepancies,
        columns=['Line No', 'Field', 'PO Value', 'OA Value', 'Comment']
    )
    disc_df['Line No'] = disc_df['Line No'].astype(str)

    date_df = build_date_discrepancy_table(date_mismatches)

    return disc_df, date_df(po_df, oa_df):
    discrepancies = []
    date_mismatches = []

    # Normalize line numbers by stripping leading zeros
    def normalize_line_no(val):
        return str(val).lstrip('0') or '0'

    po_df['Line No'] = po_df['Line No'].astype(str).apply(normalize_line_no)
    oa_df['Line No'] = oa_df['Line No'].astype(str).apply(normalize_line_no)

    # Strip ORDER TOTAL rows only for group-level matching
    po_main = po_df[po_df['Model Number'] != 'ORDER TOTAL'].copy()
    oa_main = oa_df[oa_df['Model Number'] != 'ORDER TOTAL'].copy()

    # Group OA and PO by normalized Line No
    po_groups = po_main.groupby('Line No')
    oa_groups = oa_main.groupby('Line No')

    all_lines = set(po_main['Line No']) | set(oa_main['Line No'])

    def clean_tags(val):
        return [t.strip() for t in val.split(',') if t.strip()] if isinstance(val, str) else []

    # Safe sort for mixed Line Nos (numbers and blanks)
    def safe_sort_key(x):
        s = str(x).strip()
        return ("~" + s) if not s.isdigit() else s.zfill(5)

    for line in sorted(all_lines, key=safe_sort_key):
        po_rows = po_groups.get_group(line) if line in po_groups.groups else None
        oa_rows = oa_groups.get_group(line) if line in oa_groups.groups else None

        if po_rows is not None and oa_rows is not None:
            # Aggregate OA
            oa_model_set = set(oa_rows['Model Number'])
            oa_qty = oa_rows['Qty'].astype(int).sum()
            oa_total = oa_rows['Total Price'].replace(',', '', regex=True).astype(float).sum()
            oa_tags = sum([clean_tags(t) for t in oa_rows['Tags']], [])
            oa_wire = sum([clean_tags(t) for t in oa_rows['Wire-on Tag']], [])
            oa_calib = set([c.strip() for c in ",".join(oa_rows['Calib Details']).split(',') if c.strip()])
            oa_ship_dates = set(oa_rows['Ship Date'])

            po_row = po_rows.iloc[0]  # Usually just one row

            # Model Number
            if po_row['Model Number'] not in oa_model_set:
                discrepancies.append([line, 'Model Number', po_row['Model Number'], ", ".join(oa_model_set), 'Model number mismatch'])

            # Qty
            if int(po_row['Qty']) != oa_qty:
                discrepancies.append([line, 'Qty', po_row['Qty'], str(oa_qty), 'Quantity mismatch'])

            # Total
            if float(po_row['Total Price'].replace(',', '')) != round(oa_total, 2):
                discrepancies.append([line, 'Total Price', po_row['Total Price'], f"{oa_total:,.2f}", 'Total price mismatch'])

            # Tags (multiset logic)
            po_tags = clean_tags(po_row['Tags']) * int(po_row['Qty'])
            if Counter(po_tags) != Counter(oa_tags):
                discrepancies.append([line, 'Tags', f"{Counter(po_tags)}", f"{Counter(oa_tags)}", 'Tag counts do not match PO Qty'])

            # Wire-on match
            if set(oa_tags) != set(oa_wire):
                discrepancies.append([line, 'OA Wire-on Mismatch', '', '', 'Tags listed do not match wire-on tag section'])

            # Calib Details
            po_calib = set([c.strip() for c in po_row['Calib Details'].split(',') if c.strip()])
            if po_calib and po_calib != oa_calib:
                discrepancies.append([line, 'Calib Details', ", ".join(po_calib), ", ".join(oa_calib), 'Calibration info mismatch'])

            # Ship Date mismatch (for date table)
            if po_row['Ship Date'] and po_row['Ship Date'] not in oa_ship_dates:
                date_mismatches.append([f"Line {line}", ", ".join(oa_ship_dates), po_row['Ship Date']])

        elif po_rows is not None:
            discrepancies.append([line, 'Line Status', 'Present in PO', 'Missing in OA', 'Line missing in OA'])
        elif oa_rows is not None:
            oa_model = oa_rows.iloc[0]['Model Number']
            if 'TARIFF' in oa_model.upper():
                discrepancies.append([line, 'Tariff', '', oa_model, 'Tariff line missing from PO'])
            else:
                discrepancies.append([line, 'Line Status', 'Missing in PO', 'Present in OA', 'Unexpected line in OA'])

    # ORDER TOTAL logic
    po_total = po_df[po_df['Model Number'] == 'ORDER TOTAL']['Total Price'].values
    oa_total = oa_df[oa_df['Model Number'] == 'ORDER TOTAL']['Total Price'].values
    if po_total.size and oa_total.size:
        po_val = float(po_total[0].replace(',', ''))
        oa_val = float(oa_total[0].replace(',', ''))
        if round(po_val, 2) != round(oa_val, 2):
            diff = round(abs(po_val - oa_val), 2)
            tariff_sum = oa_main[oa_main['Model Number'].str.contains('TARIFF', na=False)]['Total Price'].replace(',', '', regex=True).astype(float).sum()
            if diff == round(tariff_sum, 2):
                comment = 'Order total mismatch (**note: differs by exactly the amount of the tariff charge**)'
            else:
                comment = 'Order total mismatch'
            discrepancies.append(['', 'Order Total', f"{po_val:,.2f}", f"{oa_val:,.2f}", comment])

    # Condense date mismatches by group
    def condense_date_ranges(date_rows):
        grouped = defaultdict(list)
        for row in date_rows:
            if len(row) != 3:
                continue
            line_label, oa_date, po_date = row
            key = (oa_date.strip(), po_date.strip())
            line_num = int(line_label.replace("Line ", "").strip())
            grouped[key].append(line_num)

        condensed_rows = []
        for (oa_date, po_date), lines in grouped.items():
            lines = sorted(lines)
            if len(lines) == 1:
                label = f"Line {lines[0]}"
            else:
                label = f"Lines {lines[0]}–{lines[-1]}"
            condensed_rows.append([label, oa_date, po_date])

        return pd.DataFrame(condensed_rows, columns=['Line(s)', 'OA Expected Dates', 'Factory PO requested dates'])

    disc_df = pd.DataFrame(discrepancies, columns=['Line No', 'Field', 'PO Value', 'OA Value', 'Comment'])
    date_df = condense_date_ranges(date_mismatches)

    return disc_df, date_df
