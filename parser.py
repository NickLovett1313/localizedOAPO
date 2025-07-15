import pdfplumber
import pandas as pd
import re

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

        model = re.search(r'([A-Z0-9\-]{6,})', block)
        ship_date = re.search(r'([A-Za-z]{3} \d{1,2}, \d{4})', block)

        qty, unit_price, total_price = '', '', ''
        line_match = re.search(r'(\d+)\s+EA\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})', block)
        if line_match:
            qty = line_match.group(1)
            unit_price = line_match.group(2)
            total_price = line_match.group(3)

        tags_found = re.findall(r'\b[A-Z0-9]{2,}-[A-Z0-9\-]{2,}\b', block)
        tags = []
        for t in tags_found:
            is_model = model and t == model.group(1)
            is_cve = 'CVE' in t or 'TSE' in t
            has_letters = re.search(r'[A-Z]', t)
            has_digits = re.search(r'\d', t)
            is_all_digits = bool(re.fullmatch(r'[\d\-]+', t))
            is_date = (
                re.search(r'\d{1,2}[-/][A-Za-z]{3}[-/]\d{4}', t)
                or re.search(r'[A-Za-z]{3} \d{1,2}, \d{4}', t)
                or re.search(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}', t)
            )
            is_reasonable_len = 5 <= len(t) <= 30

            if not is_model and not is_cve and has_letters and has_digits and not is_all_digits and not is_date and is_reasonable_len:
                tags.append(t)

        tags = list(set(tags))
        has_tag = 'Y' if tags else 'N'

        if has_tag == 'Y':
            calib_parts = []
            block_lower = block.lower()
            if re.search(r'\b3[-\s]?wire\b', block_lower):
                calib_parts.append('3-wire RTD')
            if re.search(r'\b4[-\s]?wire\b', block_lower):
                calib_parts.append('4-wire RTD')

            range_units = re.findall(r'(-?\d+\s*to\s*-?\d+)\s*([A-Za-z° ]+)', block)
            for r, u in range_units:
                full_range = f"{r} {u.strip()}"
                calib_parts.append(full_range)

            calib_data = 'Y' if calib_parts else 'N'
            calib_details = ", ".join(calib_parts)
        else:
            calib_data = 'N'
            calib_details = ''

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
            'Calib Details': calib_details,
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
            'Calib Details': '',
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

        wire_tag = ''
        perm_matches_wire = ''

        lines = block.split('\n')

        def is_valid_tag(candidate):
            if not candidate:
                return False
            tag_pattern = re.compile(r'^[A-Z]{2,3}-[A-Z0-9\-]{2,}$')
            if not tag_pattern.match(candidate):
                return False
            has_letters = re.search(r'[A-Z]', candidate)
            has_digits = re.search(r'\d', candidate)
            has_dash = '-' in candidate
            is_reasonable_len = 4 <= len(candidate) <= 30
            is_not_date = not re.search(r'\d{1,2}-[A-Za-z]{3}-\d{4}', candidate)
            return has_letters and has_digits and has_dash and is_reasonable_len and is_not_date

        tags = []
        for idx, line in enumerate(lines):
            if 'PERM' in line or 'NAME' in line:
                for offset in range(1, 4):
                    if idx + offset < len(lines):
                        possible = lines[idx + offset].strip()
                        if is_valid_tag(possible):
                            tags.append(possible)

        if not tags:
            for l in lines:
                possible = l.strip()
                if is_valid_tag(possible):
                    tags.append(possible)

        tags = list(set(tags))
        has_tag = 'Y' if tags else 'N'
        perm_tag = tags[0] if tags else ''

        wire_match = re.search(r'WIRE\s*:\s*\n?([A-Z0-9\-]+)', block)
        if wire_match:
            wire_tag = wire_match.group(1).strip()

        if perm_tag and wire_tag:
            perm_matches_wire = 'Y' if perm_tag == wire_tag else 'N'
        elif perm_tag or wire_tag:
            perm_matches_wire = 'N'
        else:
            perm_matches_wire = ''

        # ✅ Final stacked config + whole block scan for wire digit
        calib_parts = []
        wire_config = ''

        for idx, l in enumerate(lines):
            if re.search(r'-?\d+\s*to\s*-?\d+', l):
                ranges = re.findall(r'-?\d+\s*to\s*-?\d+', l)

                unit_clean = ""
                if idx + 1 < len(lines):
                    unit_line = lines[idx + 1].strip().upper()
                    unit_match = re.search(r'(DEG\s*[CFK]?|°C|°F|KPA|PSI|BAR|MBAR)', unit_line)
                    if unit_match:
                        unit_clean = unit_match.group(0).strip().upper()

                if idx + 2 < len(lines):
                    config_line = lines[idx + 2].strip()
                    if re.fullmatch(r'1[2-5]', config_line):
                        code = config_line[1]
                        wire_config = f"{code}-wire RTD"

                for r in ranges:
                    if unit_clean:
                        calib_parts.append(f"{r} {unit_clean}")
                    else:
                        calib_parts.append(r)

        # ✅ Fallback: scan entire block for standalone wire digit if not found yet
        if not wire_config:
            wire_match = re.search(r'\s1([2-5])\s', block)
            if wire_match:
                code = wire_match.group(1)
                wire_config = f"{code}-wire RTD"

        if wire_config:
            calib_parts.insert(0, wire_config)

        calib_data = 'Y' if calib_parts else 'N'
        calib_details = ", ".join(calib_parts)

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
            'Calib Details': calib_details,
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
            'Calib Details': '',
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
