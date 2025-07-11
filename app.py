import streamlit as st
from compare import load_pdf, validate_po_number, compare_lines, format_report

st.title("Rosemount OA–PO Checker")

po_file = st.file_uploader("Upload PO PDF", type="pdf")
oa_file = st.file_uploader("Upload OA PDF", type="pdf")

if po_file and oa_file:
    po_df = load_pdf(po_file, is_po=True)
    oa_df = load_pdf(oa_file, is_po=False)

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
