import pdfplumber
import pandas as pd
import re

def parse_po(file):
    data = []
    order_total = ""

    with pdfplumber.open(file) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)

    # extract order total
    stop_match = re.search(r'Order total.*?\$?USD.*?([\d,]+\.\d{2})', text, re.IGNORECASE)
    if stop_match:
        order_total = stop_match.group(1).strip()

    # truncate after GST or order total marker
    gst_match = re.search(r'SPARTAN.*?GST#.*', text, re.IGNORECASE)
    if gst_match:
        pos = text.lower().find(gst_match.group(0).lower()) + len(gst_match.group(0))
        text = text[:pos]
    elif stop_match:
        text = text.split(stop_match.group(0))[0]

    # ✅ New robust line block splitter
    lines = text.split('\n')
    blocks = []
    current_block = []
    for line in lines:
        line = line.strip()
        if re.match(r'^0*\d{4,5}\b', line):  # Start of new PO line
            if current_block:
                blocks.append(current_block)
            current_block = [line]
        elif current_block:
            current_block.append(line)
    if current_block:
        blocks.append(current_block)

    for block_lines in blocks:
        try:
            block = "\n".join(block_lines)

            raw_ln = block_lines[0].strip().split()[0]
            if not raw_ln.isdigit():
                continue
            ln = int(raw_ln)
            if ln <= 0:
                continue

            # Model Number
            model_m   = re.search(r'([A-Z0-9\-_]{6,})', block)
            model_str = model_m.group(1) if model_m else ''

            # Ship Date
            ship_date_m = re.search(r'([A-Za-z]{3} \d{1,2}, \d{4})', block)
            ship_date   = ship_date_m.group(1) if ship_date_m else ''

            # Qty / Unit Price / Total Price
            qty = unit_price = total_price = ""
            m = re.search(r'(\d+)\s+EA\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})', block)
            if m:
                qty, unit_price, total_price = m.group(1), m.group(2), m.group(3)

            # TAG section (unchanged)
            tag_section = ""
            tag_hdr     = re.search(r'\bTag(?:s)?\b', block, re.IGNORECASE)
            sold_to     = re.search(r'\bSold To\b', block, re.IGNORECASE)
            if tag_hdr:
                start = tag_hdr.end()
                end   = sold_to.start() if sold_to else len(block)
                tag_section = block[start:end]

            slash_comps = []
            for raw in re.findall(r'\b[A-Z0-9\-_]+\s*/\s*[A-Z0-9\-]+(?:-NC)?\b', tag_section, re.IGNORECASE):
                slash_comps.append(re.sub(r'\s*/\s*', '/', raw.upper()))

            comp_parts = {p for comp in slash_comps for p in comp.split('/',1)}

            tags = slash_comps.copy()
            for raw in re.findall(r'\b[A-Z0-9]{2,}-[A-Z0-9\-]{2,}\b', tag_section):
                norm = raw.upper()
                if norm in comp_parts:
                    continue
                is_date       = bool(re.search(r'\d{1,2}[-/][A-Za-z]{3}[-/]\d{4}', norm))
                is_all_digits = bool(re.fullmatch(r'[\d\-]+', norm))
                has_letter    = bool(re.search(r'[A-Z]', norm))
                has_digit     = bool(re.search(r'\d', norm))
                if has_letter and has_digit and not is_date and not is_all_digits:
                    tags.append(norm)

            tags = [t for t in tags if t.upper() != "N/A"]
            tags = list(dict.fromkeys(tags))
            has_tag = 'Y' if tags else 'N'

            # ── CALIBRATION SECTION – BELOW "ADDITIONAL INFORMATION"
            calib_parts  = []
            wire_configs = []
            block_lines_clean = [ln.strip() for ln in block.split('\n') if ln.strip()]

            add_idx = next(
                (idx for idx, ln in enumerate(block_lines_clean)
                 if re.search(r'Additional Information', ln, re.IGNORECASE)),
                None
            )
            if add_idx is not None:
                for offset, ln_text in enumerate(block_lines_clean[add_idx+1:]):
                    idx_line = add_idx + 1 + offset
                    if re.search(r'\bTag(?:s)?\b|Sold To|Ship To', ln_text, re.IGNORECASE):
                        break
                    if '2-wire' in ln_text.lower():
                        continue
                    wm = re.search(r'(\d)-wire\s*RTD', ln_text, re.IGNORECASE)
                    if wm:
                        wire_configs.append(f"{wm.group(1)}-wire RTD")

                    for mrange in re.finditer(
                            r'(-?\d+(?:\.\d+)?)\s*to\s*(-?\d+(?:\.\d+)?)(?:\s*([A-Za-z°\sCFK%/]+))?',
                            ln_text):
                        start, end, unit_same = mrange.group(1), mrange.group(2), mrange.group(3)
                        unit = unit_same.strip() if unit_same else ""
                        if not unit and idx_line+1 < len(block_lines_clean):
                            um = re.search(
                                r'(DEG\s*[CFK]?|°[CFK]?|KPA|PSI|BAR|MBAR)',
                                block_lines_clean[idx_line+1].upper()
                            )
                            if um:
                                unit = um.group(0).strip()
                        calib_parts.append(f"{start} to {end} {unit}".strip())

            if not wire_configs and any('WIRE' in ln.upper() for ln in block_lines_clean):
                for w in re.findall(r'(\d)-wire', "\n".join(block_lines_clean), re.IGNORECASE):
                    cfg = f"{w}-wire RTD"
                    if cfg not in wire_configs:
                        wire_configs.append(cfg)

            if wire_configs:
                calib_parts = wire_configs + calib_parts

            calib_parts   = [p for p in calib_parts if p]
            calib_parts   = list(dict.fromkeys(calib_parts))
            calib_data    = 'Y' if calib_parts else ''
            calib_details = ", ".join(calib_parts)

            data.append({
                'Line No':       ln,
                'Model Number':  model_str,
                'Ship Date':     ship_date,
                'Qty':           qty,
                'Unit Price':    unit_price,
                'Total Price':   total_price,
                'Has Tag?':      has_tag,
                'Tags':          ", ".join(tags),
                'Wire-on Tag':   "",
                'Calib Data?':   calib_data,
                'Calib Details': calib_details
            })
        except Exception as e:
            print(f"⚠️ Error parsing block {ln}: {e}")
            continue

    df = pd.DataFrame(data)
    df = df[
        (pd.to_numeric(df['Line No'], errors='coerce') <= 10000) &
        (df['Qty'].str.strip() != '') &
        (df['Unit Price'].str.strip() != '') &
        (df['Total Price'].str.strip() != '')
    ].copy()

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

    df_main  = df[df['Model Number'] != 'ORDER TOTAL'].copy()
    df_total = df[df['Model Number'] == 'ORDER TOTAL'].copy()
    df_main['Line No'] = pd.to_numeric(df_main['Line No'], errors='coerce')
    df_main = df_main.sort_values(by='Line No', ignore_index=True)
    df = pd.concat([df_main, df_total], ignore_index=True)

    return df

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


