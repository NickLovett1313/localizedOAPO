import streamlit as st
from parse_pdf import parse_pdf
from compare import validate_po_number, compare_lines, format_report

st.title("Robust OA–PO Checker (PDF Only)")

po_file = st.file_uploader("Upload PO PDF", type="pdf")
oa_file = st.file_uploader("Upload OA PDF", type="pdf")

if po_file and oa_file:
    po_df = parse_pdf(po_file, is_po=True)
    oa_df = parse_pdf(oa_file, is_po=False)

    valid, po_number = validate_po_number(po_df, oa_df)
    if not valid:
        st.error(f"PO Number mismatch: {po_number}")
    else:
        discrepancies, weird_flags = compare_lines(po_df, oa_df)
        report = format_report(po_number, discrepancies, weird_flags)
        st.text(report)
