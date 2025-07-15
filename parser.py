import pdfplumber
import pandas as pd
import re

def extract_calib_data(lines, source='OA'):
    calib_parts = []

    valid_units = ['DEG C', 'DEG F', 'DEG K', 'KPA', 'KPAG', 'PSI', 'BAR', 'MBAR',
                   'IN H2O', 'MM H2O', 'INHG', 'TORR', 'MPA', 'MMHG', 'CM H2O']

    for idx, line in enumerate(lines):
        range_match = re.search(r'(-?\d+)\s*to\s*(-?\d+)', line)
        if range_match:
            unit = ''
            # Try to find unit on same line
            for u in valid_units:
                if u in line.upper():
                    unit = u
                    break
            # If not found, check next line
            if not unit and idx + 1 < len(lines):
                next_line = lines[idx + 1].upper().strip()
                for u in valid_units:
                    if u in next_line:
                        unit = u
                        break
            if unit:
                calib_parts.append(f"{range_match.group(1)} to {range_match.group(2)} {unit}")
            else:
                calib_parts.append(f"{range_match.group(1)} to {range_match.group(2)}")

    # Add wire config for OA if present
    wire_config = ''
    if source == 'OA':
        for l in lines:
            if re.fullmatch(r'\s*12\s*', l.strip()):
                wire_config = '2-wire RTD'
            elif re.fullmatch(r'\s*13\s*', l.strip()):
                wire_config = '3-wire RTD'
            elif re.fullmatch(r'\s*14\s*', l.strip()):
                wire_config = '4-wire RTD'
            elif '2-wire' in l.lower():
                wire_config = '2-wire RTD'
            elif '3-wire' in l.lower():
                wire_config = '3-wire RTD'
            elif '4-wire' in l.lower():
                wire_config = '4-wire RTD'
    if source == 'PO':
        # For PO, detect `3-wire RTD:` style
        for l in lines:
            if '3-wire' in l.lower():
                wire_config = '3-wire RTD'
            elif '4-wire' in l.lower():
                wire_config = '4-wire RTD'
            elif '2-wire' in l.lower():
                wire_config = '2-wire RTD'

    if wire_config:
        calib_parts.insert(0, wire_config)

    if calib_parts:
        return "Y", ", ".join(calib_parts)
    else:
        return "N", ""


def parse_po(file):
    data = []
    order_total = ""

    with pdfplumber.open(file) as pdf:
        text = "\n".join([p.extract_text() for p in pdf.pages])

    stop_match = re.search(r'Order Total.*?\$?\(?USD\)?\s*([\d,]+\.\d{2})', text, re.IGNORECASE)
    if stop_match:
        order_total = stop_match.group(1).strip()
        text = text.split(stop_match.group(0))[0]

    blocks = re.split(r'\n(0{3,}\d{2})', text)
    for i in range(1, len(blocks) - 1, 2):
        line_no = blocks[i]
        block = blocks[i+1]
        lines = block.split('\n')

        model = re.search(r'([A-Z0-9\-]{6,})', block)
        ship_date = re.search(r'([A-Za-z]{3} \d{1,2}, \d{4})', block)

        qty, unit_price, total_price = '', '', ''
        line_match = re.search(r'(\d+)\s+EA\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})', block)
        if line_match:
            qty = line_match.group(1)
            unit_price = line_match.group(2)
            total_price = line_match.group(3)

        tags_found = re.findall(r'\b[A-Z0-9]{2,}-[A-Z0-9\-]{2,}\b', block)
        tags = [t for t in tags_found if 'CVE' not in t and 'TSE' not in t]

        tags = list(set(tags))
        has_tag = 'Y' if tags else 'N'

        calib_data, calib_details = extract_calib_data(lines, source='PO')

        data.append({
            'Line No': int(line_no) if line_no else '',
            'Model Number': model.group(1) if model else '',
            'Ship Date': ship_date.group(1) if ship_date else '',
            'Qty': qty,
            'Unit Price': unit_price,
            'Total Price': total_price,
            'Has Tag?': has_tag,
            'Tags': ", ".join(tags) if tags else '',
            'Calib Data?': calib_data,
            'Calib Data': calib_details,
            'PERM = WIRE?': ''
        })

    df = pd.DataFrame(data)

    if order_total:
        order_total_row = {
            'Line No': '',
            'Model Number': 'ORDER TOTAL',
            'Ship Date': '',
            'Qty': '',
            'Unit Price': '',
            'Total Price': order_total,
            'Has Tag?': '',
            'Tags': '',
            'Calib Data?': '',
            'Calib Data': '',
            'PERM = WIRE?': ''
        }
        df = pd.concat([df, pd.DataFrame([order_total_row])], ignore_index=True)

    df_main = df[df['Model Number'] != 'ORDER TOTAL'].copy()
    df_total = df[df['Model Number'] == 'ORDER TOTAL'].copy()
    df_main['Line No'] = pd.to_numeric(df_main['Line No'], errors='coerce')
    df_main = df_main.sort_values(by='Line No', ignore_index=True)

    df = pd.concat([df_main, df_total], ignore_index=True)
    return df


def parse_oa(file):
    data = []
    order_total = ""

    with pdfplumber.open(file) as pdf:
        text = "\n".join([p.extract_text() for p in pdf.pages])

    stop_match = re.search(r'Total.*?\(USD\).*?([\d,]+\.\d{2})', text, re.IGNORECASE)
    if stop_match:
        order_total = stop_match.group(1).strip()
        text = text.split(stop_match.group(0))[0]

    blocks = re.split(r'\n(000\d{2}|\d+\.\d+)', text)
    for i in range(1, len(blocks) - 1, 2):
        line_no = blocks[i]
        block = blocks[i+1]
        lines = block.split('\n')

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

        qty, unit_price, total_price = '', '', ''
        line_match = re.search(r'(^|\s)(\d+)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})', block)
        if line_match:
            qty = line_match.group(2)
            unit_price = line_match.group(3)
            total_price = line_match.group(4)

        tags = []
        for idx, line in enumerate(lines):
            if 'PERM' in line or 'NAME' in line:
                for offset in range(1, 4):
                    if idx + offset < len(lines):
                        possible = lines[idx + offset].strip()
                        if '-' in possible and len(possible) <= 30:
                            tags.append(possible)

        tags = list(set(tags))
        has_tag = 'Y' if tags else 'N'

        perm_tag = tags[0] if tags else ''
        wire_match = re.search(r'WIRE\s*:\s*\n?([A-Z0-9\-]+)', block)
        wire_tag = wire_match.group(1).strip() if wire_match else ''

        perm_matches_wire = ''
        if perm_tag and wire_tag:
            perm_matches_wire = 'Y' if perm_tag == wire_tag else 'N'
        elif perm_tag or wire_tag:
            perm_matches_wire = 'N'

        calib_data, calib_details = extract_calib_data(lines, source='OA')

        data.append({
            'Line No': int(line_no) if line_no else '',
            'Model Number': model.group(1) if model else '',
            'Ship Date': ship_date.group(1) if ship_date else '',
            'Qty': qty,
            'Unit Price': unit_price,
            'Total Price': total_price,
            'Has Tag?': has_tag,
            'Tags': ", ".join(tags) if tags else '',
            'Calib Data?': calib_data,
            'Calib Data': calib_details,
            'PERM = WIRE?': perm_matches_wire
        })

    df = pd.DataFrame(data)

    if order_total:
        order_total_row = {
            'Line No': '',
            'Model Number': 'ORDER TOTAL',
            'Ship Date': '',
            'Qty': '',
            'Unit Price': '',
            'Total Price': order_total,
            'Has Tag?': '',
            'Tags': '',
            'Calib Data?': '',
            'Calib Data': '',
            'PERM = WIRE?': ''
        }
        df = pd.concat([df, pd.DataFrame([order_total_row])], ignore_index=True)

    df_main = df[df['Model Number'] != 'ORDER TOTAL'].copy()
    df_total = df[df['Model Number'] == 'ORDER TOTAL'].copy()
    df_main['Line No'] = pd.to_numeric(df_main['Line No'], errors='coerce')
    df_main = df_main.sort_values(by='Line No', ignore_index=True)

    df_tariff = df_main[df_main['Model Number'].str.contains('TARIFF', case=False, na=False)].copy()
    df_main = df_main[~df_main['Model Number'].str.contains('TARIFF', case=False, na=False)].copy()
    df_tariff['Line No'] = ''

    df = pd.concat([df_main, df_tariff, df_total], ignore_index=True)
    return df
