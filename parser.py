import pdfplumber
import pandas as pd
import re

def parse_po(file):
    data = []
    order_total = ""

    with pdfplumber.open(file) as pdf:
        text = "\n".join([p.extract_text() for p in pdf.pages])

    stop_match = re.search(r'Order total.*?\$?USD.*?([\d,]+\.\d{2})', text, re.IGNORECASE)
    if stop_match:
        order_total = stop_match.group(1).strip()
        text = text.split(stop_match.group(0))[0]

    blocks = re.split(r'\n(0{2,}\d{2,}|\d+\.\d+)', text)

    for i in range(1, len(blocks) - 1, 2):
        line_no = blocks[i]
        block = blocks[i+1]

        model = re.search(r'([A-Z0-9\-_]{6,})', block)
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

        calib_parts = []
        wire_configs = []

        lines = block.split('\n')

        for l in lines:
            l_upper = l.strip().upper()
            if 'RANGE:' in l_upper:
                parts = l.split('Range:')[-1].strip()

                wire_match = re.search(r'([2-5])-WIRE', parts, re.IGNORECASE)
                if wire_match:
                    wire_configs.append(f"{wire_match.group(1)}-wire RTD")

                parts_clean = re.sub(r'([2-5])-WIRE RTD[:\s]*', '', parts, flags=re.IGNORECASE)
                parts_clean = re.sub(r'([2-5])-WIRE[:\s]*', '', parts_clean, flags=re.IGNORECASE)

                range_match = re.search(r'-?\d+\s*to\s*-?\d+.*', parts_clean)
                if range_match:
                    value = range_match.group(0).strip()
                    value = re.sub(r'deg c', 'DEG C', value, flags=re.IGNORECASE)
                    value = re.sub(r'kpag', 'KPAG', value, flags=re.IGNORECASE)
                    calib_parts.append(value)

        wire_configs = list(set(wire_configs))
        if wire_configs:
            calib_parts = wire_configs + calib_parts

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
            'Wire-on Tag': '',  # PO always blank
            'Calib Data?': calib_data,
            'Calib Details': calib_details
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
            'Wire-on Tag': '',
            'Calib Data?': '',
            'Calib Details': ''
        }
        df = pd.concat([df, pd.DataFrame([order_total_row])], ignore_index=True)

    df_main = df[df['Model Number'] != 'ORDER TOTAL'].copy()
    df_total = df[df['Model Number'] == 'ORDER TOTAL'].copy()
    df_main['Line No'] = pd.to_numeric(df_main['Line No'], errors='coerce')
    df_main = df_main.sort_values(by='Line No', ignore_index=True)
    df = pd.concat([df_main, df_total], ignore_index=True)

    return df

import pdfplumber
import pandas as pd
import re

def parse_oa(file):
    data = []
    order_total = ""

    with pdfplumber.open(file) as pdf:
        text = "\n".join([p.extract_text() for p in pdf.pages])

    stop_match = re.search(r'Total.*?\(USD\).*?([\d,]+\.\d{2})', text, re.IGNORECASE)
    if stop_match:
        order_total = stop_match.group(1).strip()
        text = text.split(stop_match.group(0))[0]

    blocks = re.split(r'\n(0{2,}\d{2,}|\d+\.\d+)', text)

    for i in range(1, len(blocks) - 1, 2):
        raw_line_no = blocks[i].strip()
        block = blocks[i + 1]

        line_nos = [raw_line_no]
        if '/' in raw_line_no:
            line_nos = [ln.strip() for ln in raw_line_no.split('/') if ln.strip()]

        for line_no in line_nos:
            model = re.search(r'([A-Z0-9\-_]{6,})', block)
            ship_date = re.search(r'Expected Ship Date: (\d{2}-[A-Za-z]{3}-\d{4})', block)
            if not ship_date:
                ship_date = re.search(r'([A-Za-z]{3} \d{1,2}, \d{4})', block)

            qty, unit_price, total_price = '', '', ''
            line_match = re.search(r'(^|\s)(\d+)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})', block)
            if line_match:
                qty = line_match.group(2)
                unit_price = line_match.group(3)
                total_price = line_match.group(4)

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
                is_reasonable_len = 4 <= len(candidate) <= 50
                is_not_date = not re.search(r'\d{1,2}-[A-Za-z]{3}-\d{4}', candidate)
                return has_letters and has_digits and has_dash and is_reasonable_len and is_not_date

            tags = []
            wire_on_tags = []

            for idx, line in enumerate(lines):
                line_upper = line.upper().strip()
                possible_tags = []
                if '/' in line:
                    parts = [p.strip() for p in line.split('/') if p.strip()]
                    possible_tags.extend(parts)
                else:
                    possible_tags.append(line.strip())

                for tag in possible_tags:
                    if is_valid_tag(tag):
                        tags.append(tag)
                    elif re.search(r'IC\d{2,5}-NC', tag.upper()):
                        tags.append(tag)

                if 'WIRE' in line_upper:
                    if idx + 1 < len(lines):
                        wire_candidate = lines[idx + 1].strip()
                        if '/' in wire_candidate:
                            parts = [p.strip() for p in wire_candidate.split('/') if p.strip()]
                            for p in parts:
                                if is_valid_tag(p):
                                    wire_on_tags.append(p)
                                elif re.search(r'IC\d{2,5}-NC', p.upper()):
                                    wire_on_tags.append(p)
                        else:
                            if is_valid_tag(wire_candidate):
                                wire_on_tags.append(wire_candidate)
                            elif re.search(r'IC\d{2,5}-NC', wire_candidate.upper()):
                                wire_on_tags.append(wire_candidate)

            tags = list(set(tags))
            wire_on_tags = list(set(wire_on_tags))
            has_tag = 'Y' if tags else 'N'

            calib_parts = []
            wire_configs = []

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
                            wire_configs.append(f"{code}-wire RTD")
                    for r in ranges:
                        if unit_clean:
                            calib_parts.append(f"{r} {unit_clean}")
                        else:
                            calib_parts.append(r)

            if not wire_configs:
                wire_match = re.findall(r'\s1([2-5])\s', block)
                for m in wire_match:
                    wire_configs.append(f"{m}-wire RTD")
            wire_configs = list(set(wire_configs))
            if wire_configs:
                calib_parts = wire_configs + calib_parts

            calib_data = 'Y' if calib_parts else 'N'
            calib_details = ", ".join(calib_parts)

            data.append({
                'Line No': line_no,
                'Model Number': model.group(1) if model else '',
                'Ship Date': ship_date.group(1) if ship_date else '',
                'Qty': qty,
                'Unit Price': unit_price,
                'Total Price': total_price,
                'Has Tag?': has_tag,
                'Tags': ", ".join(tags) if tags else '',
                'Wire-on Tag': ", ".join(wire_on_tags) if wire_on_tags else '',
                'Calib Data?': calib_data,
                'Calib Details': calib_details
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
            'Wire-on Tag': '',
            'Calib Data?': '',
            'Calib Details': ''
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

    df['Line No'] = pd.to_numeric(df['Line No'], errors='coerce')
    df = df[(df['Line No'].fillna(0) >= 0) & (df['Line No'].fillna(0) <= 5000)]
    df = df[df['Model Number'].str.contains('[A-Za-z]', na=False)]
    df = df.dropna(how='all').reset_index(drop=True)

    return df

