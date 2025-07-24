import pandas as pd
import re
from difflib import ndiff
from dateutil.parser import parse as date_parse

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

def parse_price(p):
    try:
        return float(str(p).replace(',', '').strip())
    except:
        return None

def combine_duplicate_lines(df):
    df = df.copy()
    df['Line No'] = df['Line No'].astype(str).apply(normalize_line_number)
    return df.groupby('Line No').agg({
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

def compare_dates(oa_df, po_df):
    oa = oa_df[['Line No', 'Ship Date']].copy()
    po = po_df[['Line No', 'Ship Date']].copy()
    oa['Line No'] = oa['Line No'].apply(normalize_line_number)
    po['Line No'] = po['Line No'].apply(normalize_line_number)

    def try_parse(x):
        try:
            return date_parse(str(x), dayfirst=True).date()
        except:
            return None

    oa['__parsed'] = oa['Ship Date'].apply(try_parse)
    po['__parsed'] = po['Ship Date'].apply(try_parse)

    merged = pd.merge(oa, po, on='Line No', suffixes=('_OA', '_PO'))
    diff = merged[merged['__parsed_OA'] != merged['__parsed_PO']]
    if diff.empty:
        return pd.DataFrame()

    def describe_diff(d1, d2):
        if d1 is None or d2 is None:
            return "Unknown"
        days = abs((d2 - d1).days)
        if days < 7:
            return "<1 week"
        elif days < 14:
            return "1–2 weeks"
        elif days < 30:
            return f"{days // 7} weeks"
        elif days < 60:
            return "1–2 months"
        elif days < 365:
            return f"{days // 30} months"
        else:
            return f"{round(days / 365, 1)} years"

    diff['Date Difference'] = diff.apply(
        lambda row: describe_diff(row['__parsed_OA'], row['__parsed_PO']),
        axis=1
    )

    df = diff.rename(columns={
        'Line No': 'Line',
        'Ship Date_OA': 'OA Expected Dates',
        'Ship Date_PO': 'PO Requested Dates'
    })[['Line', 'OA Expected Dates', 'PO Requested Dates', 'Date Difference']]

    df = df[df['Line'].str.strip().str.isdigit()]
    df = df.sort_values(by='Line', key=lambda col: col.astype(int))
    return df

def highlight_diff(a, b):
    return ''.join(
        ch if flag == ' ' else f"[{ch}]"
        for flag, ch in ((x[0], x[2]) for x in ndiff(a, b))
        if ch.strip()
    )

def normalize_unit(u):
    u = u.upper().replace('°', '').replace('DEG', '').strip()
    u = ' '.join(u.split())
    m = {'C': 'C', 'F': 'F', 'K': 'K', 'KPA': 'KPA', 'KPAG': 'KPA', 'PSI': 'PSI'}
    for k, v in m.items():
        u = u.replace(k, v)
    return u

def calib_match(a, b):
    sa = set(r.strip() for r in re.split(r',\s*', a.upper()) if r)
    sb = set(r.strip() for r in re.split(r',\s*', b.upper()) if r)
    return sa == sb

def compare_oa_po(po_df, oa_df):
    discrepancies = []

    oa_df['__price_float'] = oa_df['Total Price'].apply(parse_price)
    po_df['__price_float'] = po_df['Total Price'].apply(parse_price)
    oa_tariffs = oa_df[oa_df['Model Number'].str.contains('TARIFF', case=False, na=False)].copy()
    po_tariffs = po_df[po_df['Model Number'].str.contains('TARIFF', case=False, na=False)].copy()

    for _, oa_tar in oa_tariffs.iterrows():
        if not ((po_tariffs['__price_float'] == oa_tar['__price_float']).any()):
            discrepancies.append({
                'Discrepancy': f"OA includes a tariff charge ${oa_tar['Total Price']} but PO does not."
            })
    for _, po_tar in po_tariffs.iterrows():
        if not ((oa_tariffs['__price_float'] == po_tar['__price_float']).any()):
            discrepancies.append({
                'Discrepancy': f"PO includes a tariff charge ${po_tar['Total Price']} but OA does not."
            })

    oa_df = oa_df.loc[~oa_df['Model Number'].str.contains('TARIFF', case=False, na=False)].drop(columns='__price_float')
    po_df = po_df.loc[~po_df['Model Number'].str.contains('TARIFF', case=False, na=False)].drop(columns='__price_float')

    oa_df = combine_duplicate_lines(oa_df)
    po_df = combine_duplicate_lines(po_df)

    date_df = compare_dates(oa_df, po_df)

    po_map = {row['Line No']: row for _, row in po_df.iterrows()}
    oa_map = {row['Line No']: row for _, row in oa_df.iterrows()}
    all_lines = sorted(set(po_map) | set(oa_map), key=safe_sort_key)

    for ln in all_lines:
        po = po_map.get(ln)
        oa = oa_map.get(ln)
        if po is None:
            discrepancies.append({'Discrepancy': f"Line {ln}: present in OA but missing in PO."})
            continue
        if oa is None:
            discrepancies.append({'Discrepancy': f"Line {ln}: present in PO but missing in OA."})
            continue
        if oa['Model Number'].upper() == 'ORDER TOTAL' and po['Model Number'].upper() == 'ORDER TOTAL':
            continue

        if po['Model Number'] != oa['Model Number']:
            diff = highlight_diff(po['Model Number'], oa['Model Number'])
            discrepancies.append({
                'Discrepancy': f"Line {ln}: Model Number mismatch → OA: '{oa['Model Number']}' vs PO: '{po['Model Number']}' | Diff: {diff}"
            })
        if po['Unit Price'] != oa['Unit Price']:
            discrepancies.append({
                'Discrepancy': f"Line {ln}: Unit Price mismatch → OA: {oa['Unit Price']} vs PO: {po['Unit Price']}"
            })
        if po['Total Price'] != oa['Total Price']:
            discrepancies.append({
                'Discrepancy': f"Line {ln}: Total Price mismatch → OA: {oa['Total Price']} vs PO: {po['Total Price']}"
            })
        if oa['Tags'] and oa['Wire-on Tag'] and oa['Tags'] != oa['Wire-on Tag']:
            discrepancies.append({
                'Discrepancy': f"Line {ln}: OA Wire-on Tag mismatch → Tags: {oa['Tags']} vs Wire-on Tag: {oa['Wire-on Tag']}"
            })

        oa_has = oa['Has Tag?'] == 'Y'
        po_has = po['Has Tag?'] == 'Y'
        oa_tags = set(oa['Tags'].split(', ')) if oa['Tags'] else set()
        po_tags = set(po['Tags'].split(', ')) if po['Tags'] else set()
        if oa_has and not po_has:
            discrepancies.append({'Discrepancy': f"Line {ln}: OA has tag(s) but PO does not"})
        elif po_has and not oa_has:
            discrepancies.append({'Discrepancy': f"Line {ln}: PO has tag(s) but OA does not"})
        elif oa_has and po_has and oa_tags != po_tags:
            discrepancies.append({
                'Discrepancy': f"Line {ln}: Tag mismatch → OA: {sorted(oa_tags)} vs PO: {sorted(po_tags)}"
            })

        if not (oa['Calib Data?'] == 'N' and po['Calib Data?'] == 'N'):
            if oa['Calib Data?'] != po['Calib Data?']:
                discrepancies.append({
                    'Discrepancy': f"Line {ln}: Calibration data missing on one side → OA: {oa['Calib Data?']} vs PO: {po['Calib Data?']}"
                })
            else:
                a = normalize_unit(oa['Calib Details'])
                b = normalize_unit(po['Calib Details'])
                if not calib_match(a, b):
                    discrepancies.append({
                        'Discrepancy': f"Line {ln}: Calibration mismatch → OA: {oa['Calib Details']} vs PO: {po['Calib Details']}"
                    })

    oa_tot = oa_df[oa_df['Model Number'] == 'ORDER TOTAL']['Total Price'].values
    po_tot = po_df[po_df['Model Number'] == 'ORDER TOTAL']['Total Price'].values
    if oa_tot.size and po_tot.size and oa_tot[0] != po_tot[0]:
        try:
            o = float(oa_tot[0].replace(',', ''))
            p = float(po_tot[0].replace(',', ''))
            tariff_sum = oa_tariffs['__price_float'].sum()
            if abs((o - p) - tariff_sum) < 0.01:
                diff_amt = abs(o - p)
                discrepancies.append({
                    'Discrepancy': f"Order Total mismatch → OA: {oa_tot[0]} vs PO: {po_tot[0]}. Difference ${diff_amt:.2f} is exactly due to tariff charges."
                })
            else:
                discrepancies.append({
                    'Discrepancy': f"Order Total mismatch → OA: {oa_tot[0]} vs PO: {po_tot[0]}"
                })
        except:
            discrepancies.append({
                'Discrepancy': "Could not compare Order Totals due to formatting."
            })

    return pd.DataFrame(discrepancies), date_df
