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
    oa = oa_df[['Line No','Ship Date']].copy()
    po = po_df[['Line No','Ship Date']].copy()
    oa['Line No'] = oa['Line No'].apply(normalize_line_number)
    po['Line No'] = po['Line No'].apply(normalize_line_number)
    merged = pd.merge(oa, po, on='Line No', suffixes=('_OA','_PO'))
    diff = merged[merged['Ship Date_OA'] != merged['Ship Date_PO']]
    if diff.empty:
        return pd.DataFrame()
    issues = []
    for (d_oa, d_po), grp in diff.groupby(['Ship Date_OA','Ship Date_PO']):
        nums = sorted(int(n) for n in grp['Line No'] if n.isdigit())
        if not nums:
            continue
        rng = f"Line {nums[0]}" if len(nums) == 1 else f"Lines {nums[0]}–{nums[-1]}"
        issues.append({
            'OA Line Range':       rng,
            'OA Expected Dates':   d_oa,
            'PO Line Range':       rng,
            'PO Requested Dates':  d_po
        })
    return pd.DataFrame(issues)

def highlight_diff(a, b):
    return ''.join(
        ch if flag == ' ' else f"[{ch}]"
        for flag, ch in ((x[0], x[2]) for x in ndiff(a, b))
        if ch.strip()
    )

def normalize_unit(u):
    u = u.upper().replace('°', '').replace('DEG', '').strip()
    m = {'C':'C','F':'F','K':'K','KPA':'KPA','KPAG':'KPA','PSI':'PSI'}
    for k, v in m.items():
        u = u.replace(k, v)
    return u

def calib_match(a, b):
    sa = set(r.strip() for r in re.split(r',\s*', a.upper()) if r)
    sb = set(r.strip() for r in re.split(r',\s*', b.upper()) if r)
    return sa == sb

def compare_oa_po(po_df, oa_df):
    disc = []

    # Normalize & combine duplicates
    po_df = combine_duplicate_lines(po_df)
    oa_df = combine_duplicate_lines(oa_df)

    po_map = {normalize_line_number(r['Line No']): r for _, r in po_df.iterrows()}
    oa_map = {normalize_line_number(r['Line No']): r for _, r in oa_df.iterrows()}

    date_df = compare_dates(oa_df, po_df)
    lines = sorted(set(po_map) | set(oa_map), key=safe_sort_key)

    for ln in lines:
        po = po_map.get(ln)
        oa = oa_map.get(ln)

        if po is None:
            disc.append({'Discrepancy': f"Line {ln} is present in OA but missing in PO."})
            continue
        if oa is None:
            disc.append({'Discrepancy': f"Line {ln} is present in PO but missing in OA."})
            continue

        # Skip ORDER TOTAL lines
        if "ORDER TOTAL" in oa['Model Number'].upper() or "ORDER TOTAL" in po['Model Number'].upper():
            continue

        # ─── Explicit TARIFF Rule ───
        oa_m = oa['Model Number'].upper()
        po_m = po['Model Number'].upper()
        if "TARIFF" in oa_m:
            if "TARIFF" not in po_m:
                disc.append({'Discrepancy': f"Line {ln}: OA includes a tariff charge but PO does not."})
            else:
                if po['Total Price'] != oa['Total Price']:
                    disc.append({
                        'Discrepancy': f"Line {ln}: Tariff price mismatch → OA: {oa['Total Price']} vs PO: {po['Total Price']}"
                    })
            continue  # skip all further checks for tariff lines

        # Model Number (non-tariff)
        if po['Model Number'] != oa['Model Number']:
            a, b = po['Model Number'], oa['Model Number']
            diff = highlight_diff(a, b)
            disc.append({'Discrepancy':
                f"Line {ln}: Model Number mismatch → OA: '{b}' vs PO: '{a}' | Diff: {diff}"
            })

        # Prices
        if po['Unit Price'] != oa['Unit Price']:
            disc.append({'Discrepancy':
                f"Line {ln}: Unit Price mismatch → OA: {oa['Unit Price']} vs PO: {po['Unit Price']}"
            })
        if po['Total Price'] != oa['Total Price']:
            disc.append({'Discrepancy':
                f"Line {ln}: Total Price mismatch → OA: {oa['Total Price']} vs PO: {po['Total Price']}"
            })

        # Wire-on Tag
        if oa['Tags'] and oa['Wire-on Tag'] and oa['Tags'] != oa['Wire-on Tag']:
            disc.append({'Discrepancy':
                f"Line {ln}: OA Wire-on Tag mismatch → Tags: {oa['Tags']} vs Wire-on Tag: {oa['Wire-on Tag']}"
            })

        # Tags
        oa_has = oa['Has Tag?'] == 'Y'
        po_has = po['Has Tag?'] == 'Y'
        oa_set = set(oa['Tags'].split(', ')) if oa['Tags'] else set()
        po_set = set(po['Tags'].split(', ')) if po['Tags'] else set()

        if oa_has and not po_has:
            disc.append({'Discrepancy': f"Line {ln}: OA has tag(s) but PO does not"})
        elif po_has and not oa_has:
            disc.append({'Discrepancy': f"Line {ln}: PO has tag(s) but OA does not"})
        elif oa_has and po_has and oa_set != po_set:
            disc.append({'Discrepancy':
                f"Line {ln}: Tag mismatch → OA: {sorted(oa_set)} vs PO: {sorted(po_set)}"
            })

        # Calibration
        if not (oa['Calib Data?'] == 'N' and po['Calib Data?'] == 'N'):
            if oa['Calib Data?'] != po['Calib Data?']:
                disc.append({'Discrepancy':
                    f"Line {ln}: Calibration data missing on one side → OA: {oa['Calib Data?']} vs PO: {po['Calib Data?']}"
                })
            else:
                a = normalize_unit(oa['Calib Details'])
                b = normalize_unit(po['Calib Details'])
                if not calib_match(a, b):
                    disc.append({'Discrepancy':
                        f"Line {ln}: Calibration mismatch → OA: {oa['Calib Details']} vs PO: {po['Calib Details']}"
                    })

    # Order Total
    oa_tot = oa_df[oa_df['Model Number'] == 'ORDER TOTAL']['Total Price'].values
    po_tot = po_df[po_df['Model Number'] == 'ORDER TOTAL']['Total Price'].values
    if oa_tot.size > 0 and po_tot.size > 0 and oa_tot[0] != po_tot[0]:
        try:
            o = float(oa_tot[0].replace(',', ''))
            p = float(po_tot[0].replace(',', ''))
            tariff_sum = oa_df[oa_df['Model Number'].str.contains('TARIFF', case=False)]['Total Price'] \
                         .apply(lambda x: float(x.replace(',', ''))).sum()
            if abs((o - p) - tariff_sum) < 0.01:
                disc.append({'Discrepancy':
                    "Order Total differs, but the difference is exactly due to the tariff charge amount."
                })
            else:
                disc.append({'Discrepancy':
                    f"Order Total mismatch → OA: {oa_tot[0]} vs PO: {po_tot[0]}"
                })
        except:
            disc.append({'Discrepancy':
                "Could not compare Order Totals due to formatting."
            })

    return pd.DataFrame(disc), date_df
