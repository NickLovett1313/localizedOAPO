# ✅ parser.py — DO NOT put any import of itself in here

import pdfplumber
import pandas as pd
import re

def parse_po(file):
    data = []
    with pdfplumber.open(file) as pdf:
        text = "\n".join([p.extract_text() for p in pdf.pages])

    lines = re.split(r'\n0{3,}\d{2}', text)  # Split on 00010, 00020, etc.
    for block in lines[1:]:
        model = re.search(r'([A-Z0-9\-]{8,})', block)
        ship_date = re.search(r'([A-Za-z]{3} \d{1,2}, \d{4})', block)
        qty = re.search(r'(\d+) EA', block)
        unit_price = re.search(r'Unit.*?([\\d,]+\\.\\d{2})', block)
        total_price = re.search(r'Extended.*?([\\d,]+\\.\\d{2})', block)
        tags = re.findall(r'(SR1-\\S+)', block)

        data.append({
            'Model Number': model.group(1) if model else '',
            'Ship Date': ship_date.group(1) if ship_date else '',
            'Qty': qty.group(1) if qty else '',
            'Unit Price': unit_price.group(1) if unit_price else '',
            'Total Price': total_price.group(1) if total_price else '',
            'Tags': ", ".join(tags) if tags else ''
        })
    return pd.DataFrame(data)

def parse_oa(file):
    data = []
    with pdfplumber.open(file) as pdf:
        text = "\n".join([p.extract_text() for p in pdf.pages])

    lines = re.split(r'Cust Line No', text)
    for block in lines[1:]:
        model = re.search(r'([A-Z0-9\-]{8,})', block)
        ship_date = re.search(r'Expected Ship Date: (\\d{2}-[A-Za-z]{3}-\\d{4})', block)
        qty = re.search(r'\\n(\\d+)\\s+[\\d,]+\\.\\d{2}', block)
        unit_price = re.search(r'\\n\\d+\\s+([\\d,]+\\.\\d{2})', block)
        total_price = re.search(r'\\n\\d+\\s+[\\d,]+\\.\\d{2}\\s+([\\d,]+\\.\\d{2})', block)
        tags = re.findall(r'SR1-\\S+', block)

        data.append({
            'Model Number': model.group(1) if model else '',
            'Ship Date': ship_date.group(1) if ship_date else '',
            'Qty': qty.group(1) if qty else '',
            'Unit Price': unit_price.group(1) if unit_price else '',
            'Total Price': total_price.group(1) if total_price else '',
            'Tags': ", ".join(tags) if tags else ''
        })
    return pd.DataFrame(data)
