import streamlit as st
import pandas as pd
import datetime
import urllib.parse
import io
import re

# 1. Configuração da Página
st.set_page_config(
    page_title="Auditoria & Alertas de Ponto | Turin Transportes",
    page_icon="🚌",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("Painel de Auditoria e Alerta de Pendências de Ponto")
st.caption("Turin Transportes — Notificação Automática de Batidas Faltantes")

uploaded_file = st.file_uploader("Carregar relatório do Flit (.xlsx ou .csv)", type=["xlsx", "csv"])

# Função para extrair hora prevista da escala
def extrair_hora_prevista(escala_str):
    if not isinstance(escala_str, str):
        return None
    matches = re.findall(r'(\d{1,2}:\d{2})', escala_str)
    return matches[0] if matches else None

if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
        
        cols_obrigatorias = ['Colaborador', 'Matricula', 'Data', 'Hora']
        if not all(col in df.columns for col in cols_obrigatorias):
            st.error(f"O arquivo precisa conter: {', '.join(cols_obrigatorias)}")
        else:
            # 2. Tratamento e ordenação
            df['Data_dt'] = pd.to_datetime(df['Data'], format='%d/%m/%Y', errors='coerce')
            df_sorted = df.sort_values(by=['Matricula', 'Data_dt', 'Hora'])

            meta_cols = [c for c in ['Matricula', 'Colaborador', 'Empresa', 'Departamento', 'Cargo', 'Escala'] if c in df.columns]

            # 3. Agrupamento por colaborador e dia
            grouped = df_sorted.groupby(meta_cols + ['Data', 'Data_dt'])['Hora'].apply(list).reset_index()

            grouped['Qtd_Batidas'] = grouped['Hora'].apply(len)
            grouped['Entrada_Real'] = grouped['Hora'].apply(lambda x: x[0] if len(x) > 0 else "")
            grouped['Saida_Real'] = grouped['Hora'].apply(lambda x: x[-1] if len(x) > 1 else "")
            grouped['Hora_Prevista'] = grouped['Escala'].apply(extrair_hora_prevista)

            # Classificação do status
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

            max_batidas = grouped['Hora'].apply(len).max()
            for i in range(max_batidas):
                rotulo = f"Entrada {i//2 + 1}" if i % 2 == 0 else f"Saída {i//2 + 1}"
                grouped[f"Batida {i+1} ({rotulo})"] = grouped['Hora'].apply(lambda x: x[i] if len(x) > i else "")

            df_base = grouped.drop(columns=['Hora', 'Data_dt']).sort_values(by=['Colaborador', 'Data'])

            # 4. Filtros Laterais
            st.sidebar.header("🔍 Filtros")

            if 'Departamento' in df_base.columns:
                deptos = ['Todos'] + sorted(list(df_base['Departamento'].dropna().unique()))
                depto_sel = st.sidebar.selectbox("Departamento:", deptos)
                if depto_sel != 'Todos':
                    df_base = df_base[df_base['Departamento'] == depto_sel]

            busca = st.sidebar.text_input("Buscar Colaborador ou Matrícula:")
            if busca:
                df_base = df_base[
                    df_base['Colaborador'].astype(str).str.contains(busca, case=False, na=False) |
                    df_base['Matricula'].astype(str).str.contains(busca, case=False, na=False)
                ]

            # 5. Métricas Rápidas
            total = len(df_base)
            desvios = len(df_base[df_base['Status_Auditoria'].str.contains('🚨')])
            impares = len(df_base[df_base['Status_Auditoria'].str.contains('⚠️')])

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Dias Analisados", total)
            c2.metric("Marcações Conformes", total - desvios - impares)
            c3.metric("Desvios de Escala", desvios)
            c4.metric("Batidas Faltantes (Ímpares)", impares)

            st.markdown("---")

            # 6. Abas de Exibição
            aba1, aba2 = st.tabs(["📲 Notificações / Cobrança", "📋 Base Completa Pivotada"])

            with aba1:
                st.subheader("Gerador de Alertas de Marcações Pendentes")
                
                # Consolidar pendências ímpares por colaborador
                df_pendencias = df_base[df_base['Status_Auditoria'].str.contains('⚠️')].copy()
                
                if len(df_pendencias) == 0:
                    st.success("Nenhuma pendência de marcação faltante encontrada!")
                else:
                    cobranca_colab = df_pendencias.groupby(['Matricula', 'Colaborador'])['Data'].apply(list).reset_index()
                    cobranca_colab['Qtd_Dias_Pendentes'] = cobranca_colab['Data'].apply(len)
                    cobranca_colab['Datas_Pendentes'] = cobranca_colab['Data'].apply(lambda x: ", ".join(x))
                    
                    st.info(f"Encontrados **{len(cobranca_colab)} colaboradores** com batidas incompletas.")
                    
                    # Tabela com as mensagens prontas
                    for _, row in cobranca_colab.iterrows():
                        nome = row['Colaborador']
                        matr = row['Matricula']
                        datas = row['Datas_Pendentes']
                        qtd = row['Qtd_Dias_Pendentes']
                        
                        msg = (
                            f"Olá, {nome} (Matrícula: {matr})!\n\n"
                            f"Identificamos {qtd} dia(s) com pendência de marcação de ponto no sistema Flit:\n"
                            f"📅 Datas: {datas}\n\n"
                            f"Por favor, acesse o Flit Gestor / App ou envie o comprovante/justificativa para regularizarmos o fechamento de ponto."
                        )
                        
                        # Link de direcionamento para o WhatsApp Web
                        msg_encoded = urllib.parse.quote(msg)
                        link_wa = f"https://web.whatsapp.com/send?text={msg_encoded}"

                        with st.expander(f"👤 {nome} — Matrícula {matr} ({qtd} dia(s) pendente(s))"):
                            st.text_area("Texto da Notificação:", value=msg, height=140, key=f"txt_{matr}")
                            st.markdown(f"[📲 Clique para Enviar via WhatsApp Web]({link_wa})", unsafe_allow_html=True)

            with aba2:
                st.subheader("Base Completa com Todas as Batidas")
                st.dataframe(df_base, use_container_width=True, hide_index=True)

            # Exportação
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                if len(df_pendencias) > 0:
                    cobranca_colab.to_excel(writer, index=False, sheet_name='Resumo_Cobrança_Funcionarios')
                df_base.to_excel(writer, index=False, sheet_name='Base_Pivotada_Completa')

            st.download_button(
                label="📥 Baixar Planilha de Cobrança em Excel (.xlsx)",
                data=output.getvalue(),
                file_name="cobranca_batidas_faltantes_flit.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e:
        st.error(f"Erro ao processar o arquivo: {str(e)}")
