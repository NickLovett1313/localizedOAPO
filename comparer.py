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
    mapping = {'C':'C','F':'F','K':'K','KPA':'KPA','KPAG':'KPA','PSI':'PSI'}
    for k, v in mapping.items():
        u = u.replace(k, v)
    return u

def calib_match(a, b):
    sa = set(r.strip() for r in re.split(r',\s*', a.upper()) if r)
    sb = set(r.strip() for r in re.split(r',\s*', b.upper()) if r)
    return sa == sb

def compare_oa_po(po_df, oa_df):
    discrepancies = []

    # Normalize and combine duplicates
    po_df = combine_duplicate_lines(po_df)
    oa_df = combine_duplicate_lines(oa_df)

    po_map = {normalize_line_number(r['Line No']): r for _, r in po_df.iterrows()}
    oa_map = {normalize_line_number(r['Line No']): r for _, r in oa_df.iterrows()}

    # 1) Date table (unchanged)
    date_df = compare_dates(oa_df, po_df)

    # 2) Iterate every line
    all_lines = sorted(set(po_map) | set(oa_map), key=safe_sort_key)
    for ln in all_lines:
        po = po_map.get(ln)
        oa = oa_map.get(ln)

        # Missing lines
        if po is None:
            discrepancies.append({'Discrepancy': f"Line {ln} is present in OA but missing in PO."})
            continue
        if oa is None:
            discrepancies.append({'Discrepancy': f"Line {ln} is present in PO but missing in OA."})
            continue

        # ─── SKIP ORDER TOTAL ───
        oa_model = oa['Model Number'].upper()
        po_model = po['Model Number'].upper()
        if "ORDER TOTAL" in oa_model or "ORDER TOTAL" in po_model:
            continue

        # ─── TARIFF RULE ───
        if "TARIFF" in oa_model:
            if "TARIFF" not in po_model:
                discrepancies.append({'Discrepancy': f"Line {ln}: OA includes a tariff charge but PO does not."})
            else:
                if po['Total Price'] != oa['Total Price']:
                    discrepancies.append({
                        'Discrepancy': f"Line {ln}: Tariff price mismatch → OA: {oa['Total Price']} vs PO: {po['Total Price']}"
                    })
            continue  # skip all other checks for tariff lines

        # ─── MODEL NUMBER ─── (only non‐tariff, non‐total)
        if po['Model Number'] != oa['Model Number']:
            a, b = po['Model Number'], oa['Model Number']
            diff = highlight_diff(a, b)
            discrepancies.append({
                'Discrepancy': f"Line {ln}: Model Number mismatch → OA: '{b}' vs PO: '{a}' | Diff: {diff}"
            })

        # ─── PRICES ───
        if po['Unit Price'] != oa['Unit Price']:
            discrepancies.append({'Discrepancy':
                f"Line {ln}: Unit Price mismatch → OA: {oa['Unit Price']} vs PO: {po['Unit Price']}"
            })
        if po['Total Price'] != oa['Total Price']:
            discrepancies.append({'Discrepancy':
                f"Line {ln}: Total Price mismatch → OA: {oa['Total Price']} vs PO: {po['Total Price']}"
            })

        # ─── WIRE‐ON TAG ───
        if oa['Tags'] and oa['Wire-on Tag'] and oa['Tags'] != oa['Wire-on Tag']:
            discrepancies.append({'Discrepancy':
                f"Line {ln}: OA Wire-on Tag mismatch → Tags: {oa['Tags']} vs Wire-on Tag: {oa['Wire-on Tag']}"
            })

        # ─── TAGS ───
        oa_has = oa['Has Tag?'] == 'Y'
        po_has = po['Has Tag?'] == 'Y'
        oa_tags = set(oa['Tags'].split(', ')) if oa['Tags'] else set()
        po_tags = set(po['Tags'].split(', ')) if po['Tags'] else set()
        if oa_has and not po_has:
            discrepancies.append({'Discrepancy': f"Line {ln}: OA has tag(s) but PO does not"})
        elif po_has and not oa_has:
            discrepancies.append({'Discrepancy': f"Line {ln}: PO has tag(s) but OA does not"})
        elif oa_has and po_has and oa_tags != po_tags:
            discrepancies.append({'Discrepancy':
                f"Line {ln}: Tag mismatch → OA: {sorted(oa_tags)} vs PO: {sorted(po_tags)}"
            })

        # ─── CALIBRATION ───
        if not (oa['Calib Data?'] == 'N' and po['Calib Data?'] == 'N'):
            if oa['Calib Data?'] != po['Calib Data?']:
                discrepancies.append({'Discrepancy':
                    f"Line {ln}: Calibration data missing on one side → OA: {oa['Calib Data?']} vs PO: {po['Calib Data?']}"
                })
            else:
                a = normalize_unit(oa['Calib Details'])
                b = normalize_unit(po['Calib Details'])
                if not calib_match(a, b):
                    discrepancies.append({'Discrepancy':
                        f"Line {ln}: Calibration mismatch → OA: {oa['Calib Details']} vs PO: {po['Calib Details']}"
                    })

    # 3) Order Total check
    oa_tot = oa_df[oa_df['Model Number'] == 'ORDER TOTAL']['Total Price'].values
    po_tot = po_df[po_df['Model Number'] == 'ORDER TOTAL']['Total Price'].values
    if oa_tot.size > 0 and po_tot.size > 0 and oa_tot[0] != po_tot[0]:
        try:
            oa_val = float(oa_tot[0].replace(',', ''))
            po_val = float(po_tot[0].replace(',', ''))
            tariff_sum = oa_df[oa_df['Model Number'].str.contains('TARIFF', case=False)]['Total Price'] \
                         .apply(lambda x: float(x.replace(',', ''))).sum()
            if abs((oa_val - po_val) - tariff_sum) < 0.01:
                discrepancies.append({'Discrepancy':
                    "Order Total differs, but the difference is exactly due to the tariff charge amount."
                })
            else:
                discrepancies.append({'Discrepancy':
                    f"Order Total mismatch → OA: {oa_tot[0]} vs PO: {po_tot[0]}"
                })
        except:
            discrepancies.append({'Discrepancy':
                "Could not compare Order Totals due to formatting."
            })

    return pd.DataFrame(discrepancies), date_df
