import streamlit as st
import pandas as pd
from parser import parse_po, parse_oa

st.set_page_config(page_title="OA vs PO Extractor", layout="wide")

st.title("📄 OA vs PO PDF Extractor")

col1, col2 = st.columns(2)

with col1:
    st.header("📑 Order Acknowledgement (OA)")
    oa_file = st.file_uploader("Upload OA PDF", type=['pdf'], key='oa')
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

with col2:
    st.header("📑 Purchase Order (PO)")
    po_file = st.file_uploader("Upload PO PDF", type=['pdf'], key='po')
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
