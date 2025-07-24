import streamlit as st
import pandas as pd
from parser import parse_po, parse_oa
from comparer import compare_oa_po

st.set_page_config(page_title="OA vs PO Extractor", layout="wide")
st.title("📄 OA vs PO PDF Extractor")

col1, col2 = st.columns(2)

# OA Upload
with col1:
    st.header("📑 Order Acknowledgement (OA)")
    oa_file = st.file_uploader("Upload OA PDF", type=['pdf'], key='oa')
    oa_df = None
    if oa_file:
        oa_df = parse_oa(oa_file)
        st.subheader("Parsed OA Data")
        st.dataframe(oa_df, use_container_width=True)
        csv = oa_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download OA CSV",
            data=csv,
            file_name="oa_extracted.csv",
            mime="text/csv"
        )

# PO Upload
with col2:
    st.header("📑 Purchase Order (PO)")
    po_file = st.file_uploader("Upload PO PDF", type=['pdf'], key='po')
    po_df = None
    if po_file:
        po_df = parse_po(po_file)
        st.subheader("Parsed PO Data")
        st.dataframe(po_df, use_container_width=True)
        csv = po_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download PO CSV",
            data=csv,
            file_name="po_extracted.csv",
            mime="text/csv"
        )

# ✅ Comparison Section
if po_file and oa_file and po_df is not None and oa_df is not None:
    st.markdown("---")
    st.header("✅ OA vs PO Comparison")

    if st.button("🔍 Ready to Compare"):
        try:
            disc_df, date_df = compare_oa_po(po_df, oa_df)

            # Summary
            if disc_df.empty and date_df.empty:
                st.success("I have reviewed the OA and Factory PO for this order and found no discrepancies. Everything else looked good.")
            else:
                st.warning("I have reviewed the OA and Factory PO for this order and found the following discrepancies. Everything else (that didn't appear in the list) looked good.")

            # Date Table
            if not date_df.empty:
                st.subheader("📅 Date Discrepancies Found:")
                st.dataframe(date_df, use_container_width=True)

            # Main Discrepancies
            if not disc_df.empty:
                st.subheader("📋 Main Discrepancies Found:")
                st.dataframe(disc_df, use_container_width=True)

                csv = disc_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Download Discrepancy Report CSV",
                    data=csv,
                    file_name="oa_po_discrepancy_report.csv",
                    mime="text/csv"
                )
        except Exception as e:
            st.error(f"⚠️ An error occurred during comparison: {e}")
