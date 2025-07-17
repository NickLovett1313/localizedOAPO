import pdfplumber
import pandas as pd
import re

def parse_po(file):
    data = []
    order_total = ""

    # 1) Read full PDF text
    with pdfplumber.open(file) as pdf:
        text = "\n".join([p.extract_text() or "" for p in pdf.pages])

    # 2) Extract the USD order total
    stop_match = re.search(r'Order total.*?\$?USD.*?([\d,]+\.\d{2})', text, re.IGNORECASE)
    if stop_match:
        order_total = stop_match.group(1).strip()

    # 3) Crop at Spartan GST# or Order Total line
    gst_match = re.search(r'SPARTAN.*?GST#.*', text, re.IGNORECASE)
    if gst_match:
        pos = text.lower().find(gst_match.group(0).lower()) + len(gst_match.group(0))
        text = text[:pos]
    elif stop_match:
        text = text.split(stop_match.group(0))[0]

    # 4) Updated line splitter
    blocks = re.split(r'\n(0*\d{4,5})', text)

    for i in range(1, len(blocks) - 1, 2):
        raw_ln = blocks[i].strip()
        block  = blocks[i + 1]

        if not raw_ln.isdigit():
            continue
        ln = int(raw_ln)
        if ln <= 0:
            continue

        model     = re.search(r'([A-Z0-9\-_]{6,})', block)
        ship_date = re.search(r'([A-Za-z]{3} \d{1,2}, \d{4})', block)

        qty = unit_price = total_price = ""
        m = re.search(r'(\d+)\s+EA\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})', block)
        if m:
            qty, unit_price, total_price = m.group(1), m.group(2), m.group(3)

        model_str = model.group(1) if model else ''

        tags_found = re.findall(r'\b[A-Z0-9]{2,}-[A-Z0-9\-]{2,}\b', block)
        tags = []
        for t in tags_found:
            is_model     = model_str and t == model_str
            is_cve       = 'CVE' in t or 'TSE' in t
            has_letters  = bool(re.search(r'[A-Z]', t))
            has_digits   = bool(re.search(r'\d', t))
            is_all_digits= bool(re.fullmatch(r'[\d\-]+', t))
            is_date      = bool(re.search(r'\d{1,2}[-/][A-Za-z]{3}[-/]\d{4}', t)
                              or re.search(r'[A-Za-z]{3} \d{1,2}, \d{4}', t)
                              or re.search(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}', t))
            ok_len       = 5 <= len(t) <= 30
            if not (is_model or is_cve or is_all_digits or is_date) and has_letters and has_digits and ok_len:
                tags.append(t)
        tags = list(set(tags))
        has_tag = 'Y' if tags else 'N'

        calib_parts  = []
        wire_configs = []
        for line in block.split('\n'):
            if 'RANGE:' in line.upper():
                parts = line.split('Range:')[-1].strip()
                wm = re.search(r'([2-5])-WIRE', parts, re.IGNORECASE)
                if wm:
                    wire_configs.append(f"{wm.group(1)}-wire RTD")
                pc = re.sub(r'([2-5])-WIRE RTD[:\s]*', '', parts, flags=re.IGNORECASE)
                pc = re.sub(r'([2-5])-WIRE[:\s]*', '', pc, flags=re.IGNORECASE)
                rm = re.search(r'-?\d+\s*to\s*-?\d+.*', pc)
                if rm:
                    val = rm.group(0).strip()
                    val = re.sub(r'deg c', 'DEG C', val, flags=re.IGNORECASE)
                    val = re.sub(r'kpag', 'KPAG', val, flags=re.IGNORECASE)
                    calib_parts.append(val)
        wire_configs = list(set(wire_configs))
        if wire_configs:
            calib_parts = wire_configs + calib_parts
        calib_data    = 'Y' if calib_parts else 'N'
        calib_details = ", ".join(calib_parts)

        data.append({
            'Line No':       ln,
            'Model Number':  model_str,
            'Ship Date':     ship_date.group(1) if ship_date else '',
            'Qty':           qty,
            'Unit Price':    unit_price,
            'Total Price':   total_price,
            'Has Tag?':      has_tag,
            'Tags':          ", ".join(tags),
            'Wire-on Tag':   '',
            'Calib Data?':   calib_data,
            'Calib Details': calib_details
        })

    # 10) Build DataFrame
    df = pd.DataFrame(data)

    # 🔒 Hard Cleanup Step
    df = df[
        (pd.to_numeric(df['Line No'], errors='coerce') <= 10000) &
        (df['Qty'].str.strip() != '') &
        (df['Unit Price'].str.strip() != '') &
        (df['Total Price'].str.strip() != '')
    ].copy()

    # 11) Append order total if present
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
            'Calib Details': ''
        }])], ignore_index=True)

    # 12) Final sort
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
    tariff_rows = []

    # 1) Read full PDF text
    with pdfplumber.open(file) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)

    # 1a) Extract the Customer PO so it’s never treated as a tag
    cp_matches = re.findall(r'Customer PO(?: No)?\s*:\s*([A-Z0-9\-]+)', text, re.IGNORECASE)
    cust_po = cp_matches[-1].strip() if cp_matches else None

    # 2) Minimal “TARIFF” surcharge detector
    for line in text.split("\n"):
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

    # 3) Pull off the final total
    stop_match = re.search(r'Total.*?\(USD\).*?([\d,]+\.\d{2})', text, re.IGNORECASE)
    if stop_match:
        order_total = stop_match.group(1).strip()
        text = text.split(stop_match.group(0))[0]

    # 4) Split into blocks by 5-digit OA line numbers (including slash-groups)
    blocks = re.split(r'\n(\d{5}(?:/\d{5})*)', text)
    for i in range(1, len(blocks) - 1, 2):
        raw_line_no = blocks[i].strip()
        block       = blocks[i + 1]

        # filter valid line numbers
        line_nos = [ln for ln in raw_line_no.split('/')
                    if ln.isdigit() and 1 <= int(ln) <= 10000]
        if not line_nos:
            continue

        contains_tag_section = bool(re.search(r'\bTag\b', block, re.IGNORECASE))
        lines_clean = [l.strip() for l in block.split('\n') if l.strip()]

        for line_no in line_nos:
            # Model Number
            model_m = re.search(r'\b(?=[A-Z0-9\-_]*[A-Z])[A-Z0-9\-_]{6,}\b', block)
            model   = model_m.group(0) if model_m else ""

            # Ship Date
            sd = re.search(r'Expected Ship Date:\s*(\d{2}-[A-Za-z]{3}-\d{4})', block)
            ship_date = sd.group(1) if sd else (
                (re.search(r'([A-Za-z]{3}\s+\d{1,2},\s+\d{4})', block) or [None, ""])[1]
            )

            # Qty / Unit / Total
            qty = unit_price = total_price = ""
            m2 = re.search(r'(^|\s)(\d+)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})', block)
            if m2:
                qty, unit_price, total_price = m2.group(2), m2.group(3), m2.group(4)

            # === TAG SECTION LOGIC: exact extraction under "Tag" label ===
            tags = []
            wire_on_tags = []
            if contains_tag_section:
                # locate the line with "Tag:" or "Tags:"
                tag_idx = next((idx for idx, l in enumerate(lines_clean)
                                if re.match(r'(?i)^Tags?:', l)), None)
                raw_tags_line = ""
                if tag_idx is not None:
                    line = lines_clean[tag_idx]
                    # if tags follow the colon on same line
                    if ':' in line:
                        raw_tags_line = line.split(':', 1)[1]
                    # else, tags on next line
                    elif tag_idx + 1 < len(lines_clean):
                        raw_tags_line = lines_clean[tag_idx + 1]
                # split multiple tags by comma or semicolon
                if raw_tags_line:
                    tags = [t.strip() for t in re.split(r'[;,]\s*', raw_tags_line) if t.strip()]

            # dedupe per row
            tags = list(dict.fromkeys(tags))
            has_tag = 'Y' if tags else 'N'

            # Calibration / Configuration logic (unchanged)
            calib_parts  = []
            wire_configs = []
            for idx, ln in enumerate(lines_clean):
                if re.search(r'-?\d+(?:\.\d+)?\s*to\s*-?\d+(?:\.\d+)?', ln):
                    ranges = re.findall(r'-?\d+(?:\.\d+)?\s*to\s*-?\d+(?:\.\d+)?', ln)
                    unit_clean = ''
                    if idx + 1 < len(lines_clean):
                        um = re.search(r'(DEG\s*[CFK]?|°C|°F|KPA|PSI|BAR|MBAR)',
                                       lines_clean[idx + 1].upper())
                        if um:
                            unit_clean = um.group(0).strip().upper()
                    if idx + 2 < len(lines_clean) and re.fullmatch(r'1[2-5]', lines_clean[idx + 2].strip()):
                        code = lines_clean[idx + 2].strip()[1]
                        wire_configs.append(f"{code}-wire RTD")
                    for r in ranges:
                        calib_parts.append(f"{r} {unit_clean}".strip())
            if not wire_configs and any('WIRE' in ln.upper() for ln in lines_clean):
                for w in re.findall(r'\s1([2-5])\s', block):
                    wire_configs.append(f"{w}-wire RTD")
            wire_configs = list(dict.fromkeys(wire_configs))
            if wire_configs:
                calib_parts = wire_configs + calib_parts
            calib_data    = 'Y' if calib_parts else 'N'
            calib_details = ", ".join(calib_parts)

            data.append({
                'Line No':       line_no,
                'Model Number':  model,
                'Ship Date':     ship_date,
                'Qty':           qty,
                'Unit Price':    unit_price,
                'Total Price':   total_price,
                'Has Tag?':      has_tag,
                'Tags':          ", ".join(tags),
                'Wire-on Tag':   ", ".join(wire_on_tags),
                'Calib Data?':   calib_data,
                'Calib Details': calib_details
            })

    # 5) Append surcharge rows
    data.extend(tariff_rows)

    # 6) Build DataFrame & append ORDER TOTAL
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
            'Calib Details': ''
        }])], ignore_index=True)

    # 7) Final sort
    df_main  = df[df['Model Number'] != 'ORDER TOTAL'].copy()
    df_total = df[df['Model Number'] == 'ORDER TOTAL'].copy()
    df_main = df_main.sort_values(
        by='Line No',
        key=lambda col: pd.to_numeric(col, errors='coerce'),
        ignore_index=True
    )
    df = pd.concat([df_main, df_total], ignore_index=True)
    return df


