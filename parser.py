import streamlit as st
import pandas as pd
from parser import parse_po, parse_oa

st.title("OA vs PO PDF Extractor")

col1, col2 = st.columns(2)

with col1:
    st.header("OA PDF")
    oa_file = st.file_uploader("Upload OA PDF", type=['pdf'], key='oa')
    if oa_file:
        oa_df = parse_oa(oa_file)
        st.dataframe(oa_df)
        csv = oa_df.to_csv(index=False).encode('utf-8')
        st.download_button("Download OA CSV", csv, "oa_extracted.csv", "text/csv")

with col2:
    st.header("PO PDF")
    po_file = st.file_uploader("Upload PO PDF", type=['pdf'], key='po')
    if po_file:
        po_df = parse_po(po_file)
        st.dataframe(po_df)
        csv = po_df.to_csv(index=False).encode('utf-8')
        st.download_button("Download PO CSV", csv, "po_extracted.csv", "text/csv")
