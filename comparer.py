import pandas as pd
from difflib import ndiff

def normalize_line(line):
    try:
        return str(int(str(line).lstrip("0")))
    except:
        return str(line).strip()

def clean_tags(val):
    return [t.strip() for t in val.split(',') if t.strip()] if isinstance(val, str) else []

def compare_oa_po(po_df, oa_df):
    try:
        # Normalize line numbers
        po_df['Line No'] = po_df['Line No'].apply(normalize_line)
        oa_df['Line No'] = oa_df['Line No'].apply(normalize_line)

        po_groups = po_df.groupby('Line No')
        oa_groups = oa_df.groupby('Line No')

        all_lines = set(po_df['Line No'].dropna().astype(str)) | set(oa_df['Line No'].dropna().astype(str))

        discrepancies = []
        date_discrepancies = []

        for line in sorted(all_lines, key=lambda x: int(x) if x.isdigit() else 99999):
            po_rows = po_groups.get_group(line) if line in po_groups.groups else pd.DataFrame()
            oa_rows = oa_groups.get_group(line) if line in oa_groups.groups else pd.DataFrame()

            if po_rows.empty:
                discrepancies.append(("Line Missing in PO", line, "", "Present in OA only"))
                continue
            if oa_rows.empty:
                discrepancies.append(("Line Missing in OA", line, "Present in PO only", ""))
                continue

            po_row = po_rows.iloc[0]
            oa_row = oa_rows.iloc[0]

            # Model Number
            if po_row['Model Number'] != oa_row['Model Number']:
                diff = '\n'.join(ndiff([str(po_row['Model Number'])], [str(oa_row['Model Number'])]))
                discrepancies.append(("Model Number", line, po_row['Model Number'], oa_row['Model Number'] + "\n" + diff))

            # Ship Date
            if po_row['Ship Date'] != oa_row['Ship Date']:
                date_discrepancies.append((line, oa_row['Ship Date'], po_row['Ship Date']))

            # Quantity
            if po_row['Qty'] != oa_row['Qty']:
                discrepancies.append(("Quantity", line, po_row['Qty'], oa_row['Qty']))

            # Unit Price
            if po_row['Unit Price'] != oa_row['Unit Price']:
                discrepancies.append(("Unit Price", line, po_row['Unit Price'], oa_row['Unit Price']))

            # Total Price
            if po_row['Total Price'] != oa_row['Total Price']:
                discrepancies.append(("Total Price", line, po_row['Total Price'], oa_row['Total Price']))

            # Tags
            po_tags = clean_tags(po_row.get('Tags', ''))
            oa_tags = clean_tags(oa_row.get('Tags', ''))
            wire_tags = clean_tags(oa_row.get('Wire-on Tag', ''))

            if sorted(po_tags * int(po_row.get('Qty') or 1)) != sorted(oa_tags):
                discrepancies.append(("Tag Mismatch", line, ", ".join(po_tags), ", ".join(oa_tags)))

            if wire_tags and set(wire_tags) != set(oa_tags):
                discrepancies.append(("Wire-on Tag Mismatch", line, ", ".join(wire_tags), ", ".join(oa_tags)))

            # Calibration details
            if oa_row.get("Calib Details", "") and po_row.get("Calib Details", ""):
                if oa_row["Calib Details"].lower().strip() != po_row["Calib Details"].lower().strip():
                    discrepancies.append(("Calibration Details", line, po_row["Calib Details"], oa_row["Calib Details"]))

        # Check order total
        po_total = po_df[po_df['Model Number'] == 'ORDER TOTAL']['Total Price'].values
        oa_total = oa_df[oa_df['Model Number'] == 'ORDER TOTAL']['Total Price'].values

        if len(po_total) and len(oa_total):
            po_amt = float(po_total[0].replace(',', ''))
            oa_amt = float(oa_total[0].replace(',', ''))
            if po_amt != oa_amt:
                # Check for tariff
                tariff_rows = oa_df[oa_df['Model Number'].str.contains('TARIFF', na=False, case=False)]
                if not tariff_rows.empty:
                    tariff_amt = sum(float(val.replace(',', '')) for val in tariff_rows['Total Price'] if val)
                    if abs(po_amt + tariff_amt - oa_amt) < 0.01:
                        note = f"**note that the order total differs by exactly the amount of the tariff charge**"
                        discrepancies.append(("Order Total", "", f"${po_amt:,.2f}", f"${oa_amt:,.2f}  \n{note}"))
                    else:
                        discrepancies.append(("Order Total", "", f"${po_amt:,.2f}", f"${oa_amt:,.2f}"))
                else:
                    discrepancies.append(("Order Total", "", f"${po_amt:,.2f}", f"${oa_amt:,.2f}"))

        # Check if PO is missing any tariff lines
        oa_tariffs = oa_df[oa_df['Model Number'].str.contains('TARIFF', na=False, case=False)]
        po_tariffs = po_df[po_df['Model Number'].str.contains('TARIFF', na=False, case=False)]
        if not oa_tariffs.empty and po_tariffs.empty:
            discrepancies.append(("Tariff Charge", "", "Missing from PO", "Present in OA"))

        summary = "I have reviewed the OA and Factory PO for this order and found the following discrepancies:" if discrepancies or date_discrepancies else "I have reviewed the OA and Factory PO for this order and found **no discrepancies**. Everything else looked good."

        return {
            "summary": summary,
            "date_discrepancies": date_discrepancies,
            "main_discrepancies": pd.DataFrame(discrepancies, columns=["Field", "Line", "PO Value", "OA Value"])
        }

    except Exception as e:
        return {"summary": f"⚠️ An error occurred during comparison: {e}"}
