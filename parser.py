
import pdfplumber
import pandas as pd
import re

def parse_pdf(file, doc_type='OA'):
    """
    Parse PO or OA PDF to extract key fields into a DataFrame.
    """
    lines_data = []

    with pdfplumber.open(file) as pdf:
        text = ""
        for page in pdf.pages:
            text += page.extract_text() + "\n"

    po_number_pattern = r'PURCHASE ORDER #[:\s]*(\\S+)' if doc_type == 'PO' else r'Customer PO No[:\s]*(\\S+)'
    po_number = re.search(po_number_pattern, text)
    po_number = po_number.group(1) if po_number else "Not Found"

    line_blocks = re.findall(r'(Line No\\.?[^L]*?)(?=Line No\\.|$)', text, re.DOTALL)

    for block in line_blocks:
        line_no = re.search(r'Line No\\.?\\s*(\\d+)', block)
        cust_line_no = re.search(r'Cust Line No\\.?\\s*(\\d+)', block)
        model = re.search(r'Description\\s*[:\\s]*(\\w[\\w\-]*)', block)
        ship_date = re.search(r'(Requested Ship Date|Expected Ship Date)[:\\s]*(\\S+)', block)
        qty = re.search(r'Qty[:\\s]*(\\d+)', block)
        unit_price = re.search(r'(Unit Price|Unit Amount)[:\\s]*([\\d\\.]+)', block)
        total_price = re.search(r'(Extended Price|Total Amount)[:\\s]*([\\d\\.]+)', block)
        tags = re.findall(r'Tag[:\\s]*(\\S+)', block)
        calibration = re.search(r'Calibration.*?(\\d+\\s*KPA)', block, re.IGNORECASE)

        lines_data.append({
            'PO Number': po_number,
            'Line No': line_no.group(1) if line_no else (cust_line_no.group(1) if cust_line_no else ''),
            'Model Number': model.group(1) if model else '',
            'Ship Date': ship_date.group(2) if ship_date else '',
            'Qty': qty.group(1) if qty else '',
            'Unit Price': unit_price.group(2) if unit_price else '',
            'Total Price': total_price.group(2) if total_price else '',
            'Tags': ', '.join(tags) if tags else '',
            'Calibration Data': calibration.group(1) if calibration else ''
        })

    df = pd.DataFrame(lines_data)
    return df
