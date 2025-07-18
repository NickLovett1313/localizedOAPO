import pandas as pd
import difflib

def normalize_line(line):
    try:
        return str(int(str(line).strip().lstrip("0")))
    except:
        return str(line).strip()

def group_lines_by_date(df, date_col, line_col):
    df = df[[line_col, date_col]].dropna()
    df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
    df[line_col] = df[line_col].apply(normalize_line)
    df = df.dropna()

    grouped = []
    current_group = []
    current_date = None

    for _, row in df.sort_values(line_col, key=lambda x: x.astype(int)).iterrows():
        line = row[line_col]
        date = row[date_col]

        if current_date is None:
            current_group = [line]
            current_date = date
        elif date == current_date:
            current_group.append(line)
        else:
            grouped.append((current_group, current_date))
            current_group = [line]
            current_date = date

    if current_group:
        grouped.append((current_group, current_date))

    return grouped

def make_line_range(lines):
    lines = sorted([int(x) for x in lines])
    if len(lines) == 1:
        return f"Line {lines[0]}"
    else:
        return f"Lines {lines[0]}–{lines[-1]}"

def loose_unit_match(val1, val2):
    def simplify(unit):
        return unit.lower().replace(" ", "").replace("°", "").replace("deg", "").replace("g", "")
    return simplify(val1) == simplify(val2)

def highlight_diff(str1, str2):
    return ''.join([
        f"[{s2}]" if s1 != s2 else s1
        for s1, s2 in zip(str1, str2)
    ])

def compare_oa_po(po_df, oa_df):
    discrepancies = []

    # Normalize line numbers
    po_df["Line No"] = po_df["Line No"].apply(normalize_line)
    oa_df["Line No"] = oa_df["Line No"].apply(normalize_line)

    # DATE DISCREPANCIES
    po_grouped = group_lines_by_date(po_df, "Ship Date", "Line No")
    oa_grouped = group_lines_by_date(oa_df, "Expected Ship Date", "Line No")

    date_rows = []
    for (oa_lines, oa_date) in oa_grouped:
        for (po_lines, po_date) in po_grouped:
            intersect = list(set(oa_lines) & set(po_lines))
            if intersect and oa_date != po_date:
                date_rows.append({
                    "OA Lines": make_line_range(intersect),
                    "OA Date": oa_date.strftime("%b %d, %Y"),
                    "PO Lines": make_line_range(intersect),
                    "PO Date": po_date.strftime("%b %d, %Y")
                })

    if date_rows:
        discrepancies.append("1. The dates between the factory PO and OA are different as follows:")
        for row in date_rows:
            discrepancies.append(
                f"→ {row['OA Lines']} (OA: {row['OA Date']}) vs {row['PO Lines']} (PO: {row['PO Date']})"
            )

    # Merge OA and PO dataframes on Line No (may have multiple entries)
    merged_lines = sorted(set(po_df["Line No"]).union(set(oa_df["Line No"])), key=lambda x: int(x))

    for line in merged_lines:
        po_lines = po_df[po_df["Line No"] == line]
        oa_lines = oa_df[oa_df["Line No"] == line]

        if po_lines.empty:
            discrepancies.append(f"Line {line} is present in OA but missing in PO.")
            continue
        if oa_lines.empty:
            discrepancies.append(f"Line {line} is present in PO but missing in OA.")
            continue

        po_row = po_lines.fillna("").agg(' '.join)
        oa_row = oa_lines.fillna("").agg(' '.join)

        # Model Number check
        po_model = po_row.get("Vendor Item Number Description", "").strip()
        oa_model = oa_row.get("Description", "").strip()
        if po_model != oa_model:
            differences = highlight_diff(oa_model, po_model)
            discrepancies.append(
                f"Line {line}: Model numbers do not match.\n"
                f"    → OA: {oa_model}\n"
                f"    → PO: {po_model}\n"
                f"    → Diff: {differences}"
            )

        # Unit price
        if po_row.get("Extended Price", "") != oa_row.get("Total Amount", ""):
            discrepancies.append(
                f"Line {line}: Total price mismatch. OA: {oa_row.get('Total Amount')} vs PO: {po_row.get('Extended Price')}"
            )

        # Tags
        has_tag_oa = oa_row.get("Has Tag?", "N")
        has_tag_po = po_row.get("Has Tag?", "N")
        if has_tag_oa == "Y" or has_tag_po == "Y":
            oa_tag = oa_row.get("Tags", "").strip()
            oa_wire_tag = oa_row.get("Wire-on Tag", "").strip()
            po_tag = po_row.get("Tags", "").strip()

            if oa_wire_tag and oa_tag and oa_wire_tag != oa_tag:
                discrepancies.append(
                    f"Line {line}: Wire-on Tag and Tag differ on OA. Wire-on: {oa_wire_tag}, Tag: {oa_tag}"
                )

            if oa_tag != po_tag:
                discrepancies.append(
                    f"Line {line}: Tag mismatch. OA: {oa_tag} vs PO: {po_tag}"
                )

        # Calibration Data
        calib_oa = oa_row.get("Calib Data?", "N")
        calib_po = po_row.get("Calib Data?", "N")

        if calib_oa == "Y" or calib_po == "Y":
            if calib_oa != calib_po:
                discrepancies.append(f"Line {line}: Calibration data flag mismatch. OA: {calib_oa}, PO: {calib_po}")
            else:
                oa_details = oa_row.get("Calib Details", "")
                po_details = po_row.get("Calib Details", "")
                if not loose_unit_match(oa_details, po_details):
                    discrepancies.append(
                        f"Line {line}: Calibration data mismatch.\n"
                        f"    → OA: {oa_details}\n"
                        f"    → PO: {po_details}"
                    )

    # Order total check
    po_total = po_df.get("ORDER TOTAL", pd.Series()).values
    oa_total = oa_df.get("ORDER TOTAL", pd.Series()).values
    if len(po_total) and len(oa_total):
        try:
            po_val = float(po_total[0])
            oa_val = float(oa_total[0])
            if po_val != oa_val:
                tariff = 0
                if "Tariff" in oa_df["Description"].values:
                    tariff = float(oa_df[oa_df["Description"].str.contains("Tariff", na=False)]["Total Amount"].astype(float).sum())
                if abs(po_val - oa_val) == tariff:
                    discrepancies.append("Order Total differs, but difference is exactly due to the tariff charge.")
                else:
                    discrepancies.append(f"Order Total mismatch. OA: {oa_val}, PO: {po_val}")
        except:
            pass

    return discrepancies
