import pandas as pd
import re
from difflib import ndiff

def normalize_line_number(ln):
    try:
        return str(int(str(ln).strip()))
    except:
        return str(ln).strip()

def safe_sort_key(x):
    try:
        return int(x)
    except:
        return float('inf')

def combine_duplicate_lines(df):
    df['Line No'] = df['Line No'].astype(str).apply(normalize_line_number)
    df = df.groupby('Line No').agg({
        'Model Number': lambda x: ' / '.join(sorted(set(x))),
        'Ship Date': lambda x: ', '.join(sorted(set(x))),
        'Qty': lambda x: ', '.join(sorted(set(x))),
        'Unit Price': lambda x: ', '.join(sorted(set(x))),
        'Total Price': lambda x: ', '.join(sorted(set(x))),
        'Has Tag?': lambda x: 'Y' if 'Y' in x.values else 'N',
        'Tags': lambda x: ', '.join(sorted(set(', '.join(x).split(', ')))),
        'Wire-on Tag': lambda x: ', '.join(sorted(set(', '.join(x).split(', ')))),
        'Calib Data?': lambda x: 'Y' if 'Y' in x.values else 'N',
        'Calib Details': lambda x: ', '.join(sorted(set(', '.join(x).split(', '))))
    }).reset_index()
    return df

def compare_dates(oa_df, po_df):
    date_issues = []

    oa_ship = oa_df[['Line No', 'Ship Date']].copy()
    po_ship = po_df[['Line No', 'Ship Date']].copy()

    oa_ship['Line No'] = oa_ship['Line No'].apply(normalize_line_number)
    po_ship['Line No'] = po_ship['Line No'].apply(normalize_line_number)

    merged = pd.merge(oa_ship, po_ship, on='Line No', suffixes=('_OA', '_PO'))
    merged = merged[merged['Ship Date_OA'] != merged['Ship Date_PO']]

    if merged.empty:
        return pd.DataFrame()

    groups = merged.groupby(['Ship Date_OA', 'Ship Date_PO'])

    for (oa_date, po_date), group in groups:
        lines = sorted(int(x) for x in group['Line No'] if x.isdigit())
        if not lines:
            continue
        line_range = f"Line {lines[0]}" if len(lines) == 1 else f"Lines {lines[0]}–{lines[-1]}"
        date_issues.append({
            'OA Line Range': line_range,
            'OA Expected Dates': oa_date,
            'PO Line Range': line_range,
            'PO Requested Dates': po_date
        })

    return pd.DataFrame(date_issues)

def highlight_diff(a, b):
    return ''.join(x[2] if x[0] == ' ' else f"[{x[2]}]" for x in ndiff(a, b) if x[2].strip())

def normalize_unit(unit):
    unit = unit.upper().replace('°', '').replace('DEG', '').strip()
    mapping = {'C': 'C', 'F': 'F', 'K': 'K', 'KPA': 'KPA', 'KPAG': 'KPA', 'PSI': 'PSI'}
    for key in mapping:
        unit = unit.replace(key, mapping[key])
    return unit

def calib_match(a, b):
    def parse_ranges(s):
        return set([r.strip() for r in re.split(r',\s*', s.upper()) if r])
    set_a = parse_ranges(a)
    set_b = parse_ranges(b)
    return set_a == set_b

def compare_oa_po(po_df, oa_df):
    discrepancies = []

    # Normalize and group
    po_df = combine_duplicate_lines(po_df)
    oa_df = combine_duplicate_lines(oa_df)

    po_map = {normalize_line_number(r['Line No']): r for _, r in po_df.iterrows()}
    oa_map = {normalize_line_number(r['Line No']): r for _, r in oa_df.iterrows()}

    date_df = compare_dates(oa_df, po_df)

    all_lines = sorted(set(po_map.keys()) | set(oa_map.keys()), key=safe_sort_key)

    for ln in all_lines:
        po_row = po_map.get(ln)
        oa_row = oa_map.get(ln)

        if po_row is None:
            discrepancies.append({'Discrepancy': f"Line {ln} is present in OA but missing in PO."})
            continue
        if oa_row is None:
            discrepancies.append({'Discrepancy': f"Line {ln} is present in PO but missing in OA."})
            continue

        # ───── TARIFF LOGIC ─────
        oa_model = oa_row['Model Number'].upper()
        po_model = po_row['Model Number'].upper()
        is_oa_tariff = 'TARIFF' in oa_model
        is_po_tariff = 'TARIFF' in po_model

        if is_oa_tariff:
            if not is_po_tariff:
                discrepancies.append({
                    'Discrepancy': f"Line {ln}: OA includes a tariff charge but PO does not."
                })
                continue
            else:
                if po_row['Total Price'] != oa_row['Total Price']:
                    discrepancies.append({
                        'Discrepancy': f"Line {ln}: Tariff price mismatch → OA: {oa_row['Total Price']} vs PO: {po_row['Total Price']}"
                    })
                continue  # Skip other checks for tariff lines

        # ───── Model Number ─────
        if po_row['Model Number'] != oa_row['Model Number']:
            a, b = po_row['Model Number'], oa_row['Model Number']
            diff = highlight_diff(a, b)
            discrepancies.append({
                'Discrepancy': f"Line {ln}: Model Number mismatch → OA: '{a}' vs PO: '{b}' | Diff: {diff}"
            })

        # ───── Prices ─────
        if po_row['Unit Price'] != oa_row['Unit Price']:
            discrepancies.append({
                'Discrepancy': f"Line {ln}: Unit Price mismatch → OA: {oa_row['Unit Price']} vs PO: {po_row['Unit Price']}"
            })
        if po_row['Total Price'] != oa_row['Total Price']:
            discrepancies.append({
                'Discrepancy': f"Line {ln}: Total Price mismatch → OA: {oa_row['Total Price']} vs PO: {po_row['Total Price']}"
            })

        # ───── Wire-on Tag mismatch ─────
        if oa_row['Tags'] and oa_row['Wire-on Tag'] and oa_row['Tags'] != oa_row['Wire-on Tag']:
            discrepancies.append({
                'Discrepancy': f"Line {ln}: OA Wire-on Tag mismatch → 'Tags': {oa_row['Tags']} vs 'Wire-on Tag': {oa_row['Wire-on Tag']}"
            })

        # ───── Tag Comparison ─────
        oa_has_tags = oa_row['Has Tag?'] == 'Y'
        po_has_tags = po_row['Has Tag?'] == 'Y'
        oa_tags = set(oa_row['Tags'].split(', ')) if oa_row['Tags'] else set()
        po_tags = set(po_row['Tags'].split(', ')) if po_row['Tags'] else set()

        if oa_has_tags and not po_has_tags:
            discrepancies.append({
                'Discrepancy': f"Line {ln}: OA has tag(s) but PO does not"
            })
        elif po_has_tags and not oa_has_tags:
            discrepancies.append({
                'Discrepancy': f"Line {ln}: PO has tag(s) but OA does not"
            })
        elif oa_has_tags and po_has_tags and oa_tags != po_tags:
            discrepancies.append({
                'Discrepancy': f"Line {ln}: Tag mismatch → OA: {sorted(oa_tags)} vs PO: {sorted(po_tags)}"
            })

        # ───── Calibration Comparison ─────
        if po_row['Calib Data?'] == 'N' and oa_row['Calib Data?'] == 'N':
            pass
        elif po_row['Calib Data?'] != oa_row['Calib Data?']:
            discrepancies.append({
                'Discrepancy': f"Line {ln}: Calibration data missing on one side → OA: {oa_row['Calib Data?']} vs PO: {po_row['Calib Data?']}"
            })
        else:
            a = normalize_unit(oa_row['Calib Details'])
            b = normalize_unit(po_row['Calib Details'])
            if not calib_match(a, b):
                discrepancies.append({
                    'Discrepancy': f"Line {ln}: Calibration mismatch → OA: {oa_row['Calib Details']} vs PO: {po_row['Calib Details']}"
                })

    # ───── Order Total Check ─────
    oa_total = oa_df[oa_df['Model Number'] == 'ORDER TOTAL']['Total Price'].values
    po_total = po_df[po_df['Model Number'] == 'ORDER TOTAL']['Total Price'].values

    if oa_total.size > 0 and po_total.size > 0 and oa_total[0] != po_total[0]:
        try:
            oa_val = float(oa_total[0].replace(',', ''))
            po_val = float(po_total[0].replace(',', ''))

            # Check if tariff explains it
            tariff_rows = oa_df[oa_df['Model Number'].str.contains('TARIFF', case=False, na=False)]
            tariff_total = tariff_rows['Total Price'].apply(lambda x: float(x.replace(',', ''))).sum()

            if abs((oa_val - po_val) - tariff_total) < 0.01:
                discrepancies.append({
                    'Discrepancy': "Order Total differs, but the difference is exactly due to the tariff charge amount."
                })
            else:
                discrepancies.append({
                    'Discrepancy': f"Order Total mismatch → OA: {oa_total[0]} vs PO: {po_total[0]}"
                })
        except:
            discrepancies.append({'Discrepancy': "Could not compare Order Totals due to formatting."})

    return pd.DataFrame(discrepancies), date_df
