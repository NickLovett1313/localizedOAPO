import pandas as pd
from itertools import groupby
from operator import itemgetter

def normalize_line_no(val):
    return str(val).lstrip("0") or "0"

def compare_oa_po(oa_df, po_df):
    output_text = []
    date_discrepancies = []

    # Normalize line numbers
    oa_df["Line No"] = oa_df["Line No"].apply(normalize_line_no)
    po_df["Line No"] = po_df["Line No"].apply(normalize_line_no)

    oa_df.set_index("Line No", inplace=True)
    po_df.set_index("Line No", inplace=True)

    all_lines = sorted(set(oa_df.index) | set(po_df.index), key=lambda x: int(x) if x.isdigit() else 99999)

    discrepancies = []
    
    for line in all_lines:
        oa_row = oa_df.loc[[line]] if line in oa_df.index else pd.DataFrame()
        po_row = po_df.loc[[line]] if line in po_df.index else pd.DataFrame()

        if oa_row.empty or po_row.empty:
            discrepancies.append({
                "Line": line,
                "Issue": "Line missing from OA" if po_row.empty else "Line missing from PO"
            })
            continue

        # Dates
        oa_date = oa_row["Ship Date"].values[0]
        po_date = po_row["Ship Date"].values[0]
        if oa_date != po_date:
            date_discrepancies.append((line, oa_date, po_date))

        # Model number
        if oa_row["Model Number"].values[0] != po_row["Model Number"].values[0]:
            discrepancies.append({
                "Line": line,
                "Issue": "Model mismatch",
                "OA": oa_row["Model Number"].values[0],
                "PO": po_row["Model Number"].values[0]
            })

        # Price
        if oa_row["Total Price"].values[0] != po_row["Total Price"].values[0]:
            discrepancies.append({
                "Line": line,
                "Issue": "Total price mismatch",
                "OA": oa_row["Total Price"].values[0],
                "PO": po_row["Total Price"].values[0]
            })

        # Tags logic
        oa_tags = set(str(oa_row["Tags"].values[0]).split(", "))
        wire_tags = set(str(oa_row["Wire-on Tag"].values[0]).split(", "))
        unmatched_tags = wire_tags - oa_tags
        if unmatched_tags:
            discrepancies.append({
                "Line": line,
                "Issue": "Wire-on tag(s) not found in Tags",
                "Wire-on Tag(s)": ", ".join(unmatched_tags),
                "Tags": oa_row["Tags"].values[0]
            })

    # Tariff logic
    oa_tariff = oa_df[oa_df["Model Number"].str.contains("TARIFF", na=False)]
    po_tariff = po_df[po_df["Model Number"].str.contains("TARIFF", na=False)]
    tariff_diff = False
    if not oa_tariff.empty and po_tariff.empty:
        tariff_amount = oa_tariff["Total Price"].astype(str).str.replace(",", "").astype(float).sum()
        oa_total = oa_df[oa_df["Model Number"] == "ORDER TOTAL"]["Total Price"].astype(str).str.replace(",", "").astype(float).sum()
        po_total = po_df[po_df["Model Number"] == "ORDER TOTAL"]["Total Price"].astype(str).str.replace(",", "").astype(float).sum()
        note = ""
        if abs(oa_total - po_total - tariff_amount) < 0.01:
            note = " (**note that the order total differs by exactly the amount of the tariff charge**)"
        discrepancies.append({
            "Line": "-",
            "Issue": f"TARIFF charge is missing from PO{note}"
        })

    # Order total mismatch
    if not oa_df[oa_df['Model Number'] == 'ORDER TOTAL'].empty and not po_df[po_df['Model Number'] == 'ORDER TOTAL'].empty:
        oa_total = oa_df[oa_df["Model Number"] == "ORDER TOTAL"]["Total Price"].astype(str).str.replace(",", "").astype(float).sum()
        po_total = po_df[po_df["Model Number"] == "ORDER TOTAL"]["Total Price"].astype(str).str.replace(",", "").astype(float).sum()
        if abs(oa_total - po_total) >= 0.01 and not tariff_diff:
            discrepancies.append({
                "Line": "-",
                "Issue": "ORDER TOTAL mismatch",
                "OA": f"${oa_total:,.2f}",
                "PO": f"${po_total:,.2f}"
            })

    # Build outputs
    summary = "I have reviewed the OA and Factory PO for this order and found the following discrepancies:"
    if not discrepancies and not date_discrepancies:
        summary = "I have reviewed the OA and Factory PO for this order and found **no discrepancies**. Everything else looked good."

    date_table = build_date_table(date_discrepancies) if date_discrepancies else ""

    discrepancies_df = pd.DataFrame(discrepancies)
    return summary, date_table, discrepancies_df

# 🧠 Date Table Formatter
def build_date_table(date_discrepancies):
    # Group by OA/PO date pair
    grouped = {}
    for line, oa_date, po_date in date_discrepancies:
        key = (oa_date, po_date)
        grouped.setdefault(key, []).append(int(line) if line.isdigit() else 99999)

    rows = []
    for (oa_date, po_date), lines in grouped.items():
        lines = sorted(lines)
        line_str = f"Line {lines[0]}" if len(lines) == 1 else f"Lines {lines[0]}–{lines[-1]}"
        rows.append((line_str, oa_date, po_date))

    df = pd.DataFrame(rows, columns=["Line(s)", "OA Expected Dates", "Factory PO requested dates"])
    return df
