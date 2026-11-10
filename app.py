import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Tratamento de Ponto - Flit", layout="wide")
st.title("📊 Automação de Fechamento de Ponto")

uploaded_file = st.file_uploader("Arraste o relatório do Flit (XLSX ou CSV)", type=["xlsx", "csv"])

if uploaded_file is not None:
    # Leitura do arquivo
    if uploaded_file.name.endswith('.csv'):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)
    
    st.subheader("Pré-visualização dos Dados")
    st.dataframe(df.head())

    # Processamento de pendências
    # Ajuste os nomes das colunas conforme o relatório oficial do Flit
    cols_batidas = [c for c in df.columns if 'Entrada' in c or 'Saida' in c or 'Batida' in c]
    
    if cols_batidas:
        # Identifica linhas com valores nulos nas batidas
        pendencias = df[df[cols_batidas].isna().any(axis=1)].copy()
        pendencias['Status_Fechamento'] = 'Inconsistência / Marcação Pendente'
        
        st.error(f"Foram encontradas {len(pendencias)} linhas com pendências de marcação.")
        st.dataframe(pendencias)
        
        # Download do resultado limpo
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            pendencias.to_excel(writer, index=False, sheet_name='Pendencias')
        
        st.download_button(
            label="📥 Baixar Relatório de Pendências (.xlsx)",
            data=output.getvalue(),
            file_name="pendencias_fechamento_flit.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.info("Nenhuma coluna padrão de batida encontrada para validar automaticamente.")
