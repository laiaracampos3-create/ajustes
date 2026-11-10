import streamlit as st
import pandas as pd
import datetime
import urllib.parse
import requests
import io
import re

# 1. Configuração da Página
st.set_page_config(
    page_title="Auditoria & Alertas de Ponto | Turin Transportes",
    page_icon="🚌",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilização CSS Executiva
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    h1 { color: #1e293b; font-size: 26px; font-weight: 700; }
    h3 { color: #334155; font-size: 18px; font-weight: 600; }
    </style>
""", unsafe_allow_html=True)

st.title("Painel de Auditoria e Cobrança de Ponto (WhatsApp)")
st.caption("Turin Transportes — Notificação de Marcações Faltantes & Gestão de Escalas")

uploaded_file = st.file_uploader("Carregar relatório de marcações do Flit (.xlsx ou .csv)", type=["xlsx", "csv"])

# Função para extrair hora cadastrada no nome da escala
def extrair_hora_prevista(escala_str):
    if not isinstance(escala_str, str):
        return None
    matches = re.findall(r'(\d{1,2}:\d{2})', escala_str)
    return matches[0] if matches else None

# Função de Sugestão de Jornada (Dupla Pegada ou 7h20)
def sugerir_escala_clt(row):
    qtd = row.get('Qtd_Batidas', 0)
    if qtd == 4:
        e1 = row.get('Entrada_Real', '')
        s1 = row.get('Batida 2 (Saída 1)', '')
        e2 = row.get('Batida 3 (Entrada 2)', '')
        s2 = row.get('Saida_Real', '')
        if e1 and s1 and e2 and s2:
            try:
                t1 = (datetime.datetime.strptime(s1, '%H:%M') - datetime.datetime.strptime(e1, '%H:%M')).total_seconds() / 3600.0
                t2 = (datetime.datetime.strptime(s2, '%H:%M') - datetime.datetime.strptime(e2, '%H:%M')).total_seconds() / 3600.0
                total_h = t1 + t2
                h_int = int(total_h)
                m_int = int(round((total_h - h_int) * 60))
                return f"{e1}-{s1} | {e2}-{s2} ({h_int}h{m_int:02d}m trab.)"
            except:
                pass
    e1 = row.get('Entrada_Real', '')
    if e1:
        try:
            t_in = datetime.datetime.strptime(e1, '%H:%M')
            t_out = t_in + datetime.timedelta(hours=8, minutes=20)
            return f"{e1} às {t_out.strftime('%H:%M')} (7h20 + 1h int)"
        except:
            return "-"
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
            # 2. Tratamento e Ordenação
            df['Data_dt'] = pd.to_datetime(df['Data'], format='%d/%m/%Y', errors='coerce')
            df_sorted = df.sort_values(by=['Matricula', 'Data_dt', 'Hora'])

            meta_cols = [c for c in ['Matricula', 'Colaborador', 'Empresa', 'Departamento', 'Cargo', 'Escala'] if c in df.columns]

            # 3. Pivotamento e Agrupamento
            grouped = df_sorted.groupby(meta_cols + ['Data', 'Data_dt'])['Hora'].apply(list).reset_index()

            grouped['Qtd_Batidas'] = grouped['Hora'].apply(len)
            grouped['Entrada_Real'] = grouped['Hora'].apply(lambda x: x[0] if len(x) > 0 else "")
            grouped['Saida_Real'] = grouped['Hora'].apply(lambda x: x[-1] if len(x) > 1 else "")
            grouped['Hora_Prevista'] = grouped['Escala'].apply(extrair_hora_prevista)

            max_batidas = grouped['Hora'].apply(len).max()
            for i in range(max_batidas):
                rotulo = f"Entrada {i//2 + 1}" if i % 2 == 0 else f"Saída {i//2 + 1}"
                grouped[f"Batida {i+1} ({rotulo})"] = grouped['Hora'].apply(lambda x: x[i] if len(x) > i else "")

            # Classificação de Auditoria
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
            grouped['Sugestao_Escala_7h20'] = grouped.apply(sugerir_escala_clt, axis=1)

            df_base = grouped.drop(columns=['Hora', 'Data_dt']).sort_values(by=['Colaborador', 'Data'])

            # 4. Filtros Laterais
            st.sidebar.header("🔍 Filtros de Busca")

            if 'Departamento' in df_base.columns:
                deptos = ['Todos'] + sorted(list(df_base['Departamento'].dropna().unique()))
                depto_sel = st.sidebar.selectbox("Filtrar por Departamento:", deptos)
                if depto_sel != 'Todos':
                    df_base = df_base[df_base['Departamento'] == depto_sel]

            busca = st.sidebar.text_input("Buscar Colaborador ou Matrícula:")
            if busca:
                df_base = df_base[
                    df_base['Colaborador'].astype(str).str.contains(busca, case=False, na=False) |
                    df_base['Matricula'].astype(str).str.contains(busca, case=False, na=False)
                ]

            # Configurações de Envio Automático por API de WhatsApp (Opcional)
            st.sidebar.markdown("---")
            st.sidebar.header("🤖 Envio Automático via API")
            api_url = st.sidebar.text_input("URL da API (ex: Z-API / Evolution)", placeholder="https://api.z-api.io/...")
            api_token = st.sidebar.text_input("Token / API Key:", type="password")

            # 5. Métricas no Topo
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
            aba1, aba2 = st.tabs(["📲 Cobrança via WhatsApp", "📋 Base Completa Pivotada"])

            with aba1:
                st.subheader("Gerador de Alertas de Ponto por WhatsApp")
                
                df_pendencias = df_base[df_base['Status_Auditoria'].str.contains('⚠️')].copy()
                
                if len(df_pendencias) == 0:
                    st.success("Nenhuma pendência de marcação faltante encontrada!")
                else:
                    cobranca_colab = df_pendencias.groupby(['Matricula', 'Colaborador'])['Data'].apply(list).reset_index()
                    cobranca_colab['Qtd_Dias_Pendentes'] = cobranca_colab['Data'].apply(len)
                    cobranca_colab['Datas_Pendentes'] = cobranca_colab['Data'].apply(lambda x: ", ".join(x))
                    
                    st.info(f"Encontrados **{len(cobranca_colab)} colaboradores** com marcações incompletas no mês.")
                    
                    # Botão para envio automático em lote via API (se API configurada)
                    if api_url and api_token:
                        if st.button("🚀 Disparar Mensagens Automáticas em Lote para Todos"):
                            sucesso_count = 0
                            for _, r in cobranca_colab.iterrows():
                                msg = (
                                    f"🚌 *Turin Transportes - Notificação de Ponto*\n\n"
                                    f"Olá, *{r['Colaborador']}* (Matrícula: {r['Matricula']})!\n\n"
                                    f"Identificamos que constam pendências de marcação no Flit nos seguintes dias:\n"
                                    f"📅 *{r['Datas_Pendentes']}*\n\n"
                                    f"Por favor, solicite o ajuste no aplicativo do Flit Gestor para regularizar seu fechamento."
                                )
                                # Chamada de envio via API
                                try:
                                    res = requests.post(
                                        api_url, 
                                        json={"text": msg}, 
                                        headers={"Client-Token": api_token, "Content-Type": "application/json"}
                                    )
                                    if res.status_code == 200:
                                        sucesso_count += 1
                                except:
                                    pass
                            st.success(f"Disparo concluído! {sucesso_count} mensagens enviadas.")
                            st.markdown("---")

                    # Lista de Envio Individual / Manual por WhatsApp Web
                    for _, row in cobranca_colab.iterrows():
                        nome = row['Colaborador']
                        matr = row['Matricula']
                        datas = row['Datas_Pendentes']
                        qtd = row['Qtd_Dias_Pendentes']
                        
                        msg = (
                            f"🚌 *Turin Transportes - Notificação de Ponto*\n\n"
                            f"Olá, *{nome}* (Matrícula: {matr})!\n\n"
                            f"Identificamos {qtd} dia(s) com pendência de marcação de ponto no Flit:\n"
                            f"📅 *Datas:* {datas}\n\n"
                            f"Por favor, acesse o aplicativo do Flit Gestor ou envie a justificativa para fechamento da folha."
                        )
                        
                        msg_encoded = urllib.parse.quote(msg)
                        link_wa = f"https://web.whatsapp.com/send?text={msg_encoded}"

                        with st.expander(f"👤 {nome} — Matrícula {matr} ({qtd} dia(s) pendente(s))"):
                            st.text_area("Texto da Mensagem:", value=msg, height=130, key=f"txt_{matr}")
                            st.markdown(f"[📲 Abrir no WhatsApp Web para Enviar]({link_wa})", unsafe_allow_html=True)

            with aba2:
                st.subheader("Base Completa com Todas as Batidas")
                st.dataframe(df_base, use_container_width=True, hide_index=True)

            # 7. Exportação para Excel
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                if len(df_pendencias) > 0:
                    cobranca_colab.to_excel(writer, index=False, sheet_name='Resumo_Cobrança_WhatsApp')
                df_base.to_excel(writer, index=False, sheet_name='Base_Pivotada_Completa')

            st.download_button(
                label="📥 Baixar Relatório de Cobrança em Excel (.xlsx)",
                data=output.getvalue(),
                file_name="cobranca_ponto_whatsapp_turin.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e:
        st.error(f"Erro ao processar arquivo: {str(e)}")
