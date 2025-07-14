import pandas as pd
import difflib

def validate_po_number(po_df, oa_df):
    po_number = po_df['PURCHASE ORDER #'].iloc[0]
    oa_po_number = oa_df['Customer PO No'].iloc[0]
    if po_number != oa_po_number:
        return False, f"PO Number mismatch: PO={po_number} OA={oa_po_number}"
    return True, po_number

def compare_lines(po_df, oa_df):
    discrepancies = []

    for line in po_df['Line No.'].unique():
        po_line = po_df[po_df['Line No.'] == line]
        oa_line = oa_df[oa_df['Cust Line No'] == line]

        if oa_line.empty:
            discrepancies.append(f"Line {line} in PO not found in OA.")
            continue

        po_qty = pd.to_numeric(po_line['Qty'], errors='coerce').sum()
        oa_qty = pd.to_numeric(oa_line['Qty'], errors='coerce').sum()
        if po_qty != oa_qty:
            discrepancies.append(f"Qty mismatch for Line {line}: PO={po_qty} OA={oa_qty}")

        po_model = po_line['Description'].iloc[0]
        oa_model = oa_line['Description'].iloc[0]
        if po_model != oa_model:
            diff = '\n'.join(list(difflib.ndiff(po_model, oa_model)))
            discrepancies.append(f"Model # mismatch for Line {line}:\n{diff}")

    for line in oa_df['Cust Line No'].unique():
        if line not in po_df['Line No.'].values:
            discrepancies.append(f"OA has extra line: {line}")

    return discrepancies, []

def format_report(po_number, discrepancies, weird_flags):
    report = f"Discrepancies for PO# {po_number}:\n\n"
    for idx, d in enumerate(discrepancies, 1):
        report += f"{idx}. {d}\n"
    return report
