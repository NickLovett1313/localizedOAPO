import fitz  # PyMuPDF
import re
import pandas as pd

LINE_ITEM_PATTERN = re.compile(
    r'(?P<line>\d{5})\s+'
    r'(?P<model>[A-Za-z0-9\-]+)\s+'
    r'(?P<date>\w+\s+\d{1,2},\s+\d{4})\s+'
    r'(?P<qty>\d+)\s+EA\s+'
    r'(?P<unit_price>[\d,]+\.\d+)\s+'
    r'(?P<total_price>[\d,]+\.\d+)'
)

def extract_pdf_text(uploaded_file):
    doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
    text = ""
    for page in doc:
        text += page.get_text()
    return text

def parse_line_items(text):
    matches = LINE_ITEM_PATTERN.finditer(text)
    items = []
    for m in matches:
        items.append({
            'Line': m.group('line'),
            'Model': m.group('model'),
            'Ship Date': m.group('date'),
            'Qty': m.group('qty'),
            'Unit Price': m.group('unit_price').replace(',', ''),
            'Total Price': m.group('total_price').replace(',', ''),
        })
    return items

def build_dataframe(items, po_number, is_po=True):
    if not items:
        # If no matches, return an empty DataFrame with correct columns
        if is_po:
            cols = ['Line No.', 'Description', 'Requested Ship Date', 'Qty', 'Unit Price', 'Extended Price', 'PURCHASE ORDER #']
        else:
            cols = ['Cust Line No', 'Description', 'Expected Ship Date', 'Qty', 'Unit Price', 'Total Amount', 'Customer PO No']
        return pd.DataFrame(columns=cols)
    
    df = pd.DataFrame(items)
    df['Qty'] = pd.to_numeric(df['Qty'], errors='coerce')
    df['Unit Price'] = pd.to_numeric(df['Unit Price'], errors='coerce')
    df['Total Price'] = pd.to_numeric(df['Total Price'], errors='coerce')
    
    if is_po:
        df.rename(columns={
            'Line': 'Line No.',
            'Model': 'Description',
            'Ship Date': 'Requested Ship Date',
            'Total Price': 'Extended Price'
        }, inplace=True)
        df['PURCHASE ORDER #'] = po_number
    else:
        df.rename(columns={
            'Line': 'Cust Line No',
            'Model': 'Description',
            'Ship Date': 'Expected Ship Date',
            'Total Price': 'Total Amount'
        }, inplace=True)
        df['Customer PO No'] = po_number
    
    return df

def parse_pdf(uploaded_file, is_po=True):
    text = extract_pdf_text(uploaded_file)
    po_number = get_po_number(text)
    items = parse_line_items(text)
    df = build_dataframe(items, po_number, is_po=is_po)
    return df
