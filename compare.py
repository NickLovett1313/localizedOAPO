import fitz  # PyMuPDF
import pandas as pd
import difflib

def load_pdf(uploaded_file, is_po=True):
    # Open PDF with PyMuPDF
    doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
    text = ""
    for page in doc:
        text += page.get_text()

    # Split text into lines
    lines = text.split('\n')

    extracted = []
    for idx, line in enumerate(lines):
        parts = line.strip().split()
        if len(parts) >= 5 and parts[0].isdigit():
            try:
                # Example: 00010 702DX... Jul 8, 2025 3 EA 2,205.33 6,615.99
                line_no = parts[0]
                model = parts[1]
                ship_date = " ".join(parts[2:5]) if ',' in parts[3] else parts[2]
                qty = parts[-4]
                unit_price = parts[-2].replace(',', '')
                total_price = parts[-1].replace(',', '')
                extracted.append([line_no, model, ship_date, qty, unit_price, total_price])
            except:
                pass  # skip lines that break

    if is_po:
        df = pd.DataFrame(extracted, columns=['Line No.', 'Description', 'Requested Ship Date', 'Qty', 'Unit Price', 'Extended Price'])
        df['PURCHASE ORDER #'] = get_po_number(lines)
    else:
        df = pd.DataFrame(extracted, columns=['Cust Line No', 'Description', 'Expected Ship Date', 'Qty', 'Unit Price', 'Total Amount'])
        df['Customer PO No'] = get_po_number(lines)

    return df

def get_po_number(lines):
    for line in lines:
        if 'PO Number' in line or 'PURCHASE ORDER #' in line or 'Customer PO No:' in line:
            return ''.join(filter(str.isdigit, line))
    return 'UNKNOWN'

def validate_po_number(po_df, oa_df):
    po_number = po_df['PURCHASE ORDER #'].iloc[0]
    oa_po_number = oa_df['Customer PO No'].iloc[0]
    if po_number != oa_po_number:
        return False, f"PO Number mismatch: PO={po_number} OA={oa_po_number}"
    return True, po_number

def compare_lines(po_df, oa_df):
    discrepancies = []
    weird_flags = []

    for line in po_df['Line No.'].unique():
        po_line = po_df[po_df['Line No.'] == line]
        oa_line = oa_df[oa_df['Cust Line No'] == line]

        if oa_line.empty:
            discrepancies.append(f"Line {line} in PO not found in OA.")
            continue

        # ✅ Safe qty check
        po_qtys = pd.to_numeric(po_line['Qty'], errors='coerce')
        oa_qtys = pd.to_numeric(oa_line['Qty'], errors='coerce')
        po_qty = po_qtys.sum()
        oa_qty = oa_qtys.sum()

        if pd.isna(po_qty) or pd.isna(oa_qty):
            discrepancies.append(f"⚠️ Weird Issue: Non-numeric Qty for Line {line} — check manually")
        elif po_qty != oa_qty:
            discrepancies.append(f"Qty mismatch for Line {line}: PO={po_qty}, OA={oa_qty}")

        # ✅ Model #
        po_model = po_line['Description'].iloc[0]
        oa_model = oa_line['Description'].iloc[0]
        if po_model != oa_model:
            diff = list(difflib.ndiff(po_model, oa_model))
            diff_text = '\n'.join(diff)
            discrepancies.append(f"Model # mismatch for Line {line}:\n{diff_text}")

    # ✅ Extra lines in OA
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
