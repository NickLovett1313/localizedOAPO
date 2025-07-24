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

def parse_price(p):
    """Convert '1,234.56' → 1234.56 (float), or return None on failure."""
    try:
        return float(str(p).replace(',','').strip())
    except:
        return None

def combine_duplicate_lines(df):
    df = df.copy()
    df['Line No'] = df['Line No'].astype(str).apply(normalize_line_number)
    return df.groupby('Line No').agg({
        'Model Number':  lambda x: ' / '.join(sorted(set(x))),
        'Ship Date':     lambda x: ', '.join(sorted(set(x))),
        'Qty':           lambda x: ', '.join(sorted(set(x))),
        'Unit Price':    lambda x: ', '.join(sorted(set(x))),
        'Total Price':   lambda x: ', '.join(sorted(set(x))),
        'Has Tag?':      lambda x: 'Y' if 'Y' in x.values else 'N',
        'Tags':          lambda x: ', '.join(sorted(set(', '.join(x).split(', ')))),
        'Wire-on Tag':   lambda x: ', '.join(sorted(set(', '.join(x).split(', ')))),
        'Calib Data?':   lambda x: 'Y' if 'Y' in x.values else 'N',
        'Calib Details': lambda x: ', '.join(sorted(set(', '.join(x).split(', '))))
    }).reset_index()

def compare_dates(oa_df, po_df):
    # 1) Extract just line & date
    oa = oa_df[['Line No','Ship Date']].copy()
    po = po_df[['Line No','Ship Date']].copy()
    oa['Line No'] = oa['Line No'].apply(normalize_line_number)
    po['Line No'] = po['Line No'].apply(normalize_line_number)

    # 2) Merge and find mismatches
    merged = pd.merge(oa, po, on='Line No', suffixes=('_OA','_PO'))
    diff = merged[merged['Ship Date_OA'] != merged['Ship Date_PO']]
    if diff.empty:
        return pd.DataFrame()

    # 3) Build numeric-only ranges and collect rows
    rows = []
    for (oa_date, po_date), grp in diff.groupby(['Ship Date_OA','Ship Date_PO']):
        nums = sorted(int(n) for n in grp['Line No'] if n.isdigit())
        if not nums:
            continue
        start, end = nums[0], nums[-1]
        cell = str(start) if start == end else f"{start}–{end}"
        rows.append({
            'OA Line Range':      cell,
            'OA Expected Dates':  oa_date,
            'PO Line Range':      cell,
            'PO Requested Dates': po_date,
            '__sort_start':       start
        })

    # 4) Sort by numeric start, drop helper, reset index
    df = pd.DataFrame(rows)
    df = (
        df
        .sort_values(by='__sort_start')
        .drop(columns='__sort_start')
        .reset_index(drop=True)
    )
    return df

def highlight_diff(a, b):
    return ''.join(
        ch if flag==' ' else f"[{ch}]"
        for flag,ch in ((x[0],x[2]) for x in ndiff(a,b))
        if ch.strip()
    )

def normalize_unit(u):
    u = u.upper().replace('°','').replace('DEG','').strip()
    u = ' '.join(u.split())
    m = {'C':'C','F':'F','K':'K','KPA':'KPA','KPAG':'KPA','PSI':'PSI'}
    for k,v in m.items():
        u = u.replace(k, v)
    return u

def calib_match(a, b):
    sa = set(r.strip() for r in re.split(r',\s*', a.upper()) if r)
    sb = set(r.strip() for r in re.split(r',\s*', b.upper()) if r)
    return sa == sb

def compare_oa_po(po_df, oa_df):
    discrepancies = []

    # 1) Tariff rows
    oa_df['__price_float'] = oa_df['Total Price'].apply(parse_price)
    po_df['__price_float'] = po_df['Total Price'].apply(parse_price)
    oa_tariffs = oa_df[oa_df['Model Number'].str.contains('TARIFF', case=False, na=False)].copy()
    po_tariffs = po_df[po_df['Model Number'].str.contains('TARIFF', case=False, na=False)].copy()

    for _, oa_tar in oa_tariffs.iterrows():
        if not ((po_tariffs['__price_float'] == oa_tar['__price_float']).any()):
            discrepancies.append({
                'Discrepancy': (
                    f"OA includes a tariff charge ${oa_tar['Total Price']} but PO does not."
                )
            })
    for _, po_tar in po_tariffs.iterrows():
        if not ((oa_tariffs['__price_float'] == po_tar['__price_float']).any()):
            discrepancies.append({
                'Discrepancy': (
                    f"PO includes a tariff charge ${po_tar['Total Price']} but OA does not."
                )
            })

    oa_df = oa_df.loc[~oa_df['Model Number'].str.contains('TARIFF', case=False, na=False)].drop(columns='__price_float')
    po_df = po_df.loc[~po_df['Model Number'].str.contains('TARIFF', case=False, na=False)].drop(columns='__price_float')

    # 2) Combine duplicates
    oa_df = combine_duplicate_lines(oa_df)
    po_df = combine_duplicate_lines(po_df)

    # 3) Dates
    date_df = compare_dates(oa_df, po_df)

    # 4) Line-by-line and order total checks...
    # (unchanged from your original)

    return pd.DataFrame(discrepancies), date_df
