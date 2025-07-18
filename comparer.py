# comparer.py
import pandas as pd
from collections import Counter

def compare_oa_po(po_df, oa_df):
    discrepancies = []
    date_mismatches = []

    def normalize_line_no(val):
        return str(val).lstrip('0') or '0'

    # Normalize Line No
    po_df['Line No'] = po_df['Line No'].astype(str).apply(normalize_line_no)
    oa_df['Line No'] = oa_df['Line No'].astype(str).apply(normalize_line_no)

    # Exclude ORDER TOTAL for per-line comparison
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

        # Both OA and PO have this line
        if po_rows is not None and oa_rows is not None:
            po = po_rows.iloc[0]
            oa_date = oa_rows['Ship Date'].iloc[0]
            po_date = po['Ship Date']

            # Only collect date mismatches when they differ
            if po_date and po_date != oa_date:
                date_mismatches.append((int(line), oa_date.strip(), po_date.strip()))

            # Model number
            oa_models = set(oa_rows['Model Number'])
            if po['Model Number'] not in oa_models:
                discrepancies.append([
                    line,
                    'Model Number',
                    po['Model Number'],
                    ", ".join(oa_models),
                    'Model number mismatch'
                ])

            # Quantity
            oa_qty = oa_rows['Qty'].astype(int).sum()
            if int(po['Qty']) != oa_qty:
                discrepancies.append([
                    line,
                    'Qty',
                    po['Qty'],
                    str(oa_qty),
                    'Quantity mismatch'
                ])

            # Total Price
            oa_total = oa_rows['Total Price'].str.replace(',', '').astype(float).sum()
            if float(po['Total Price'].replace(',', '')) != round(oa_total, 2):
                discrepancies.append([
                    line,
                    'Total Price',
                    po['Total Price'],
                    f"{oa_total:,.2f}",
                    'Total price mismatch'
                ])

            # Tags (multiset)
            expected = clean_tags(po['Tags']) * int(po['Qty'])
            oa_tags = sum([clean_tags(t) for t in oa_rows['Tags']], [])
            if Counter(expected) != Counter(oa_tags):
                discrepancies.append([
                    line,
                    'Tags',
                    f"{Counter(expected)}",
                    f"{Counter(oa_tags)}",
                    'Tag counts mismatch'
                ])

            # Wire-on vs Tags
            oa_wire = sum([clean_tags(t) for t in oa_rows['Wire-on Tag']], [])
            if set(oa_wire) != set(oa_tags):
                discrepancies.append([
                    line,
                    'OA Wire-on Mismatch',
                    '',
                    '',
                    'Wire-on tags not in Tags'
                ])

            # Calibration
            oa_calib = set(
                c.strip()
                for c in ",".join(oa_rows['Calib Details']).split(',')
                if c.strip()
            )
            po_calib = set(
                c.strip()
                for c in po['Calib Details'].split(',')
                if c.strip()
            )
            if po_calib and po_calib != oa_calib:
                discrepancies.append([
                    line,
                    'Calib Details',
                    ", ".join(po_calib),
                    ", ".join(oa_calib),
                    'Calibration info mismatch'
                ])

        # PO-only line
        elif po_rows is not None:
            discrepancies.append([
                line,
                'Line Status',
                'Present in PO',
                '',
                'Line missing in OA'
            ])

        # OA-only line
        else:
            model = oa_rows['Model Number'].iloc[0]
            if 'TARIFF' in model.upper():
                discrepancies.append([
                    line,
                    'Tariff',
                    '',
                    model,
                    'Tariff missing in PO'
                ])
            else:
                discrepancies.append([
                    line,
                    'Line Status',
                    '',
                    'Present in OA',
                    'Line missing in PO'
                ])

    # ORDER TOTAL and tariff‐aware total mismatch
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
            discrepancies.append([
                '',
                'Order Total',
                f"{po_val:,.2f}",
                f"{oa_val:,.2f}",
                'Order total mismatch' + note
            ])

    # Build DataFrames and cast Line No to string
    disc_df = pd.DataFrame(
        discrepancies,
        columns=['Line No', 'Field', 'PO Value', 'OA Value', 'Comment']
    )
    disc_df['Line No'] = disc_df['Line No'].astype(str)

    date_df = build_date_discrepancy_table(date_mismatches)

    return disc_df, date_df


def build_date_discrepancy_table(mismatches):
    """
    Input: list of (line:int, oa_date:str, po_date:str)
    Output: DataFrame grouping runs where oa_date != po_date into ranges.
    """
    if not mismatches:
        return pd.DataFrame(
            columns=['Line(s)', 'OA Expected Dates', 'Factory PO requested dates']
        )

    # 1) Sort by line number
    mismatches.sort(key=lambda x: x[0])

    # 2) Collapse contiguous runs of identical (oa, po)
    segments = []
    curr_lines, curr_oa, curr_po = [mismatches[0][0]], mismatches[0][1], mismatches[0][2]
    for line, oa_date, po_date in mismatches[1:]:
        if oa_date == curr_oa and po_date == curr_po:
            curr_lines.append(line)
        else:
            segments.append((curr_lines, curr_oa, curr_po))
            curr_lines, curr_oa, curr_po = [line], oa_date, po_date
    segments.append((curr_lines, curr_oa, curr_po))

    # 3) Format into DataFrame
    rows = []
    for grp, oa_date, po_date in segments:
        if len(grp) == 1:
            label = f"Line {grp[0]}"
        else:
            label = f"Lines {grp[0]}–{grp[-1]}"
        rows.append([label, oa_date, po_date])

    return pd.DataFrame(
        rows,
        columns=['Line(s)', 'OA Expected Dates', 'Factory PO requested dates']
    )
