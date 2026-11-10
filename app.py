import streamlit as st
import pandas as pd
import io

st.set_page_config(
    page_title="Fechamento de Ponto & Escalas - Turin Transportes", 
    page_icon="🚌", 
    layout="wide"
)

st.title("🚌 Automação de Fechamento de Ponto e Escalas (Flit)")
st.markdown("Carregue o relatório bruto do Flit para pivotar batidas, conferir inconsistências e identificar a escala real praticada.")

uploaded_file = st.file_uploader("Arraste o relatório do Flit (.xlsx ou .csv)", type=["xlsx", "csv"])

if uploaded_file is not None:
    try:
        # Carregamento do arquivo
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
        
        cols_obrigatorias = ['Colaborador', 'Matricula', 'Data', 'Hora']
        if not all(col in df.columns for col in cols_obrigatorias):
            st.error(f"O arquivo precisa conter as colunas: {', '.join(cols_obrigatorias)}")
        else:
            # 1. Tratamento e ordenação
            df['Data_dt'] = pd.to_datetime(df['Data'], format='%d/%m/%Y', errors='coerce')
            df_sorted = df.sort_values(by=['Matricula', 'Data_dt', 'Hora'])

            meta_cols = [c for c in ['Matricula', 'Colaborador', 'Empresa', 'Departamento', 'Cargo', 'Escala'] if c in df.columns]

            # 2. Agrupamento por funcionário e data
            grouped = df_sorted.groupby(meta_cols + ['Data', 'Data_dt'])['Hora'].apply(list).reset_index()

            # 3. Regras de Inconsistência e Batidas
            grouped['Qtd_Batidas'] = grouped['Hora'].apply(len)
            grouped['Status_Batida'] = grouped['Qtd_Batidas'].apply(
                lambda x: '⚠️ ÍMPAR / MARCAÇÃO FALTANTE' if x % 2 != 0 else '✅ OK'
            )
            
            # Identifica Entrada Real (1ª batida) e Saída Real (Última batida)
            grouped['Primeira_Batida'] = grouped['Hora'].apply(lambda x: x[0] if len(x) > 0 else "")
            grouped['Ultima_Batida'] = grouped['Hora'].apply(lambda x: x[-1] if len(x) > 0 else "")

            # Classificação Automática do Turno Praticado pela 1ª Batida
            def classificar_turno(hora_str):
                if not hora_str:
                    return "Sem Marcação"
                try:
                    h = int(hora_str.split(':')[0])
                    if 4 <= h < 11:
                        return "🌅 Turno Manhã (Entrada 04h-10h)"
                    elif 11 <= h < 17:
                        return "☀️ Turno Tarde (Entrada 11h-16h)"
                    elif 17 <= h < 22:
                        return "🌙 Turno Noite (Entrada 17h-21h)"
                    else:
                        return "🌌 Turno Madrugada (Entrada 22h-03h)"
                except:
                    return "Indefinido"

            grouped['Turno_Identificado'] = grouped['Primeira_Batida'].apply(classificar_turno)

            # Expansão horizontal de batidas
            max_batidas = grouped['Hora'].apply(len).max()
            for i in range(max_batidas):
                rotulo = f"Entrada {i//2 + 1}" if i % 2 == 0 else f"Saída {i//2 + 1}"
                grouped[f"Batida {i+1} ({rotulo})"] = grouped['Hora'].apply(lambda x: x[i] if len(x) > i else "")

            df_final = grouped.drop(columns=['Hora', 'Data_dt']).sort_values(by=['Colaborador', 'Data'])

            # 4. Filtros Laterais
            st.sidebar.header("🔍 Filtros de Busca")

            if 'Departamento' in df_final.columns:
                deptos = ['Todos'] + list(df_final['Departamento'].dropna().unique())
                depto_sel = st.sidebar.selectbox("Filtrar por Departamento:", deptos)
                if depto_sel != 'Todos':
                    df_final = df_final[df_final['Departamento'] == depto_sel]

            if 'Escala' in df_final.columns:
                escalas = ['Todas'] + list(df_final['Escala'].dropna().unique())
                escala_sel = st.sidebar.selectbox("Filtrar por Escala Cadastrada:", escalas)
                if escala_sel != 'Todas':
                    df_final = df_final[df_final['Escala'] == escala_sel]

            busca_nome = st.sidebar.text_input("Buscar por Nome ou Matrícula:")
            if busca_nome:
                df_final = df_final[
                    df_final['Colaborador'].astype(str).str.contains(busca_nome, case=False, na=False) |
                    df_final['Matricula'].astype(str).str.contains(busca_nome, case=False, na=False)
                ]

            # 5. Painel de KPIs
            total_dias = len(df_final)
            total_erros = len(df_final[df_final['Status_Batida'].str.contains('⚠️')])
            total_ok = total_dias - total_erros
            pct_erros = (total_erros / total_dias * 100) if total_dias > 0 else 0

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Dias Analisados", total_dias)
            col2.metric("Batidas OK", total_ok)
            col3.metric("Batidas Ímpares", total_erros)
            col4.metric("% Inconsistências", f"{pct_erros:.1f}%")

            st.markdown("---")

            # 6. Abas de Trabalho
            aba1, aba2, aba3 = st.tabs([
                "⚠️ Pendências de Ponto", 
                "🚌 Identificação de Escalas / Turnos", 
                "📋 Base Completa Pivotada"
            ])

            df_erros = df_final[df_final['Status_Batida'].str.contains('⚠️')]

            with aba1:
                st.subheader(f"Batidas Ímpares / Incompletas ({len(df_erros)} ocorrências)")
                st.dataframe(df_erros, use_container_width=True)

            with aba2:
                st.subheader("Mapeamento de Escala Cadastrada vs. Turno Praticado")
                cols_escala = [c for c in ['Matricula', 'Colaborador', 'Departamento', 'Escala', 'Data', 'Primeira_Batida', 'Ultima_Batida', 'Turno_Identificado'] if c in df_final.columns]
                st.dataframe(df_final[cols_escala], use_container_width=True)

            with aba3:
                st.subheader("Espelho de Ponto Pivotado")
                st.dataframe(df_final, use_container_width=True)

            # 7. Gerador de Arquivo Excel
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_erros.to_excel(writer, index=False, sheet_name='Pendencias_Cobranca')
                df_final.to_excel(writer, index=False, sheet_name='Base_Completa_Pivotada')

            st.download_button(
                label="📥 Baixar Relatório Excel Otimizado (.xlsx)",
                data=output.getvalue(),
                file_name="fechamento_ponto_e_escalas_flit.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e:
        st.error(f"Erro ao processar o arquivo: {str(e)}")
    
