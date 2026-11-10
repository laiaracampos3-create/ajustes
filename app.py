import streamlit as st
import pandas as pd
import datetime
import io
import re

st.set_page_config(
    page_title="Auditoria de Escalas e Ponto - Turin Transportes", 
    page_icon="🚌", 
    layout="wide"
)

st.title("🚌 Auditoria de Escalas Cadastradas vs. Batidas Reais")
st.markdown("Verifique se a escala do motorista condiz com o praticado e receba sugestões automáticas ajustadas para 7h20 diárias (44h semanais).")

uploaded_file = st.file_uploader("Arraste o relatório de marcações do Flit (.xlsx ou .csv)", type=["xlsx", "csv"])

# Função para extrair hora prevista na string da escala
def extrair_hora_prevista(escala_str):
    if not isinstance(escala_str, str):
        return None
    matches = re.findall(r'(\d{1,2}:\d{2})', escala_str)
    return matches[0] if matches else None

# Função para sugerir escala enquadrada em 7h20 trabalho + 1h intervalo (8h20 de amplitude)
def sugerir_escala_clt_7h20(hora_entrada_real):
    if not hora_entrada_real or not isinstance(hora_entrada_real, str):
        return "Sem batida de entrada"
    try:
        t_in = datetime.datetime.strptime(hora_entrada_real, '%H:%M')
        t_out = t_in + datetime.timedelta(hours=8, minutes=20)
        t_int_in = t_in + datetime.timedelta(hours=4)
        t_int_out = t_int_in + datetime.timedelta(hours=1)
        
        return f"{t_in.strftime('%H:%M')} às {t_out.strftime('%H:%M')} (Int: {t_int_in.strftime('%H:%M')}-{t_int_out.strftime('%H:%M')})"
    except:
        return "Horário Inválido"

if uploaded_file is not None:
    try:
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

            # Batidas de Entrada e Saída Reais
            grouped['Entrada_Real'] = grouped['Hora'].apply(lambda x: x[0] if len(x) > 0 else "")
            grouped['Saida_Real'] = grouped['Hora'].apply(lambda x: x[-1] if len(x) > 0 else "")
            grouped['Qtd_Batidas'] = grouped['Hora'].apply(len)

            # Extração de Hora Prevista na Escala Cadastrada
            grouped['Entrada_Prevista_Escala'] = grouped['Escala'].apply(extrair_hora_prevista)

            # 3. Regra de Auditoria de Escala (Diferença > 15 minutos)
            def auditar_escala(row):
                if row['Qtd_Batidas'] % 2 != 0:
                    return "⚠️ Batida Ímpar / Marcação Pendente"
                
                prev = row['Entrada_Prevista_Escala']
                real = row['Entrada_Real']
                
                if prev and real:
                    try:
                        t_prev = datetime.datetime.strptime(prev, '%H:%M')
                        t_real = datetime.datetime.strptime(real, '%H:%M')
                        diff = abs((t_real - t_prev).total_seconds()) / 60.0
                        if diff > 15:
                            return f"⚠️ Desvio de Escala ({prev} cadastrado vs {real} real)"
                    except:
                        pass
                return "✅ Escala OK"

            grouped['Status_Auditoria'] = grouped.apply(auditar_escala, axis=1)

            # 4. Sugestão da Escala CLT (7h20 diárias)
            grouped['Sugestao_Escala_7h20'] = grouped['Entrada_Real'].apply(sugerir_escala_clt_7h20)

            # Expansão horizontal de batidas
            max_batidas = grouped['Hora'].apply(len).max()
            for i in range(max_batidas):
                rotulo = f"Entrada {i//2 + 1}" if i % 2 == 0 else f"Saída {i//2 + 1}"
                grouped[f"Batida {i+1} ({rotulo})"] = grouped['Hora'].apply(lambda x: x[i] if len(x) > i else "")

            df_final = grouped.drop(columns=['Hora', 'Data_dt']).sort_values(by=['Colaborador', 'Data'])

            # 5. Filtros Laterais
            st.sidebar.header("🔍 Filtros")
            
            if 'Departamento' in df_final.columns:
                deptos = ['Todos'] + list(df_final['Departamento'].dropna().unique())
                depto_sel = st.sidebar.selectbox("Departamento:", deptos)
                if depto_sel != 'Todos':
                    df_final = df_final[df_final['Departamento'] == depto_sel]

            status_opcoes = ['Todos', 'Apenas Desvios de Escala e Batidas Ímpares', 'Apenas ✅ OK']
            status_sel = st.sidebar.radio("Filtrar por Status de Auditoria:", status_opcoes)
            if status_sel == 'Apenas Desvios de Escala e Batidas Ímpares':
                df_final = df_final[df_final['Status_Auditoria'].str.contains('⚠️')]
            elif status_sel == 'Apenas ✅ OK':
                df_final = df_final[df_final['Status_Auditoria'] == '✅ Escala OK']

            busca_nome = st.sidebar.text_input("Buscar por Nome ou Matrícula:")
            if busca_nome:
                df_final = df_final[
                    df_final['Colaborador'].astype(str).str.contains(busca_nome, case=False, na=False) |
                    df_final['Matricula'].astype(str).str.contains(busca_nome, case=False, na=False)
                ]

            # 6. Painel de KPIs
            total = len(df_final)
            desvios = len(df_final[df_final['Status_Auditoria'].str.contains('Desvio')])
            impares = len(df_final[df_final['Status_Auditoria'].str.contains('Ímpar')])
            ok = len(df_final[df_final['Status_Auditoria'] == '✅ Escala OK'])

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Registros Filtrados", total)
            c2.metric("Escalas Conformes (OK)", ok)
            c3.metric("Desvios de Escala", desvios)
            c4.metric("Batidas Ímpares", impares)

            st.markdown("---")

            # 7. Abas de Resultados
            aba1, aba2 = st.tabs(["🎯 Auditoria de Escala & Sugestão 7h20", "📋 Espelho Completo Pivotado"])

            with aba1:
                st.subheader("Análise de Compatibilidade e Sugestão de Horário CLT")
                cols_sugestao = [c for c in ['Matricula', 'Colaborador', 'Data', 'Escala', 'Entrada_Real', 'Saida_Real', 'Status_Auditoria', 'Sugestao_Escala_7h20'] if c in df_final.columns]
                st.dataframe(df_final[cols_sugestao], use_container_width=True)

            with aba2:
                st.subheader("Base Completa com Todas as Batidas Organizadas")
                st.dataframe(df_final, use_container_width=True)

            # 8. Exportação para Excel
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_final[cols_sugestao].to_excel(writer, index=False, sheet_name='Auditoria_e_Sugestao_Escalas')
                df_final.to_excel(writer, index=False, sheet_name='Base_Completa_Pivotada')

            st.download_button(
                label="📥 Baixar Relatório de Auditoria e Sugestões (.xlsx)",
                data=output.getvalue(),
                file_name="auditoria_escalas_sugestao_7h20.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e:
        st.error(f"Erro ao processar o arquivo: {str(e)}")
