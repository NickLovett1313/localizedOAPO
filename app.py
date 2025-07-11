import streamlit as st
from compare import load_files, validate_po_number, compare_lines, format_report

st.title("Rosemount OA–PO Checker")

po_file = st.file_uploader("Upload PO CSV", type="csv")
oa_file = st.file_uploader("Upload OA CSV", type="csv")

if po_file and oa_file:
    po_df, oa_df = load_files(po_file, oa_file)
    valid, po_number = validate_po_number(po_df, oa_df)

    if not valid:
        st.error(f"PO Number mismatch: {po_number}")
    else:
        discrepancies, weird_flags = compare_lines(po_df, oa_df)
        report = format_report(po_number, discrepancies, weird_flags)

        st.write("### Discrepancy Report")
        st.text(report)

        if st.button("Save Report"):
            with open(f"output/report_{po_number}.txt", "w") as f:
                f.write(report)
            st.success(f"Saved to output/report_{po_number}.txt")
