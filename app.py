import streamlit as st
import pandas as pd
import io

st.set_page_config(
    page_title="Fechamento de Ponto - Turin Transportes", 
    page_icon="🚌", 
    layout="wide"
)

st.title("🚌 Automação de Fechamento de Ponto (Flit)")
st.markdown("Carregue o relatório bruto de marcações do Flit para gerar o espelho pivotado e identificar inconsistências em segundos.")

uploaded_file = st.file_uploader("Arraste o relatório do Flit (.xlsx ou .csv)", type=["xlsx", "csv"])

if uploaded_file is not None:
    try:
        # Carregamento do arquivo
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
        
        # Validação de colunas essenciais
        cols_obrigatorias = ['Colaborador', 'Matricula', 'Data', 'Hora']
        if not all(col in df.columns for col in cols_obrigatorias):
            st.error(f"O arquivo precisa conter as seguintes colunas: {', '.join(cols_obrigatorias)}")
        else:
            # 1. Tratamento e ordenação cronológica
            df['Data_dt'] = pd.to_datetime(df['Data'], format='%d/%m/%Y', errors='coerce')
            df_sorted = df.sort_values(by=['Matricula', 'Data_dt', 'Hora'])

            # Identificação de colunas de metadados
            meta_cols = [c for c in ['Matricula', 'Colaborador', 'Empresa', 'Departamento', 'Cargo'] if c in df.columns]

            # 2. Agrupamento e pivotamento por funcionário e data
            grouped = df_sorted.groupby(meta_cols + ['Data', 'Data_dt'])['Hora'].apply(list).reset_index()

            # 3. Regras de inconsistência
            grouped['Qtd_Batidas'] = grouped['Hora'].apply(len)
            grouped['Status'] = grouped['Qtd_Batidas'].apply(
                lambda x: '⚠️ ÍMPAR / MARCAÇÃO FALTANTE' if x % 2 != 0 else '✅ OK'
            )

            # Expansão para colunas horizontais (Entrada 1, Saída 1, Entrada 2, Saída 2...)
            max_batidas = grouped['Hora'].apply(len).max()
            for i in range(max_batidas):
                rotulo = f"Entrada {i//2 + 1}" if i % 2 == 0 else f"Saída {i//2 + 1}"
                grouped[f"Batida {i+1} ({rotulo})"] = grouped['Hora'].apply(lambda x: x[i] if len(x) > i else "")

            # Limpeza final e ordenação
            df_final = grouped.drop(columns=['Hora', 'Data_dt']).sort_values(by=['Colaborador', 'Data'])

            # 4. Menu Lateral - Filtros
            st.sidebar.header("🔍 Filtros de Busca")

            # Filtro por Empresa
            if 'Empresa' in df_final.columns:
                empresas = ['Todas'] + list(df_final['Empresa'].dropna().unique())
                empresa_sel = st.sidebar.selectbox("Filtrar por Empresa:", empresas)
                if empresa_sel != 'Todas':
                    df_final = df_final[df_final['Empresa'] == empresa_sel]

            # Filtro por Departamento
            if 'Departamento' in df_final.columns:
                deptos = ['Todos'] + list(df_final['Departamento'].dropna().unique())
                depto_sel = st.sidebar.selectbox("Filtrar por Departamento:", deptos)
                if depto_sel != 'Todos':
                    df_final = df_final[df_final['Departamento'] == depto_sel]

            # Busca por Nome do Colaborador ou Matrícula
            busca_nome = st.sidebar.text_input("Buscar por Nome ou Matrícula:")
            if busca_nome:
                df_final = df_final[
                    df_final['Colaborador'].astype(str).str.contains(busca_nome, case=False, na=False) |
                    df_final['Matricula'].astype(str).str.contains(busca_nome, case=False, na=False)
                ]

            # 5. Painel de Indicadores (KPIs)
            total_dias = len(df_final)
            total_erros = len(df_final[df_final['Status'].str.contains('⚠️')])
            total_ok = total_dias - total_erros
            pct_erros = (total_erros / total_dias * 100) if total_dias > 0 else 0

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Registros Filtrados", total_dias)
            col2.metric("Marcações OK", total_ok)
            col3.metric("Marcações Ímpares", total_erros)
            col4.metric("% Inconsistências", f"{pct_erros:.1f}%")

            st.markdown("---")

            # 6. Abas de Exibição
            aba1, aba2 = st.tabs(["⚠️ Relatório de Pendências (Cobrança)", "📋 Base Completa Pivotada"])

            df_erros = df_final[df_final['Status'].str.contains('⚠️')]

            with aba1:
                st.subheader(f"Inconsistências Encontradas ({len(df_erros)} registros)")
                st.dataframe(df_erros, use_container_width=True)

            with aba2:
                st.subheader("Espelho de Ponto Pivotado")
                st.dataframe(df_final, use_container_width=True)

            # 7. Gerador de Arquivo Excel para Download
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_erros.to_excel(writer, index=False, sheet_name='Pendencias_Cobranca')
                df_final.to_excel(writer, index=False, sheet_name='Base_Completa_Pivotada')

            st.download_button(
                label="📥 Baixar Relatório Excel (.xlsx)",
                data=output.getvalue(),
                file_name="fechamento_ponto_flit_processado.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e:
        st.error(f"Erro ao processar o arquivo: {str(e)}")
