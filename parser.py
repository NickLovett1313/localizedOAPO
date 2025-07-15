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
            # Look for unit on same line
            for u in valid_units:
                if u in line.upper():
                    unit = u
                    break
            # Or check next line
            if not unit and idx + 1 < len(lines):
                next_line = lines[idx + 1].upper().strip()
                for u in valid_units:
                    if u in next_line:
                        unit = u
                        break

            part = f"{range_match.group(1)} to {range_match.group(2)}"
            if unit:
                part += f" {unit}"

            # Check 1–2 lines below for wire code 12/13/14 (OA only)
            wire_config = ''
            if source == 'OA':
                for offset in range(1, 3):
                    if idx + offset < len(lines):
                        w_line = lines[idx + offset].strip()
                        if re.fullmatch(r'1[2-4]', w_line):
                            wire_code = w_line
                            if wire_code == '12': wire_config = '2-wire RTD'
                            if wire_code == '13': wire_config = '3-wire RTD'
                            if wire_code == '14': wire_config = '4-wire RTD'
                            break
            if wire_config:
                calib_parts.append(f"{wire_config}, {part}")
            else:
                calib_parts.append(part)

    if not calib_parts:
        return "N", ""
    return "Y", ", ".join(calib_parts)

def parse_po(file):
    data = []
    order_total = ""

    with pdfplumber.open(file) as pdf:
        text = "\n".join([p.extract_text() for p in pdf.pages])

    stop_match = re.search(r'Order Total.*?USD\)?\s*([\d,]+\.\d{2})', text, re.IGNORECASE)
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
        tags = list(set([t for t in tags_found]))
        has_tag = 'Y' if tags else 'N'

        calib_data, calib_details = extract_calib_data(lines, source='PO')

        # Missing Calib?
        expected = int(qty) if qty else 0
        actual = len(calib_details.split(",")) if calib_data == 'Y' else 0
        missing = 'Y' if (calib_data == 'Y' and expected != actual) else 'N'

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
            'Missing Calib?': missing,
            'Calib Data': calib_details,
            'PERM = WIRE?': ''
        })

    df = pd.DataFrame(data)
    if order_total:
        df = pd.concat([df, pd.DataFrame([{'Line No': '', 'Model Number': 'ORDER TOTAL',
            'Ship Date': '', 'Qty': '', 'Unit Price': '', 'Total Price': order_total,
            'Has Tag?': '', 'Tags': '', 'Calib Data?': '', 'Missing Calib?': '',
            'Calib Data': '', 'PERM = WIRE?': ''}])], ignore_index=True)

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
            line_no = int(line_no.split('.')[0]) * 10
        else:
            line_no = int(line_no) if line_no.isdigit() else ''

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
                        if '-' in possible:
                            tags.append(possible)

        tags = list(set(tags))
        has_tag = 'Y' if tags else 'N'

        perm_tag = tags[0] if tags else ''
        wire_tag = ''
        wire_match = re.search(r'WIRE\s*:\s*\n?([A-Z0-9\-]+)', block)
        if wire_match:
            wire_tag = wire_match.group(1).strip()

        perm_matches_wire = ''
        if perm_tag and wire_tag:
            perm_matches_wire = 'Y' if perm_tag == wire_tag else 'N'
        elif perm_tag or wire_tag:
            perm_matches_wire = 'N'

        calib_data, calib_details = extract_calib_data(lines, source='OA')

        expected = int(qty) if qty else 0
        actual = len(calib_details.split(",")) if calib_data == 'Y' else 0
        missing = 'Y' if (calib_data == 'Y' and expected != actual) else 'N'

        data.append({
            'Line No': line_no,
            'Model Number': model.group(1) if model else '',
            'Ship Date': ship_date.group(1) if ship_date else '',
            'Qty': qty,
            'Unit Price': unit_price,
            'Total Price': total_price,
            'Has Tag?': has_tag,
            'Tags': ", ".join(tags) if tags else '',
            'Calib Data?': calib_data,
            'Missing Calib?': missing,
            'Calib Data': calib_details,
            'PERM = WIRE?': perm_matches_wire
        })

    df = pd.DataFrame(data)
    if order_total:
        df = pd.concat([df, pd.DataFrame([{'Line No': '', 'Model Number': 'ORDER TOTAL',
            'Ship Date': '', 'Qty': '', 'Unit Price': '', 'Total Price': order_total,
            'Has Tag?': '', 'Tags': '', 'Calib Data?': '', 'Missing Calib?': '',
            'Calib Data': '', 'PERM = WIRE?': ''}])], ignore_index=True)

    df_main = df[df['Model Number'] != 'ORDER TOTAL'].copy()
    df_total = df[df['Model Number'] == 'ORDER TOTAL'].copy()
    df_main['Line No'] = pd.to_numeric(df_main['Line No'], errors='coerce')
    df_main = df_main.sort_values(by='Line No', ignore_index=True)

    df_tariff = df_main[df_main['Model Number'].str.contains('TARIFF', case=False, na=False)].copy()
    df_main = df_main[~df_main['Model Number'].str.contains('TARIFF', case=False, na=False)].copy()
    df_tariff['Line No'] = ''

    df = pd.concat([df_main, df_tariff, df_total], ignore_index=True)
    return df
