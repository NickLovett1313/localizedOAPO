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

    # split into line‐item blocks by PO line number
    blocks = re.split(r'\n(0*\d{4,5})', text)

    for i in range(1, len(blocks) - 1, 2):
        raw_ln = blocks[i].strip()
        block  = blocks[i + 1]
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

        # —— NEW: filter out any "N/A" tags —— 
        tags = [t for t in tags if t.upper() != "N/A"]

        tags    = list(dict.fromkeys(tags))
        has_tag = 'Y' if tags else 'N'

        # ── CALIBRATION SECTION – BELOW "ADDITIONAL INFORMATION" ──
        calib_parts  = []
        wire_configs = []
        block_lines  = [ln.strip() for ln in block.split('\n') if ln.strip()]

        # locate Additional Information
        add_idx = next(
            (idx for idx, ln in enumerate(block_lines)
             if re.search(r'Additional Information', ln, re.IGNORECASE)),
            None
        )
        if add_idx is not None:
            for offset, ln_text in enumerate(block_lines[add_idx+1:]):
                idx_line = add_idx + 1 + offset

                # stop at next section
                if re.search(r'\bTag(?:s)?\b|Sold To|Ship To', ln_text, re.IGNORECASE):
                    break
                # skip invalid 2-wire
                if '2-wire' in ln_text.lower():
                    continue

                # 1) capture wire-RTD configs
                wm = re.search(r'(\d)-wire\s*RTD', ln_text, re.IGNORECASE)
                if wm:
                    wire_configs.append(f"{wm.group(1)}-wire RTD")

                # 2) capture numeric ranges + units (same line OR next line)
                for mrange in re.finditer(
                        r'(-?\d+(?:\.\d+)?)\s*to\s*(-?\d+(?:\.\d+)?)(?:\s*([A-Za-z°\sCFK%/]+))?',
                        ln_text):
                    start, end, unit_same = mrange.group(1), mrange.group(2), mrange.group(3)
                    unit = unit_same.strip() if unit_same else ""
                    # if no unit on same line, check next line for unit keywords
                    if not unit and idx_line+1 < len(block_lines):
                        um = re.search(
                            r'(DEG\s*[CFK]?|°[CFK]?|KPA|PSI|BAR|MBAR)',
                            block_lines[idx_line+1].upper()
                        )
                        if um:
                            unit = um.group(0).strip()
                    calib_parts.append(f"{start} to {end} {unit}".strip())

        # if no explicit wire configs but "wire" exists anywhere, capture broadly
        if not wire_configs and any('WIRE' in ln.upper() for ln in block_lines):
            for w in re.findall(r'(\d)-wire', "\n".join(block_lines), re.IGNORECASE):
                cfg = f"{w}-wire RTD"
                if cfg not in wire_configs:
                    wire_configs.append(cfg)

        # prepend wire configs
        if wire_configs:
            calib_parts = wire_configs + calib_parts

        # dedupe and flag
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

    # build DataFrame & apply filters
    df = pd.DataFrame(data)
    df = df[
        (pd.to_numeric(df['Line No'], errors='coerce') <= 10000) &
        (df['Qty'].str.strip() != '') &
        (df['Unit Price'].str.strip() != '') &
        (df['Total Price'].str.strip() != '')
    ].copy()

    # append ORDER TOTAL if present
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

    # sort and return
    df_main = df[df['Model Number'] != 'ORDER TOTAL'].copy()
    df_total= df[df['Model Number'] == 'ORDER TOTAL'].copy()
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

    # 3) Pull off the final total
    stop_match = re.search(r'Total.*?\(USD\).*?([\d,]+\.\d{2})', text, re.IGNORECASE)
    if stop_match:
        order_total = stop_match.group(1).strip()
        text = text.split(stop_match.group(0))[0]

    # 4) Split into blocks by 5-digit OA line numbers
    blocks = re.split(r'\n(\d{5}(?:/\d{5})*)', text)
    for i in range(1, len(blocks) - 1, 2):
        raw_line_no = blocks[i].strip()
        block       = blocks[i + 1]

        # —— merge hyphen-broken across lines as before
        block = re.sub(r'-\s*\n\s*', '-', block)

        # filter valid line numbers
        line_nos = [ln for ln in raw_line_no.split('/')
                    if ln.isdigit() and 1 <= int(ln) <= 10000]
        if not line_nos:
            continue

        tag_block            = block.replace(cust_po, " ") if cust_po else block
        contains_tag_section = bool(re.search(r'\bTag\b', block, re.IGNORECASE))
        lines_clean          = [l.strip() for l in block.split('\n') if l.strip()]

        for line_no in line_nos:
            # Model Number
            model_m   = re.search(r'\b(?=[A-Z0-9\-_]*[A-Z])[A-Z0-9\-_]{6,}\b', block)
            model     = model_m.group(0) if model_m else ""

            # Ship Date
            sd        = re.search(r'Expected Ship Date:\s*(\d{2}-[A-Za-z]{3}-\d{4})', block)
            ship_date = sd.group(1) if sd else (
                          (re.search(r'([A-Za-z]{3}\s+\d{1,2},\s+\d{4})', block) or [None, ""])[1]
                        )

            # Qty / Unit / Total
            qty = unit_price = total_price = ""
            m2  = re.search(r'(^|\s)(\d+)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})', block)
            if m2:
                qty, unit_price, total_price = m2.group(2), m2.group(3), m2.group(4)

            # === TAG SECTION LOGIC ===
            tags    = []
            skip_ic = set()

            # 0) NAME-line override
            name_tag = None
            for idx, ln in enumerate(lines_clean):
                if re.match(r'^NAME\s*[:\s]*$', ln, re.IGNORECASE):
                    if idx + 1 < len(lines_clean):
                        cand = lines_clean[idx + 1].strip()
                        if cand:
                            name_tag = cand.upper()
                    break
            if name_tag:
                tags.append(name_tag)
            else:
                if contains_tag_section:
                    # 1) slash-compounds
                    raw_comps = re.findall(
                        r'\b[A-Z0-9\-_]+(?:\s*/\s*IC\d{2,5}-NC)\b',
                        tag_block, re.IGNORECASE
                    )
                    compounds = [re.sub(r'\s*/\s*','/', rc.upper()) for rc in raw_comps]
                    for comp in compounds:
                        if cust_po and (comp == cust_po or comp.startswith(cust_po)):
                            continue
                        tags.append(comp)
                        skip_ic.add(comp.split('/',1)[1])

                    temp_block = tag_block
                    for raw in raw_comps:
                        temp_block = re.sub(re.escape(raw), ' ', temp_block, flags=re.IGNORECASE)

                    # 2) generic tags
                    for t in re.findall(r'\b[A-Z0-9]{2,}-[A-Z0-9\-]{2,}\b', temp_block):
                        if cust_po and (t == cust_po or t.startswith(cust_po)):
                            continue
                        has_letters  = bool(re.search(r'[A-Z]', t))
                        has_digits   = bool(re.search(r'\d', t))
                        is_all_digits= bool(re.fullmatch(r'[\d\-]+', t))
                        is_date      = bool(re.search(r'\d{1,2}[-/][A-Za-z]{3}[-/]\d{4}', t))
                        ok_len       = 5 <= len(t) <= 50
                        if has_letters and has_digits and not is_all_digits and not is_date and ok_len:
                            tags.append(t)

                # universal IC/NC
                for ic in set(re.findall(r'\bIC\d{2,5}(?:-NC)?\b', block, re.IGNORECASE)):
                    icn = ic.upper()
                    if icn not in skip_ic:
                        tags.append(icn)

            # repair split compounds
            for idx, ln_text in enumerate(lines_clean):
                m_split = re.match(
                    r'^([A-Z0-9\-_]+)\s*/\s*(IC\d{2,5})-$',
                    ln_text, re.IGNORECASE
                )
                if m_split and idx+1 < len(lines_clean) \
                   and lines_clean[idx+1].strip().upper() == 'NC':
                    comp = f"{m_split.group(1).upper()}/{m_split.group(2).upper()}-NC"
                    if comp not in tags:
                        tags.append(comp)

            # catch any slash-compound without "-NC"
            for ln_text in lines_clean:
                if '/' in ln_text and 'NC' not in ln_text.upper():
                    parts = re.split(r'\s*/\s*', ln_text)
                    if len(parts) == 2:
                        left, right = parts[0].strip().upper(), parts[1].strip().upper()
                        if re.fullmatch(r'[A-Z0-9\-_]+', left) and \
                           re.fullmatch(r'[A-Z0-9\-]+', right):
                            comp = f"{left}/{right}"
                            if comp not in tags:
                                tags.append(comp)

            # drop incomplete split tags
            tags = [t for t in tags if not t.endswith('-')]

            # ——— NEW: remove any “subtag” t if it’s contained in a larger tag t2 ———
            tags = [
                t for t in tags
                if not any(t != t2 and t in t2 for t2 in tags)
            ]

            # post-process qty=1
            if qty.isdigit() and int(qty) == 1:
                slash_tags = [t for t in tags if '/' in t]
                if slash_tags:
                    tags = slash_tags

            # dedupe & expand by qty
            tags = list(dict.fromkeys(tags))
            if qty.isdigit() and int(qty) > 1:
                tags = [t for t in tags for _ in range(int(qty))]

            wire_on_tags = [t for t in tags if '/' in t]
            has_tag = 'Y' if tags else 'N'

            # === calibration logic (unchanged) ===
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

    # 9) Append surcharge rows
    data.extend(tariff_rows)

    # 10) Build DataFrame & append ORDER TOTAL
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

    # Remove duplicate in Tags column
    df['Tags'] = df['Tags'].apply(
        lambda s: ", ".join(dict.fromkeys([t.strip() for t in s.split(',') if t.strip()]))
    )

    # 11) Final sort
    df_main  = df[df['Model Number']!='ORDER TOTAL'].copy()
    df_total = df[df['Model Number']=='ORDER TOTAL'].copy()
    df_main = df_main.sort_values(
        by='Line No',
        key=lambda col: pd.to_numeric(col, errors='coerce'),
        ignore_index=True
    )
    df = pd.concat([df_main, df_total], ignore_index=True)
    return df


