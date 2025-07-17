# comparer.py
import pandas as pd
from collections import Counter

def compare_oa_po(po_df, oa_df):
    discrepancies = []
    date_mismatches = []

    def normalize_line_no(val):
        return str(val).lstrip('0') or '0'

    po_df['Line No'] = po_df['Line No'].astype(str).apply(normalize_line_no)
    oa_df['Line No'] = oa_df['Line No'].astype(str).apply(normalize_line_no)

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

    for line in sorted(all_lines, key=safe_sort_key):
        po_rows = po_groups.get_group(line) if line in po_groups.groups else None
        oa_rows = oa_groups.get_group(line) if line in oa_groups.groups else None

        if po_rows is not None and oa_rows is not None:
            oa_model_set = set(oa_rows['Model Number'])
            oa_qty = oa_rows['Qty'].astype(int).sum()
            oa_total = oa_rows['Total Price'].replace(',', '', regex=True).astype(float).sum()
            oa_tags = sum([clean_tags(t) for t in oa_rows['Tags']], [])
            oa_wire = sum([clean_tags(t) for t in oa_rows['Wire-on Tag']], [])
            oa_calib = set([c.strip() for c in ",".join(oa_rows['Calib Details']).split(',') if c.strip()])
            oa_ship_dates = set(oa_rows['Ship Date'])

            po_row = po_rows.iloc[0]

            if po_row['Model Number'] not in oa_model_set:
                discrepancies.append([line, 'Model Number', po_row['Model Number'], ", ".join(oa_model_set), 'Model number mismatch'])

            if int(po_row['Qty']) != oa_qty:
                discrepancies.append([line, 'Qty', po_row['Qty'], str(oa_qty), 'Quantity mismatch'])

            if float(po_row['Total Price'].replace(',', '')) != round(oa_total, 2):
                discrepancies.append([line, 'Total Price', po_row['Total Price'], f"{oa_total:,.2f}", 'Total price mismatch'])

            po_tags = clean_tags(po_row['Tags']) * int(po_row['Qty'])
            if Counter(po_tags) != Counter(oa_tags):
                discrepancies.append([line, 'Tags', f"{Counter(po_tags)}", f"{Counter(oa_tags)}", 'Tag counts do not match PO Qty'])

            if set(oa_tags) != set(oa_wire):
                discrepancies.append([line, 'OA Wire-on Mismatch', '', '', 'Tags listed do not match wire-on tag section'])

            po_calib = set([c.strip() for c in po_row['Calib Details'].split(',') if c.strip()])
            if po_calib and po_calib != oa_calib:
                discrepancies.append([line, 'Calib Details', ", ".join(po_calib), ", ".join(oa_calib), 'Calibration info mismatch'])

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

    disc_df = pd.DataFrame(discrepancies, columns=['Line No', 'Field', 'PO Value', 'OA Value', 'Comment'])
    date_df_raw = pd.DataFrame(date_mismatches, columns=['Line(s)', 'OA Expected Dates', 'Factory PO requested dates'])
    date_df = group_date_discrepancies(date_df_raw.values.tolist()) if not date_df_raw.empty else pd.DataFrame()

    return disc_df, date_df


def group_date_discrepancies(date_discrepancies):
    entries = []
    for entry in date_discrepancies:
        if not isinstance(entry, (tuple, list)) or len(entry) != 3:
            continue
        line_str, oa_date, po_date = entry
        try:
            line_num = int(''.join(filter(str.isdigit, line_str)))
        except ValueError:
            continue
        entries.append((line_num, oa_date.strip(), po_date.strip()))

    entries.sort(key=lambda x: x[0])
    grouped = []
    current_group = [entries[0][0]]
    current_oa, current_po = entries[0][1], entries[0][2]

    for i in range(1, len(entries)):
        line, oa_date, po_date = entries[i]
        if oa_date == current_oa and po_date == current_po and line == current_group[-1] + 10:
            current_group.append(line)
        else:
            grouped.append((current_group[:], current_oa, current_po))
            current_group = [line]
            current_oa, current_po = oa_date, po_date
    grouped.append((current_group[:], current_oa, current_po))

    formatted_rows = []
    for lines, oa_date, po_date in grouped:
        if len(lines) == 1:
            line_label = f"Line {lines[0]}"
        else:
            line_label = f"Lines {lines[0]}–{lines[-1]}"
        formatted_rows.append([line_label, oa_date, po_date])

    return pd.DataFrame(formatted_rows, columns=["Line(s)", "OA Expected Dates", "Factory PO requested dates"])
