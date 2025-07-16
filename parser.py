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
    tariff_rows = []

    # 1) Read full PDF text
    with pdfplumber.open(file) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)

    # 2) Minimal “TARIFF” surcharge detector (no 5-digit line #)
    for line in text.split('\n'):
        m = re.match(
            r'\s*\d+\.\d+\s+([A-Z0-9\-]*TARIFF[A-Z0-9\-]*)\s+(\d+)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})',
            line, re.IGNORECASE
        )
        if m:
            tariff_rows.append({
                'Line No':       '',
                'Model Number':  m.group(1),
                'Ship Date':     '',
                'Qty':           m.group(2),
                'Unit Price':    m.group(3),
                'Total Price':   m.group(4),
                'Has Tag?':      '',
                'Tags':          '',
                'Wire-on Tag':   '',
                'Calib Data?':   '',
                'Calib Details': ''
            })

    # 3) Pull off the final total and trim it out
    stop_match = re.search(r'Total.*?\(USD\).*?([\d,]+\.\d{2})', text, re.IGNORECASE)
    if stop_match:
        order_total = stop_match.group(1).strip()
        text = text.split(stop_match.group(0))[0]

    # 4) Split into blocks by 5-digit OA line numbers (including slash-groups)
    blocks = re.split(r'\n(\d{5}(?:/\d{5})*)', text)

    for i in range(1, len(blocks) - 1, 2):
        raw_line_no = blocks[i].strip()
        block       = blocks[i + 1]

        # break out each number if there's a slash
        line_nos = [ln for ln in raw_line_no.split('/') if ln.strip()]

        for line_no in line_nos:
            # model & ship date
            model     = re.search(r'([A-Z0-9\-_]{6,})', block)
            ship_date = re.search(r'Expected Ship Date: (\d{2}-[A-Za-z]{3}-\d{4})', block)
            if not ship_date:
                ship_date = re.search(r'([A-Za-z]{3} \d{1,2}, \d{4})', block)

            # qty / prices
            qty = unit_price = total_price = ''
            lm = re.search(r'(^|\s)(\d+)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})', block)
            if lm:
                qty, unit_price, total_price = lm.group(2), lm.group(3), lm.group(4)

            lines = block.split('\n')

            # —— TAGS —— 
            tags = []
            # reuse original is_valid_tag logic
            def is_valid_tag(candidate):
                if not candidate:
                    return False
                tag_pattern = re.compile(r'^[A-Z]{2,}-[A-Z0-9\-]{2,}$')
                if not tag_pattern.match(candidate):
                    return False
                has_letters = re.search(r'[A-Z]', candidate)
                has_digits  = re.search(r'\d', candidate)
                has_dash    = '-' in candidate
                reasonable  = 4 <= len(candidate) <= 50
                not_date    = not re.search(r'\d{1,2}[-/][A-Za-z]{3}[-/]\d{4}', candidate)
                return bool(has_letters and has_digits and has_dash and reasonable and not_date)

            for idx, line in enumerate(lines):
                # split on slashes
                parts = [p.strip() for p in line.split('/')] if '/' in line else [line.strip()]
                for p in parts:
                    if is_valid_tag(p) or re.search(r'IC\d{2,5}-NC', p.upper()):
                        tags.append(p)

            tags = list(dict.fromkeys(tags))
            # enforce qty==1 rule
            if qty.isdigit() and int(qty) == 1 and len(tags) > 1:
                tags = tags[:1]
            has_tag = 'Y' if tags else 'N'

            # —— WIRE-ON TAGS —— 
            wire_on_tags = []
            for idx, line in enumerate(lines):
                if 'WIRE' in line.upper() and idx+1 < len(lines):
                    for p in lines[idx+1].split('/'):
                        p = p.strip()
                        if (is_valid_tag(p) or re.search(r'IC\d{2,5}-NC', p.upper())):
                            wire_on_tags.append(p)
            wire_on_tags = list(dict.fromkeys(wire_on_tags))

            # —— CALIBRATION / CONFIG —— 
            calib_parts  = []
            wire_configs = []
            for idx, l in enumerate(lines):
                if re.search(r'-?\d+\s*to\s*-?\d+', l):
                    ranges = re.findall(r'-?\d+\s*to\s*-?\d+', l)
                    unit_clean = ""
                    if idx+1 < len(lines):
                        um = re.search(r'(DEG\s*[CFK]?|°C|°F|KPA|PSI|BAR|MBAR)', lines[idx+1].upper())
                        if um:
                            unit_clean = um.group(0).strip().upper()
                    if idx+2 < len(lines) and re.fullmatch(r'1[2-5]', lines[idx+2].strip()):
                        wire_configs.append(f"{lines[idx+2].strip()[1]}-wire RTD")
                    for r in ranges:
                        calib_parts.append(f"{r} {unit_clean}".strip())
            if not wire_configs:
                for m in re.findall(r'\s1([2-5])\s', block):
                    wire_configs.append(f"{m}-wire RTD")
            if wire_configs:
                calib_parts = wire_configs + calib_parts

            calib_data    = 'Y' if calib_parts else 'N'
            calib_details = ", ".join(calib_parts)

            data.append({
                'Line No':       line_no,
                'Model Number':  model.group(1)    if model else '',
                'Ship Date':     ship_date.group(1) if ship_date else '',
                'Qty':           qty,
                'Unit Price':    unit_price,
                'Total Price':   total_price,
                'Has Tag?':      has_tag,
                'Tags':          ", ".join(tags),
                'Wire-on Tag':   ", ".join(wire_on_tags),
                'Calib Data?':   calib_data,
                'Calib Details': calib_details
            })

    # 5) tack on any surcharge rows we found
    data.extend(tariff_rows)

    # 6) build df and append ORDER TOTAL if present
    df = pd.DataFrame(data)
    if order_total:
        df = pd.concat([df, pd.DataFrame([{
            'Line No':       '',
            'Model Number':  'ORDER TOTAL',
            'Ship Date':     '',
            'Qty':           '',
            'Unit Price':    '',
            'Total Price':   order_total,
            'Has Tag?':      '',
            'Tags':          '',
            'Wire-on Tag':   '',
            'Calib Data?':   '',
            'Calib Details':''
        }])], ignore_index=True)

    # 7) final sorting and return
    df_main   = df[df['Model Number'] != 'ORDER TOTAL'].copy()
    df_total  = df[df['Model Number'] == 'ORDER TOTAL'].copy()
    df_main['Line No'] = pd.to_numeric(df_main['Line No'], errors='coerce')
    df_main = df_main.sort_values(by='Line No', ignore_index=True)
    df = pd.concat([df_main, df_total], ignore_index=True)
    return df

