import pdfplumber
import pandas as pd
import re

def parse_po(file):
    data = []
    order_total = ""

    with pdfplumber.open(file) as pdf:
        text = "\n".join([p.extract_text() for p in pdf.pages])

    # Stop at Order total ($USD)
    stop_match = re.search(r'Order total.*?\$?USD?\s+([\d,]+\.\d{2})', text, re.IGNORECASE)
    if stop_match:
        order_total = stop_match.group(1)
        text = text.split(stop_match.group(0))[0]

    blocks = re.split(r'\n(0{3,}\d{2})', text)
    for i in range(1, len(blocks) - 1, 2):
        line_no = blocks[i]
        block = blocks[i+1]

        model = re.search(r'([A-Z0-9\-]{6,})', block)
        ship_date = re.search(r'([A-Za-z]{3} \d{1,2}, \d{4})', block)
        qty = re.search(r'Qty\s*.*?(\d+)', block)
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

    df = pd.DataFrame(data)
    df['Order Total'] = order_total
    return df


def parse_oa(file):
    data = []
    order_total = ""

    with pdfplumber.open(file) as pdf:
        text = "\n".join([p.extract_text() for p in pdf.pages])

    # Stop at Total (USD)
    stop_match = re.search(r'Total.*?\(USD\)\s*:\s*([\d,]+\.\d{2})', text, re.IGNORECASE)
    if stop_match:
        order_total = stop_match.group(1)
        text = text.split(stop_match.group(0))[0]

    blocks = re.split(r'\n(000\d{2}|\d+\.\d+)', text)
    for i in range(1, len(blocks) - 1, 2):
        line_no = blocks[i]
        block = blocks[i+1]

        if '.' in line_no:
            parts = line_no.split('.')
            line_no = int(parts[0]) * 10
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
        unit_price = re.search(r'Unit Price.*?USD.*?(\d+[\d,]*\.\d{2})', block, re.IGNORECASE)
        total_price = re.search(r'Total Amount.*?USD.*?(\d+[\d,]*\.\d{2})', block, re.IGNORECASE)

        data.append({
            'Line No': line_no,
            'Model Number': model.group(1) if model else '',
            'Ship Date': ship_date.group(1) if ship_date else '',
            'Qty': qty.group(1) if qty else '',
            'Unit Price': unit_price.group(1) if unit_price else '',
            'Total Price': total_price.group(1) if total_price else '',
        })

    df = pd.DataFrame(data)
    df['Order Total'] = order_total
    return df
