import pdfplumber
import pandas as pd
import re

def parse_po(file):
    data = []
    with pdfplumber.open(file) as pdf:
        text = "\n".join([p.extract_text() for p in pdf.pages])

    blocks = re.split(r'\n(0{3,}\d{2})', text)
    for i in range(1, len(blocks) - 1, 2):
        line_no = blocks[i]
        block = blocks[i+1]

        model = re.search(r'([A-Z0-9\-]{6,})', block)
        ship_date = re.search(r'([A-Za-z]{3} \d{1,2}, \d{4})', block)
        qty = re.search(r'(\d+) EA', block)
        unit_price = re.search(r'Unit.*?([\d,]+\.\d{2})', block)
        total_price = re.search(r'Extended.*?([\d,]+\.\d{2})', block)

        data.append({
            'Line No': int(line_no) if line_no else '',
            'Model Number': model.group(1) if model else '',
            'Ship Date': ship_date.group(1) if ship_date else '',
            'Qty': qty.group(1) if qty else '',
            'Unit Price': unit_price.group(1) if unit_price else '',
            'Total Price': total_price.group(1) if total_price else '',
        })

    return pd.DataFrame(data)


def parse_oa(file):
    data = []
    with pdfplumber.open(file) as pdf:
        text = "\n".join([p.extract_text() for p in pdf.pages])

    blocks = re.split(r'\n(000\d{2}|\d+\.\d+)', text)
    for i in range(1, len(blocks) - 1, 2):
        line_no = blocks[i]
        block = blocks[i+1]

        if '.' in line_no:
            parts = line_no.split('.')
            try:
                line_no = int(parts[0]) * 10
            except:
                line_no = ''
        else:
            try:
                line_no = int(line_no)
            except:
                line_no = ''

        model = re.search(r'([A-Z0-9\-]{6,})', block)
        ship_date = re.search(r'Expected Ship Date: (\d{2}-[A-Za-z]{3}-\d{4})', block)
        if not ship_date:
            ship_date = re.search(r'([A-Za-z]{3} \d{1,2}, \d{4})', block)

        qty = re.search(r'\n(\d+)\s+[\d,]+\.\d{2}', block)
        unit_price = re.search(r'\n\d+\s+([\d,]+\.\d{2})', block)
        total_price = re.search(r'\n\d+\s+[\d,]+\.\d{2}\s+([\d,]+\.\d{2})', block)

        data.append({
            'Line No': line_no,
            'Model Number': model.group(1) if model else '',
            'Ship Date': ship_date.group(1) if ship_date else '',
            'Qty': qty.group(1) if qty else '',
            'Unit Price': unit_price.group(1) if unit_price else '',
            'Total Price': total_price.group(1) if total_price else '',
        })

    return pd.DataFrame(data)
