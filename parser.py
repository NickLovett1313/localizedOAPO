import pdfplumber
import pandas as pd
import re

def parse_po(file):
    data = []
    order_total = ""

    # 1) Read all text
    with pdfplumber.open(file) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)

    # 2) Extract & remove the final total
    stop_match = re.search(r'Order total.*?\$?USD.*?([\d,]+\.\d{2})', text, re.IGNORECASE)
    if stop_match:
        order_total = stop_match.group(1).strip()
        text = text.split(stop_match.group(0))[0]

    # 3) Split into “line-number” blocks
    blocks = re.split(r'\n(0{2,}\d{2,}|\d+\.\d+)', text)

    for i in range(1, len(blocks) - 1, 2):
        raw_line_no = blocks[i].strip()
        block       = blocks[i + 1]

        # — MODEL NUMBER: always the very first token on the block
        ft = re.match(r'\s*([A-Z0-9\-_]+)', block)
        if ft:
            model_number = ft.group(1)
        else:
            fb = re.search(r'([A-Z0-9\-_]{6,})', block)
            model_number = fb.group(1) if fb else ""

        # — SHIP DATE
        ship_date_m = re.search(r'([A-Za-z]{3} \d{1,2}, \d{4})', block)
        ship_date   = ship_date_m.group(1) if ship_date_m else ""

        # — QTY / UNIT / TOTAL
        qty = unit_price = total_price = ""
        lm = re.search(r'(\d+)\s+EA\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})', block)
        if lm:
            qty, unit_price, total_price = lm.group(1), lm.group(2), lm.group(3)

        # — TAGS
        tags_found = re.findall(r'\b[A-Z0-9]{2,}-[A-Z0-9\-]{2,}\b', block)
        tags = []
        for t in tags_found:
            if t == model_number:
                continue
            is_cve    = 'CVE' in t or 'TSE' in t
            has_let   = bool(re.search(r'[A-Z]', t))
            has_dig   = bool(re.search(r'\d', t))
            all_dig   = bool(re.fullmatch(r'[\d\-]+', t))
            looks_date= bool(re.search(r'\d{1,2}[-/][A-Za-z]{3}[-/]\d{4}', t))
            ok_len    = 5 <= len(t) <= 30
            if not is_cve and has_let and has_dig and not all_dig and not looks_date and ok_len:
                tags.append(t)
        tags      = list(dict.fromkeys(tags))
        has_tag   = 'Y' if tags else 'N'

        # — CALIBRATION / WIRE CONFIG
        calib_parts  = []
        wire_configs = []
        for line in block.split('\n'):
            if 'Range:' in line:
                rng = line.split('Range:')[-1].strip()
                wm  = re.search(r'([2-5])-WIRE', rng, re.IGNORECASE)
                if wm:
                    wire_configs.append(f"{wm.group(1)}-wire RTD")
                clean = re.sub(r'([2-5])-WIRE(?: RTD)?[:\s]*', '', rng, flags=re.IGNORECASE)
                rm    = re.search(r'-?\d+\s*to\s*-?\d+.*', clean)
                if rm:
                    v = rm.group(0).strip()
                    v = re.sub(r'deg c', 'DEG C', v, flags=re.IGNORECASE)
                    v = re.sub(r'kpag', 'KPAG', v, flags=re.IGNORECASE)
                    calib_parts.append(v)
        wire_configs = list(dict.fromkeys(wire_configs))
        if wire_configs:
            calib_parts = wire_configs + calib_parts
        calib_data    = 'Y' if calib_parts else 'N'
        calib_details = ", ".join(calib_parts)

        data.append({
            'Line No':       int(raw_line_no) if raw_line_no.isdigit() else raw_line_no,
            'Model Number':  model_number,
            'Ship Date':     ship_date,
            'Qty':           qty,
            'Unit Price':    unit_price,
            'Total Price':   total_price,
            'Has Tag?':      has_tag,
            'Tags':          ", ".join(tags),
            'Wire-on Tag':   '',
            'Calib Data?':   calib_data,
            'Calib Details': calib_details
        })

    # 4) Build DataFrame & append total row
    df = pd.DataFrame(data)
    if order_total:
        df = pd.concat([
            df,
            pd.DataFrame([{
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
                'Calib Details': ''
            }])
        ], ignore_index=True)

    # 5) Sort by line number and return
    df_main  = df[df['Model Number'] != 'ORDER TOTAL'].copy()
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

    # Read full PDF text
    with pdfplumber.open(file) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)

    # 1) Extract the true Customer PO (only “Customer PO:” lines, not “Customer PO No:” headers)
    cp_matches = re.findall(r'Customer PO\s*:\s*([A-Z0-9\-]+)', text, re.IGNORECASE)
    cust_po = cp_matches[-1].strip() if cp_matches else None

    # 2) Pull off the final USD total and trim it out
    stop_match = re.search(r'Total.*?\(USD\).*?([\d,]+\.\d{2})', text, re.IGNORECASE)
    if stop_match:
        order_total = stop_match.group(1).strip()
        text = text.split(stop_match.group(0))[0]

    # 3) Split into blocks by 5-digit line numbers (including slash-groups)
    blocks = re.split(r'\n(\d{5}(?:/\d{5})*)', text)

    for i in range(1, len(blocks) - 1, 2):
        raw_line_no = blocks[i].strip()
        block       = blocks[i + 1]

        # Prepare the tag-detection text by removing any occurrence of the Customer PO
        tag_block = block
        if cust_po:
            # replace full PO number with spaces so it won't match our tag regex
            tag_block = re.sub(re.escape(cust_po), " ", tag_block)

        # Handle slash-separated line numbers
        line_nos = [ln for ln in raw_line_no.split('/') if ln.strip()]

        for line_no in line_nos:
            # — Model & Ship Date —
            model = re.search(r'([A-Z0-9\-_]{6,})', block)
            ship_date = re.search(r'Expected Ship Date:\s*(\d{2}-[A-Za-z]{3}-\d{4})', block)
            if not ship_date:
                ship_date = re.search(r'([A-Za-z]{3}\s+\d{1,2},\s+\d{4})', block)

            # — Qty, Unit Price, Total Price —
            qty = unit_price = total_price = ""
            m = re.search(r'(^|\s)(\d+)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})', block)
            if m:
                qty, unit_price, total_price = m.group(2), m.group(3), m.group(4)

            lines = block.split('\n')

            # —— TAGS —— 
            tags_found = re.findall(r'\b[A-Z0-9]{2,}-[A-Z0-9\-]{2,}\b', tag_block)
            tags = []
            for t in tags_found:
                # never treat the Customer PO (exact or as prefix) as a tag
                if cust_po and (t == cust_po or t.startswith(cust_po) or cust_po.startswith(t)):
                    continue
                # original filters
                is_model    = model and t == model.group(1)
                is_cve      = 'CVE' in t or 'TSE' in t
                has_letters = bool(re.search(r'[A-Z]', t))
                has_digits  = bool(re.search(r'\d', t))
                is_all_dig  = bool(re.fullmatch(r'[\d\-]+', t))
                is_date     = bool(
                    re.search(r'\d{1,2}[-/][A-Za-z]{3}[-/]\d{4}', t)
                    or re.search(r'[A-Za-z]{3} \d{1,2}, \d{4}', t)
                    or re.search(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}', t)
                )
                good_len    = 5 <= len(t) <= 50

                if (not is_model and not is_cve
                    and has_letters and has_digits
                    and not is_all_dig and not is_date
                    and good_len):
                    tags.append(t)

            # dedupe while preserving order
            tags = list(dict.fromkeys(tags))

            # enforce your qty==1 rule
            if qty.isdigit() and int(qty) == 1 and len(tags) > 1:
                tags = tags[:1]

            has_tag = 'Y' if tags else 'N'

            # —— WIRE-ON TAGS —— 
            wire_on_tags = []
            for idx, line in enumerate(lines):
                if 'WIRE' in line.upper() and idx + 1 < len(lines):
                    for p in lines[idx + 1].split('/'):
                        p = p.strip()
                        if p and (p in tags or re.match(r'^[A-Z0-9]{2,}-[A-Z0-9\-]{2,}$', p)):
                            wire_on_tags.append(p)
            wire_on_tags = list(dict.fromkeys(wire_on_tags))

            # —— CALIBRATION / CONFIG —— 
            calib_parts = []
            wire_configs = []
            for idx, l in enumerate(lines):
                if re.search(r'-?\d+\s*to\s*-?\d+', l):
                    ranges = re.findall(r'-?\d+\s*to\s*-?\d+', l)
                    unit_clean = ""
                    if idx + 1 < len(lines):
                        um = re.search(r'(DEG\s*[CFK]?|°C|°F|KPA|PSI|BAR|MBAR)', lines[idx+1].upper())
                        if um:
                            unit_clean = um.group(0).strip().upper()
                    if idx + 2 < len(lines) and re.fullmatch(r'1[2-5]', lines[idx+2].strip()):
                        code = lines[idx+2].strip()[1]
                        wire_configs.append(f"{code}-wire RTD")
                    for r in ranges:
                        calib_parts.append(f"{r} {unit_clean}".strip())

            # fallback wire-count search
            if not wire_configs:
                for m in re.findall(r'\s1([2-5])\s', block):
                    wire_configs.append(f"{m}-wire RTD")

            wire_configs = list(dict.fromkeys(wire_configs))
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

    # Assemble DataFrame, append ORDER TOTAL if present
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

    # Final sorting, tariff grouping, cleanup
    df_main   = df[df['Model Number'] != 'ORDER TOTAL'].copy()
    df_total  = df[df['Model Number'] == 'ORDER TOTAL'].copy()
    df_main['Line No'] = pd.to_numeric(df_main['Line No'], errors='coerce')
    df_main   = df_main.sort_values(by='Line No', ignore_index=True)
    df_tariff = df_main[df_main['Model Number'].str.contains('TARIFF', case=False, na=False)].copy()
    df_main   = df_main[~df_main['Model Number'].str.contains('TARIFF', case=False, na=False)].copy()
    df_tariff['Line No'] = ''
    df = pd.concat([df_main, df_tariff, df_total], ignore_index=True)
    df['Line No'] = pd.to_numeric(df['Line No'], errors='coerce')
    df = df[(df['Line No'].fillna(0) >= 0) & (df['Line No'].fillna(0) <= 5000)]
    df = df[df['Model Number'].str.contains('[A-Za-z]', na=False)]
    df = df.dropna(how='all').reset_index(drop=True)

    return df

