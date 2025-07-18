import pdfplumber
import pandas as pd
import re

def parse_po(file):
    data = []
    order_total = ""

    # 1) Read full PDF text
    with pdfplumber.open(file) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)

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

    # 4) Split into blocks by line number
    blocks = re.split(r'\n(0*\d{4,5})', text)

    for i in range(1, len(blocks) - 1, 2):
        raw_ln = blocks[i].strip()
        block  = blocks[i + 1]
        if not raw_ln.isdigit():
            continue
        ln = int(raw_ln)
        if ln <= 0:
            continue

        # extract model, dates, pricing
        model_m    = re.search(r'([A-Z0-9\-_]{6,})', block)
        model_str  = model_m.group(1) if model_m else ''
        ship_date_m = re.search(r'([A-Za-z]{3} \d{1,2}, \d{4})', block)
        ship_date   = ship_date_m.group(1) if ship_date_m else ''
        qty = unit_price = total_price = ""
        m = re.search(r'(\d+)\s+EA\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})', block)
        if m:
            qty, unit_price, total_price = m.group(1), m.group(2), m.group(3)

        # ── Isolate only the text under the "Tag(s)" heading and before "Sold To:" ──
        tag_section = ""
        tag_hdr = re.search(r'\bTag(?:s)?\b', block, re.IGNORECASE)
        sold_to = re.search(r'\bSold To\b', block, re.IGNORECASE)
        if tag_hdr:
            start = tag_hdr.end()
            end   = sold_to.start() if sold_to else len(block)
            tag_section = block[start:end]

        # ── SLASH-COMPOUND TAGS ──
        slash_comps = []
        for raw in re.findall(r'\b[A-Z0-9\-_]+\s*/\s*[A-Z0-9\-]+(?:-NC)?\b', tag_section, re.IGNORECASE):
            comp = re.sub(r'\s*/\s*', '/', raw.upper())
            slash_comps.append(comp)

        # build set of any parts of those compounds to skip
        comp_parts = set()
        for comp in slash_comps:
            left, right = comp.split('/', 1)
            comp_parts.add(left)
            comp_parts.add(right)

        # ── GENERIC TAGS ──
        tags = slash_comps.copy()
        for raw in re.findall(r'\b[A-Z0-9]{2,}-[A-Z0-9\-]{2,}\b', tag_section):
            norm = raw.upper()
            # skip if it's part of a slash-compound
            if norm in comp_parts:
                continue
            # filter out dates or all-digits
            is_date      = bool(re.search(r'\d{1,2}[-/][A-Za-z]{3}[-/]\d{4}', norm))
            is_all_digits= bool(re.fullmatch(r'[\d\-]+', norm))
            has_letter   = bool(re.search(r'[A-Z]', norm))
            has_digit    = bool(re.search(r'\d', norm))
            if has_letter and has_digit and not is_date and not is_all_digits:
                tags.append(norm)

        # ── DEDUPE & FINALIZE ──
        tags = list(dict.fromkeys(tags))
        has_tag = 'Y' if tags else 'N'

        # ── Calibration detection (full version) ──
        calib_parts = []
        wire_configs = []
        lines = [line.strip() for line in block.split('\n') if line.strip()]

        for idx, line in enumerate(lines):
            # Detect ranges
            if re.search(r'-?\d+(?:\.\d+)?\s*to\s*-?\d+(?:\.\d+)?', line):
                ranges = re.findall(r'-?\d+(?:\.\d+)?\s*to\s*-?\d+(?:\.\d+)?', line)
                unit = ""
                if idx+1 < len(lines):
                    um = re.search(
                        r'(DEG\s*[CFK]?|°C|°F|KPA|KPAG|PSI|BAR|MBAR)',
                        lines[idx+1].upper()
                    )
                    if um:
                        unit = um.group(0).strip().upper()
                for r in ranges:
                    calib_parts.append(f"{r} {unit}".strip())

            # Detect wire types from values like "1 3" or "3-WIRE"
            if re.search(r'\b1[2-5]\b', line):
                matches = re.findall(r'\b1([2-5])\b', line)
                for w in matches:
                    wire_configs.append(f"{w}-wire RTD")

            if re.search(r'\b([2-5])-?WIRE\b', line.upper()):
                wire_match = re.findall(r'\b([2-5])-?WIRE\b', line.upper())
                for w in wire_match:
                    wire_configs.append(f"{w}-wire RTD")

        # Append wire types to the beginning of calibration list
        wire_configs = list(dict.fromkeys(wire_configs))
        if wire_configs:
            calib_parts = wire_configs + calib_parts

        # ✅ Final cleanup and dedup
        calib_parts = [part.strip() for part in calib_parts if part.strip()]
        calib_parts = list(dict.fromkeys(calib_parts))
        calib_data  = 'Y' if calib_parts else 'N'
        calib_detail = ", ".join(calib_parts)

        data.append({
            'Line No':       ln,
            'Model Number':  model_str,
            'Ship Date':     ship_date,
            'Qty':           qty,
            'Unit Price':    unit_price,
            'Total Price':   total_price,
            'Has Tag?':      has_tag,
            'Tags':          ", ".join(tags),
            'Wire-on Tag':   "",  # still blank
            'Calib Data?':   calib_data,
            'Calib Details': calib_detail
        })

    # 🔒 Hard Cleanup Step
    df = pd.DataFrame(data)
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
                    # 1) Grab whole-string slash-compounds (flexible spaces)
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

                    # remove those compounds before generic extraction
                    temp_block = tag_block
                    for raw in raw_comps:
                        temp_block = re.sub(re.escape(raw), ' ', temp_block, flags=re.IGNORECASE)

                    # 2) Original generic-tag extraction
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

                # Universal IC/NC detection
                for ic in set(re.findall(r'\bIC\d{2,5}(?:-NC)?\b', block, re.IGNORECASE)):
                    icn = ic.upper()
                    if icn not in skip_ic:
                        tags.append(icn)

            # Repair split slash-compounds across lines
            for idx, ln_text in enumerate(lines_clean):
                m_split = re.match(r'^([A-Z0-9\-_]+)\s*/\s*(IC\d{2,5})-$', ln_text, re.IGNORECASE)
                if m_split and idx+1 < len(lines_clean) and lines_clean[idx+1].strip().upper() == 'NC':
                    comp = f"{m_split.group(1).upper()}/{m_split.group(2).upper()}-NC"
                    if comp not in tags:
                        tags.append(comp)

            # Catch any slash-compound without "-NC"
            for ln_text in lines_clean:
                if '/' in ln_text and 'NC' not in ln_text.upper():
                    parts = re.split(r'\s*/\s*', ln_text)
                    if len(parts) == 2:
                        left, right = parts[0].strip().upper(), parts[1].strip().upper()
                        if re.fullmatch(r'[A-Z0-9\-_]+', left) and re.fullmatch(r'[A-Z0-9\-]+', right):
                            comp = f"{left}/{right}"
                            if comp not in tags:
                                tags.append(comp)

            # Compute wire-on tags
            wire_on_tags = [t for t in tags if '/' in t]

            # ── NEW FILTER: drop any incomplete split tags ending in '-' ──
            tags = [t for t in tags if not t.endswith('-')]
            wire_on_tags = [t for t in wire_on_tags if not t.endswith('-')]

            # ── POST-PROCESSING FOR QTY == 1 ──
            if qty.isdigit() and int(qty) == 1:
                slash_tags = [t for t in tags if '/' in t]
                if slash_tags:
                    tags = slash_tags
                    wire_on_tags = slash_tags

            # Dedupe & replicate by quantity
            tags = list(dict.fromkeys(tags))
            if qty.isdigit() and int(qty) > 1:
                tags = [t for t in tags for _ in range(int(qty))]

            wire_on_tags = list(dict.fromkeys(wire_on_tags))
            has_tag = 'Y' if tags else 'N'

            # === Calibration/configuration logic (with deduplication) ===
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
                    if idx3+2 < len(lines_clean) and re.fullmatch(r'1[2-5]', lines_clean[idx3+2].strip()):
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

            # ✅ Deduplicate calibration entries
            calib_parts = [part.strip() for part in calib_parts if part.strip()]
            calib_parts = list(dict.fromkeys(calib_parts))
            calib_data  = 'Y' if calib_parts else 'N'
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

    # — Remove duplicate in Tags column —
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
