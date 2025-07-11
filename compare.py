import pandas as pd
import difflib

def load_files(po_file, oa_file):
    po_df = pd.read_csv(po_file)
    oa_df = pd.read_csv(oa_file)
    return po_df, oa_df

def validate_po_number(po_df, oa_df):
    po_number = po_df['PURCHASE ORDER #'].iloc[0]
    oa_po_number = oa_df['Customer PO No'].iloc[0]
    if po_number != oa_po_number:
        return False, f"PO Number mismatch: PO={po_number} OA={oa_po_number}"
    return True, po_number

def compare_lines(po_df, oa_df):
    discrepancies = []
    weird_flags = []

    # For each unique line number in PO:
    for line in po_df['Line No.'].unique():
        po_line = po_df[po_df['Line No.'] == line]
        oa_line = oa_df[oa_df['Cust Line No'] == line]

        if oa_line.empty:
            discrepancies.append(f"Line {line} in PO not found in OA.")
            continue

        # Qty check (sum up in case of duplicates)
        po_qty = po_line['Qty'].sum()
        oa_qty = oa_line['Qty'].sum()
        if po_qty != oa_qty:
            discrepancies.append(f"Qty mismatch for Line {line}: PO={po_qty}, OA={oa_qty}")

        # Model # check
        po_model = po_line['Description'].iloc[0]
        oa_model = oa_line['Description'].iloc[0]
        if po_model != oa_model:
            diff = list(difflib.ndiff(po_model, oa_model))
            diff_text = '\n'.join(diff)
            discrepancies.append(f"Model # mismatch for Line {line}:\n{diff_text}")

    # Look for extra lines in OA
    for line in oa_df['Cust Line No'].unique():
        if line not in po_df['Line No.'].values:
            discrepancies.append(f"OA has extra line: {line}")

    return discrepancies, weird_flags

def format_report(po_number, discrepancies, weird_flags):
    report = f"Here are the discrepancies found for this OA (PO# {po_number})\n\n"
    if discrepancies:
        for idx, item in enumerate(discrepancies, 1):
            report += f"{idx}. {item}\n\n"
    else:
        report += "✅ No discrepancies found!\n"

    if weird_flags:
        for flag in weird_flags:
            report += f"⚠️ {flag}\n"

    return report
