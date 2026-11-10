import streamlit as st
import pandas as pd
import datetime
import io
import re

# Configuração da Página
st.set_page_config(
    page_title="Painel de Auditoria de Ponto | Turin Transportes",
    page_icon="🚌",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilização CSS para Limpeza Visual e Tabelas Elegantes
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    h1 { color: #1e293b; font-size: 26px; font-weight: 700; }
    h3 { color: #334155; font-size: 18px; font-weight: 600; }
    </style>
""", unsafe_allow_html=True)

st.title("Painel de Auditoria de Ponto e Escalas")
st.caption("Turin Transportes — Validação de Escala Cadastrada x Praticada & Sugestões CLT (7h20)")

uploaded_file = st.file_uploader("Carregar arquivo de marcações do Flit (.xlsx ou .csv)", type=["xlsx", "csv"])

# Função para extrair hora prevista na escala cadastrada
def extrair_hora_prevista(escala_str):
    if not isinstance(escala_str, str):
        return None
    matches = re.findall(r'(\d{1,2}:\d{2})', escala_str)
    return matches[0] if matches else None

# Sugestão de escala padronizada CLT (7h20 de trabalho + 1h de almoço = 8h20 de amplitude)
def sugerir_escala_clt(hora_entrada):
    if not hora_entrada or not isinstance(hora_entrada, str):
        return "-"
    try:
        t_in = datetime.datetime.strptime(hora_entrada, '%H:%M')
        t_out = t_in + datetime.timedelta(hours=8, minutes=20)
        t_int_in = t_in + datetime.timedelta(hours=4)
        t_int_out = t_int_in + datetime.timedelta(hours=1)
        return f"{t_in.strftime('%H:%M')} às {t_out.strftime('%H:%M')} (Int. {t_int_in.strftime('%H:%M')}-{t_int_out.strftime('%H:%M')})"
    except:
        return "-"

if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
        
        cols_obrigatorias = ['Colaborador', 'Matricula', 'Data', 'Hora']
        if not all(col in df.columns for col in cols_obrigatorias):
            st.error(f"Arquivo inválido. Certifique-se de que a planilha contém: {', '.join(cols_obrigatorias)}")
        else:
            # 1. Tratamento e ordenação dos dados
            df['Data_dt'] = pd.to_datetime(df['Data'], format='%d/%m/%Y', errors='coerce')
            df_sorted = df.sort_values(by=['Matricula', 'Data_dt', 'Hora'])

            meta_cols = [c for c in ['Matricula', 'Colaborador', 'Empresa', 'Departamento', 'Cargo', 'Escala'] if c in df.columns]

            # 2. Agrupamento por colaborador e dia
            grouped = df_sorted.groupby(meta_cols + ['Data', 'Data_dt'])['Hora'].apply(list).reset_index()

            grouped['Qtd_Batidas'] = grouped['Hora'].apply(len)
            grouped['Entrada_Real'] = grouped['Hora'].apply(lambda x: x[0] if len(x) > 0 else "")
            grouped['Saida_Real'] = grouped['Hora'].apply(lambda x: x[-1] if len(x) > 1 else "")
            grouped['Hora_Prevista'] = grouped['Escala'].apply(extrair_hora_prevista)

            # 3. Auditoria de Escala
            def classificar_status(row):
                if row['Qtd_Batidas'] % 2 != 0:
                    return "⚠️ Batida Ímpar"
                
                prev = row['Hora_Prevista']
                real = row['Entrada_Real']
                
                if prev and real:
                    try:
                        t_prev = datetime.datetime.strptime(prev, '%H:%M')
                        t_real = datetime.datetime.strptime(real, '%H:%M')
                        diff = abs((t_real - t_prev).total_seconds()) / 60.0
                        if diff > 15:
                            return f"🚨 Desvio ({prev} prev. vs {real} real)"
                    except:
                        pass
                return "✅ Conforme"

            grouped['Status_Auditoria'] = grouped.apply(classificar_status, axis=1)
            grouped['Sugestao_Escala_7h20'] = grouped['Entrada_Real'].apply(sugerir_escala_clt)

            # Expansão horizontal secundária
            max_batidas = grouped['Hora'].apply(len).max()
            for i in range(max_batidas):
                grouped[f"Batida {i+1}"] = grouped['Hora'].apply(lambda x: x[i] if len(x) > i else "")

            df_base = grouped.drop(columns=['Hora', 'Data_dt']).sort_values(by=['Colaborador', 'Data'])

            # 4. Filtros Laterais
            st.sidebar.header("Filtros")

            if 'Departamento' in df_base.columns:
                deptos = ['Todos'] + sorted(list(df_base['Departamento'].dropna().unique()))
                depto_sel = st.sidebar.selectbox("Departamento", deptos)
                if depto_sel != 'Todos':
                    df_base = df_base[df_base['Departamento'] == depto_sel]

            status_opcoes = ['Todos os Registros', 'Apenas Inconsistências (Desvios e Ímpares)', 'Apenas Conformes']
            status_sel = st.sidebar.radio("Status de Auditoria", status_opcoes)

            if status_sel == 'Apenas Inconsistências (Desvios e Ímpares)':
                df_base = df_base[df_base['Status_Auditoria'].str.contains('⚠️|🚨')]
            elif status_sel == 'Apenas Conformes':
                df_base = df_base[df_base['Status_Auditoria'] == '✅ Conforme']

            busca = st.sidebar.text_input("Buscar Colaborador ou Matrícula")
            if busca:
                df_base = df_base[
                    df_base['Colaborador'].astype(str).str.contains(busca, case=False, na=False) |
                    df_base['Matricula'].astype(str).str.contains(busca, case=False, na=False)
                ]

            # 5. Métricas no Topo
            total = len(df_base)
            conformes = len(df_base[df_base['Status_Auditoria'] == '✅ Conforme'])
            desvios = len(df_base[df_base['Status_Auditoria'].str.contains('🚨')])
            impares = len(df_base[df_base['Status_Auditoria'].str.contains('⚠️')])

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Registros", total)
            c2.metric("Conformes", conformes)
            c3.metric("Desvios de Escala", desvios)
            c4.metric("Batidas Ímpares", impares)

            st.markdown("---")

            # 6. Exibição Enxuta e Formatada
            st.subheader("Auditoria de Escalas e Sugestão Contratual (7h20)")

            # Colunas limpas para apresentação principal
            cols_exibicao = {
                'Matricula': 'Matrícula',
                'Colaborador': 'Colaborador',
                'Data': 'Data',
                'Escala': 'Escala Cadastrada',
                'Entrada_Real': '1ª Entrada',
                'Saida_Real': 'Última Saída',
                'Status_Auditoria': 'Status',
                'Sugestao_Escala_7h20': 'Sugestão Escala 7h20'
            }
            
            cols_presentes = [c for c in cols_exibicao.keys() if c in df_base.columns]
            df_display = df_base[cols_presentes].rename(columns=cols_exibicao)

            st.dataframe(df_display, use_container_width=True, hide_index=True)

            # 7. Botão de Download Organizado
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_display.to_excel(writer, index=False, sheet_name='Auditoria_Executiva')
                df_base.to_excel(writer, index=False, sheet_name='Base_Pivotada_Completa')

            st.download_button(
                label="📥 Baixar Relatório Consolidado (.xlsx)",
                data=output.getvalue(),
                file_name="auditoria_escalas_turin.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e:
        st.error(f"Erro ao processar arquivo: {str(e)}")
