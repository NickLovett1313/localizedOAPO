import pdfplumber
import pandas as pd
import re

def parse_po(file):
    data = []
    order_total = ""

    with pdfplumber.open(file) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)

    # Extract order total if present
    stop_match = re.search(r'Order total.*?\$?USD.*?([\d,]+\.\d{2})', text, re.IGNORECASE)
    if stop_match:
        order_total = stop_match.group(1).strip()
        text = text.split(stop_match.group(0))[0]

    # Robust line-by-line parsing
    lines = text.split('\n')
    current_block = []
    blocks = []

    for line in lines:
        line = line.strip()
        if re.match(r'^\d{5}\b', line):  # new PO line start
            if current_block:
                blocks.append(current_block)
            current_block = [line]
        elif current_block:
            current_block.append(line)
    if current_block:
        blocks.append(current_block)

    for block in blocks:
        try:
            block_text = "\n".join(block)

            # Line No
            line_m = re.match(r'^0*(\d{1,5})\b', block[0])
            if not line_m:
                continue
            line_no = line_m.group(1)

            # Model Number
            model_m = re.search(r'\b([A-Z0-9\-_]{6,})\b', block[0])
            model = model_m.group(1) if model_m else ''

            # Qty / Unit Price / Total Price
            qty = unit_price = total_price = ""
            m = re.search(r'(\d+)\s+EA\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})', block_text)
            if m:
                qty, unit_price, total_price = m.group(1), m.group(2), m.group(3)

            # Ship Date
            ship_date = ""
            ship_m = re.search(r'Requested Ship Date\s*[:\-]?\s*([A-Za-z]{3} \d{1,2}, \d{4})', block_text)
            if ship_m:
                ship_date = ship_m.group(1)

            # Tags
            tags = []
            has_tag = 'N'
            wire_tags = []

            for i, line in enumerate(block):
                if 'Tag(s)' in line:
                    # Pull next line(s) as tags
                    if i+1 < len(block):
                        raw_tag_line = block[i+1].strip()
                        tag_parts = re.split(r'[;/]', raw_tag_line)
                        for t in tag_parts:
                            tag = t.strip().upper()
                            if re.fullmatch(r'[A-Z0-9\-_]{5,}', tag):
                                tags.append(tag)
                                wire_tags.append(tag)

            tags = list(dict.fromkeys(tags))
            wire_tags = list(dict.fromkeys(wire_tags))
            has_tag = 'Y' if tags else 'N'

            # Calibration details (unchanged)
            calib_parts = []
            wire_configs = []
            for ln in block:
                # Range line
                if re.search(r'-?\d+(\.\d+)?\s*to\s*-?\d+(\.\d+)?', ln):
                    rng = re.findall(r'-?\d+(\.\d+)?\s*to\s*-?\d+(\.\d+)?(?:\s*([A-Z°\s]+))?', ln)
                    for m_rng in rng:
                        unit = m_rng[2].strip().upper() if len(m_rng) > 2 and m_rng[2] else ''
                        calib_parts.append(f"{m_rng[0]} to {m_rng[1]} {unit}".strip())
                if 'wire' in ln.lower():
                    w_match = re.search(r'(\d)-wire', ln, re.IGNORECASE)
                    if w_match:
                        wire_configs.append(f"{w_match.group(1)}-wire RTD")
            if wire_configs:
                calib_parts = wire_configs + calib_parts

            calib_parts = list(dict.fromkeys(p for p in calib_parts if p))
            calib_data = 'Y' if calib_parts else ''
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
                'Wire-on Tag':   ", ".join(wire_tags),
                'Calib Data?':   calib_data,
                'Calib Details': calib_details
            })

        except Exception as e:
            print(f"⚠️ Error parsing block: {e}")
            continue

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

    df_main  = df[df['Model Number']!='ORDER TOTAL'].copy()
    df_total = df[df['Model Number']=='ORDER TOTAL'].copy()
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

    with pdfplumber.open(file) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)

    cp_matches = re.findall(r'Customer PO(?: No)?\s*:\s*([A-Z0-9\-]+)', text, re.IGNORECASE)
    cust_po = cp_matches[-1].strip() if cp_matches else None

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

    stop_match = re.search(r'Total.*?\(USD\).*?([\d,]+\.\d{2})', text, re.IGNORECASE)
    if stop_match:
        order_total = stop_match.group(1).strip()
        text = text.split(stop_match.group(0))[0]

    blocks = re.split(r'\n(\d{5}(?:/\d{5})*)', text)
    for i in range(1, len(blocks) - 1, 2):
        raw_line_no = blocks[i].strip()
        block       = blocks[i + 1]
        block = re.sub(r'-\s*\n\s*', '-', block)

        line_nos = [ln for ln in raw_line_no.split('/')
                    if ln.isdigit() and 1 <= int(ln) <= 10000]
        if not line_nos:
            continue

        lines_clean = [l.strip() for l in block.split('\n') if l.strip()]

        model_m   = re.search(r'\b(?=[A-Z0-9\-_]*[A-Z])[A-Z0-9\-_]{6,}\b', block)
        model     = model_m.group(0) if model_m else ""

        sd        = re.search(r'Expected Ship Date:\s*(\d{2}-[A-Za-z]{3}-\d{4})', block)
        ship_date = sd.group(1) if sd else (
                      (re.search(r'([A-Za-z]{3}\s+\d{1,2},\s+\d{4})', block) or [None, ""])[1]
                    )

        qty = unit_price = total_price = ""
        m2  = re.search(r'(^|\s)(\d+)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})', block)
        if m2:
            qty, unit_price, total_price = m2.group(2), m2.group(3), m2.group(4)

        # ✅ Final universal tag logic: supports NAME, WIRE, PERM and fallback
        tags = []
        wire_on_tags = []
        qty_int = int(qty) if qty.isdigit() else 1

        # Step 1: Look for a label line (NAME, WIRE, PERM), grab the next line
        for i in range(len(lines_clean) - 1):
            label = lines_clean[i].strip().upper()
            candidate = lines_clean[i+1].strip().upper()
            if re.match(r'^(NAME|WIRE|PERM)\s*[:\s]*$', label):
                if '/' in candidate and 'IC' in candidate:
                    compound = re.sub(r'\s*/\s*', '/', candidate)
                    if re.fullmatch(r'[A-Z0-9\-_]+/[A-Z0-9\-_]+(-NC)?', compound):
                        tags.append(compound)
                        wire_on_tags.append(compound)
                        break
                elif re.fullmatch(r'[A-Z0-9\-_]{5,}', candidate):
                    tags.append(candidate)
                    wire_on_tags.append(candidate)
                    break

        # Step 2: If nothing found, fallback to lines below WIRE:
        if not tags:
            wire_idx = None
            for idx, ln in enumerate(lines_clean):
                if re.match(r'^WIRE\s*[:\s]*$', ln, re.IGNORECASE):
                    wire_idx = idx
                    break
            if wire_idx is not None:
                tag_candidates = lines_clean[wire_idx+1:]
                for line in tag_candidates:
                    tag_candidate = line.strip().upper()
                    if re.fullmatch(r'[A-Z0-9\-_]{5,}', tag_candidate):
                        tags.append(tag_candidate)
                        wire_on_tags.append(tag_candidate)
                    if len(tags) >= qty_int:
                        break

        tags = list(dict.fromkeys(tags))
        wire_on_tags = list(dict.fromkeys(wire_on_tags))
        has_tag = 'Y' if tags else 'N'

        # 🔬 Calibration logic
        calib_parts  = []
        wire_configs = []
        for idx3, ln3 in enumerate(lines_clean):
            if re.search(r'-?\d+(?:\.\d+)?\s*to\s*-?\d+(?:\.\d+)?', ln3):
                ranges    = re.findall(r'-?\d+(?:\.\d+)?\s*to\s*-?\d+(?:\.\d+)?', ln3)
                unit_clean= ""
                if idx3+1 < len(lines_clean):
                    um = re.search(
                        r'(DEG\s*[CFK]?|°C|°F|KPA|PSI|BAR|MBAR)',
                        lines_clean[idx3+1].upper()
                    )
                    if um:
                        unit_clean = um.group(0).strip().upper()
                if idx3+2 < len(lines_clean) and \
                   re.fullmatch(r'1[2-5]', lines_clean[idx3+2].strip()):
                    code = lines_clean[idx3+2].strip()[1]
                    wire_configs.append(f"{code}-wire RTD")
                for r in ranges:
                    calib_parts.append(f"{r} {unit_clean}".strip())
        if not wire_configs and any('WIRE' in ln.upper() for ln in lines_clean):
            for w in re.findall(r'\s1([2-5])\s', block):
                wire_configs.append(f"{w}-wire RTD")
        wire_configs = list(dict.fromkeys(wire_configs))
        if wire_configs:
            calib_parts = wire_configs + calib_parts
        calib_parts   = [p for p in calib_parts if p]
        calib_parts   = list(dict.fromkeys(calib_parts))
        calib_data    = 'Y' if calib_parts else 'N'
        calib_details = ", ".join(calib_parts)

        for line_no in line_nos:
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

    data.extend(tariff_rows)

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

    df['Tags'] = df['Tags'].apply(
        lambda s: ", ".join(dict.fromkeys([t.strip() for t in s.split(',') if t.strip()]))
    )

    df_main  = df[df['Model Number']!='ORDER TOTAL'].copy()
    df_total = df[df['Model Number']=='ORDER TOTAL'].copy()
    df_main = df_main.sort_values(
        by='Line No',
        key=lambda col: pd.to_numeric(col, errors='coerce'),
        ignore_index=True
    )
    df = pd.concat([df_main, df_total], ignore_index=True)
    return df


