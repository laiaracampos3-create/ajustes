import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Tratamento de Ponto - Turin Transportes", layout="wide")
st.title("📊 Automação de Fechamento de Ponto - Flit")

uploaded_file = st.file_uploader("Arraste o relatório de marcações do Flit (XLSX ou CSV)", type=["xlsx", "csv"])

if uploaded_file is not None:
    try:
        # Carregamento dos dados
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
        
        st.subheader("Pré-visualização dos Dados Brutos")
        st.dataframe(df.head())

        # Validação das colunas mínimas do Flit
        colunas_obrigatorias = ['Colaborador', 'Matricula', 'Data', 'Hora']
        if not all(col in df.columns for col in colunas_obrigatorias):
            st.error(f"O arquivo enviado precisa conter as colunas: {', '.join(colunas_obrigatorias)}")
        else:
            # Ordenação cronológica dos registros
            df_sorted = df.sort_values(by=['Matricula', 'Data', 'Hora'])
            
            # Identificação de colunas adicionais para compor o relatório
            meta_cols = [c for c in ['Matricula', 'Colaborador', 'Empresa', 'Departamento', 'Cargo'] if c in df.columns]
            
            # Agrupamento por funcionário e data
            grouped = df_sorted.groupby(meta_cols + ['Data'])['Hora'].apply(list).reset_index()
            
            # Identifica a quantidade de marcados e flag de batida ímpar (inconsistência)
            grouped['Qtd_Marcacoes'] = grouped['Hora'].apply(len)
            grouped['Status'] = grouped['Qtd_Marcacoes'].apply(
                lambda x: '⚠️ ÍMPAR / MARCAÇÃO FALTANTE' if x % 2 != 0 else 'OK'
            )
            
            # Expande a lista de batidas em colunas (Entrada 1, Saída 1, Entrada 2, Saída 2...)
            max_batidas = grouped['Hora'].apply(len).max()
            for i in range(max_batidas):
                rotulo = f"Entrada {i//2 + 1}" if i % 2 == 0 else f"Saída {i//2 + 1}"
                grouped[f"Batida {i+1} ({rotulo})"] = grouped['Hora'].apply(lambda x: x[i] if len(x) > i else "")

            # Remove a coluna original com lista de horas
            relatorio_final = grouped.drop(columns=['Hora'])

            # Filtros no Streamlit
            st.markdown("---")
            st.subheader("📌 Resumo das Inconsistências")
            
            apenas_pendencias = st.checkbox("Mostrar apenas marcações inconsistentes (batidas ímpares)", value=True)
            
            if apenas_pendencias:
                df_exibicao = relatorio_final[relatorio_final['Status'].str.contains('⚠️')]
            else:
                df_exibicao = relatorio_final

            st.warning(f"Total de inconsistências encontradas: {len(relatorio_final[relatorio_final['Status'].str.contains('⚠️')])} ocorrências.")
            st.dataframe(df_exibicao, use_container_width=True)

            # Exportação para Excel
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                relatorio_final.to_excel(writer, index=False, sheet_name='Ponto_Processado')
            
            st.download_button(
                label="📥 Baixar Planilha Consolidada (.xlsx)",
                data=output.getvalue(),
                file_name="fechamento_ponto_flit_processado.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e:
        st.error(f"Erro ao processar o arquivo: {str(e)}")
