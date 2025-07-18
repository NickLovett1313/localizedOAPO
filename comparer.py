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

    # Exclude the ORDER TOTAL row for line-by-line comparison
    po_main = po_df[po_df['Model Number'] != 'ORDER TOTAL'].copy()
    oa_main = oa_df[oa_df['Model Number'] != 'ORDER TOTAL'].copy()

    po_groups = po_main.groupby('Line No')
    oa_groups = oa_main.groupby('Line No')
    all_lines = sorted(
        set(po_main['Line No']) | set(oa_main['Line No']),
        key=lambda x: int(x) if x.isdigit() else 99999
    )

    def clean_tags(val):
        if not isinstance(val, str):
            return []
        return [t.strip() for t in val.split(',') if t.strip()]

    # Compare each line
    for line in all_lines:
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
            oa_calib     = set(
                c.strip()
                for c in ",".join(oa_rows['Calib Details']).split(',')
                if c.strip()
            )
            oa_date      = oa_rows['Ship Date'].iloc[0]

            po = po_rows.iloc[0]
            po_date = po['Ship Date']

            # Model number
            if po['Model Number'] not in oa_model_set:
                discrepancies.append([
                    line, 'Model Number',
                    po['Model Number'],
                    ", ".join(oa_model_set),
                    'Model number mismatch'
                ])
            # Quantity
            if int(po['Qty']) != oa_qty:
                discrepancies.append([line, 'Qty', po['Qty'], str(oa_qty), 'Quantity mismatch'])
            # Total price
            if float(po['Total Price'].replace(',', '')) != round(oa_total, 2):
                discrepancies.append([
                    line, 'Total Price',
                    po['Total Price'],
                    f"{oa_total:,.2f}",
                    'Total price mismatch'
                ])
            # Tags multiset
            expected_tags = clean_tags(po['Tags']) * int(po['Qty'])
            if Counter(expected_tags) != Counter(oa_tags):
                discrepancies.append([
                    line, 'Tags',
                    f"{Counter(expected_tags)}",
                    f"{Counter(oa_tags)}",
                    'Tag counts mismatch'
                ])
            # Wire-on vs Tags
            if set(oa_wire) != set(oa_tags):
                discrepancies.append([
                    line, 'OA Wire-on Mismatch',
                    '', '', 'Wire-on tags not in Tags'
                ])
            # Calibration details
            po_calib = set(
                c.strip() for c in po['Calib Details'].split(',')
                if c.strip()
            )
            if po_calib and po_calib != oa_calib:
                discrepancies.append([
                    line, 'Calib Details',
                    ", ".join(po_calib),
                    ", ".join(oa_calib),
                    'Calibration info mismatch'
                ])
            # Ship Date mismatch
            if po_date and po_date != oa_date:
                date_mismatches.append((int(line), oa_date.strip(), po_date.strip()))

        # Present in PO only
        elif po_rows is not None:
            discrepancies.append([line, 'Line missing in OA'])
        # Present in OA only
        else:
            oa_model = oa_rows['Model Number'].iloc[0]
            if 'TARIFF' in oa_model.upper():
                discrepancies.append([line, 'Tariff missing in PO'])
            else:
                discrepancies.append([line, 'Line missing in PO'])

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
            discrepancies.append([
                '', 'Order Total',
                f"{po_val:,.2f}",
                f"{oa_val:,.2f}",
                'Order total mismatch' + note
            ])

    disc_df = pd.DataFrame(
        discrepancies,
        columns=['Line No', 'Field', 'PO Value', 'OA Value', 'Comment']
    )
    date_df = build_date_discrepancy_table(date_mismatches)

    return disc_df, date_df


def build_date_discrepancy_table(mismatches):
    # Group OA ship dates into sequential segments
    mismatches.sort(key=lambda x: x[0])  # sort by line number
    segments = []
    if not mismatches:
        return pd.DataFrame(columns=['Line(s)', 'OA Expected Dates', 'Factory PO requested dates'])

    # Step 1: group by OA date
    oa_groups = []
    curr = [mismatches[0]]
    for entry in mismatches[1:]:
        line, oa_date, po_date = entry
        if oa_date == curr[-1][1]:
            curr.append(entry)
        else:
            oa_groups.append(curr)
            curr = [entry]
    oa_groups.append(curr)

    # Step 2: within each OA-group, split by PO date changes
    final = []
    for grp in oa_groups:
        sub = [grp[0]]
        for entry in grp[1:]:
            if entry[2] == sub[-1][2]:
                sub.append(entry)
            else:
                final.append(sub)
                sub = [entry]
        final.append(sub)

    # Step 3: filter segments where OA != PO
    rows = []
    for seg in final:
        oa_date = seg[0][1]
        po_date = seg[0][2]
        if oa_date == po_date:
            continue
        lines = [e[0] for e in seg]
        if len(lines) == 1:
            label = f"Line {lines[0]}"
        else:
            label = f"Lines {lines[0]}–{lines[-1]}"
        rows.append([label, oa_date, po_date])

    return pd.DataFrame(rows, columns=[
        'Line(s)', 'OA Expected Dates', 'Factory PO requested dates'
    ])
