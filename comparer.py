import pandas as pd
import difflib

def compare_oa_po(oa_df, po_df):
    messages = []
    date_discrepancies = []

    # Normalize line numbers (strip leading zeros)
    oa_df['Line No'] = oa_df['Line No'].astype(str).str.lstrip('0')
    po_df['Line No'] = po_df['Line No'].astype(str).str.lstrip('0')

    # Drop blank lines (but keep ORDER TOTAL and tariff rows)
    def is_valid_line(df):
        return (df['Model Number'].fillna('') != '') | (df['Total Price'].fillna('') != '')
    oa_df = oa_df[is_valid_line(oa_df)].copy()
    po_df = po_df[is_valid_line(po_df)].copy()

    # Set index by Line No for easier matching
    oa_indexed = oa_df.set_index('Line No')
    po_indexed = po_df.set_index('Line No')

    all_lines = sorted(set(oa_indexed.index).union(po_indexed.index), key=lambda x: int(x) if x.isdigit() else 99999)

    discrepancy_rows = []

    for line in all_lines:
        oa_row = oa_indexed.loc[line] if line in oa_indexed.index else None
        po_row = po_indexed.loc[line] if line in po_indexed.index else None

        # Missing lines
        if oa_row is None:
            discrepancy_rows.append([line, "Missing from OA", "", "Exists in PO"])
            continue
        if po_row is None:
            if "TARIFF" in str(oa_row['Model Number']).upper():
                tariff_amt = oa_row['Total Price']
                discrepancy_rows.append([line, "TARIFF line exists in OA but is missing from PO", "", f"Amount: ${tariff_amt}"])
            else:
                discrepancy_rows.append([line, "Exists in OA", "", "Missing from PO"])
            continue

        # Normalize comparison values
        def norm(val): return str(val).strip()

        # Model mismatch
        if norm(oa_row['Model Number']) != norm(po_row['Model Number']):
            diff = '\n'.join(difflib.ndiff([norm(po_row['Model Number'])], [norm(oa_row['Model Number'])]))
            discrepancy_rows.append([line, "Model Number", norm(po_row['Model Number']), norm(oa_row['Model Number'])])

        # Quantity
        if norm(oa_row['Qty']) != norm(po_row['Qty']):
            discrepancy_rows.append([line, "Quantity", norm(po_row['Qty']), norm(oa_row['Qty'])])

        # Unit Price
        if norm(oa_row['Unit Price']) != norm(po_row['Unit Price']):
            discrepancy_rows.append([line, "Unit Price", norm(po_row['Unit Price']), norm(oa_row['Unit Price'])])

        # Total Price
        if norm(oa_row['Total Price']) != norm(po_row['Total Price']):
            discrepancy_rows.append([line, "Total Price", norm(po_row['Total Price']), norm(oa_row['Total Price'])])

        # Ship Date
        if norm(oa_row['Ship Date']) != norm(po_row['Ship Date']):
            date_discrepancies.append((line, norm(oa_row['Ship Date']), norm(po_row['Ship Date'])))

        # Calibration mismatch
        if norm(oa_row['Calib Details']) != norm(po_row['Calib Details']):
            discrepancy_rows.append([line, "Calibration", norm(po_row['Calib Details']), norm(oa_row['Calib Details'])])

        # Tags match logic
        oa_tags = sorted([t.strip() for t in str(oa_row['Tags']).split(',') if t.strip()])
        oa_wire_tags = sorted([t.strip() for t in str(oa_row['Wire-on Tag']).split(',') if t.strip()])
        po_tags = sorted([t.strip() for t in str(po_row['Tags']).split(',') if t.strip()])

        # Check for mismatched wire-on tag alignment
        if oa_tags and oa_wire_tags:
            unmatched_wire_tags = [t for t in oa_wire_tags if t not in oa_tags]
            if unmatched_wire_tags:
                discrepancy_rows.append([line, "Wire-on Tag mismatch", "", f"Missing: {', '.join(unmatched_wire_tags)}"])

        # Tag presence logic (PO tags *must* appear exact # of times in OA tags)
        tag_mismatch = False
        for tag in po_tags:
            expected_count = po_tags.count(tag)
            actual_count = oa_tags.count(tag)
            if actual_count < expected_count:
                tag_mismatch = True
                discrepancy_rows.append([line, f"Tag mismatch ({tag})", f"Expected {expected_count}", f"Found {actual_count}"])

    # Order total mismatch (check if tariff explains it)
    oa_total = oa_df[oa_df['Model Number'] == 'ORDER TOTAL']['Total Price'].values
    po_total = po_df[po_df['Model Number'] == 'ORDER TOTAL']['Total Price'].values

    if oa_total and po_total and norm(oa_total[0]) != norm(po_total[0]):
        oa_val = float(oa_total[0].replace(',', ''))
        po_val = float(po_total[0].replace(',', ''))
        tariff_rows = oa_df[oa_df['Model Number'].str.upper().str.contains("TARIFF", na=False)]
        tariff_amt = sum([float(t.replace(',', '')) for t in tariff_rows['Total Price'] if t.strip().replace(',', '').replace('.', '').isdigit()])
        if abs(oa_val - po_val - tariff_amt) < 0.01:
            discrepancy_rows.append(['', 'ORDER TOTAL', f"${po_val:,.2f}", f"${oa_val:,.2f} (**note that the order total differs by exactly the amount of the tariff charge**)"])
        else:
            discrepancy_rows.append(['', 'ORDER TOTAL', f"${po_val:,.2f}", f"${oa_val:,.2f}"])

    # Build summary message
    summary_text = (
        "I have reviewed the OA and Factory PO for this order and found the following discrepancies:"
        if discrepancy_rows or date_discrepancies
        else "I have reviewed the OA and Factory PO for this order and found **no discrepancies**. Everything else looked good."
    )

    summary_df = pd.DataFrame(discrepancy_rows, columns=["Line", "Field", "PO Value", "OA Value"]) if discrepancy_rows else pd.DataFrame()

    return summary_text, summary_df, build_date_table(date_discrepancies)


def build_date_table(date_discrepancies):
    from collections import defaultdict

    grouped = defaultdict(list)
    for line, oa_date, po_date in date_discrepancies:
        key = (oa_date, po_date)
        grouped[key].append(int(line) if line.isdigit() else 99999)

    rows = []
    for (oa_date, po_date), line_nums in grouped.items():
        line_nums.sort()
        if len(line_nums) == 1:
            line_label = f"Line {line_nums[0]}"
        else:
            line_label = f"Lines {line_nums[0]}–{line_nums[-1]}"
        rows.append((line_label, oa_date, po_date))

    df = pd.DataFrame(rows, columns=["Line(s)", "OA Expected Dates", "Factory PO requested dates"])
    return df
