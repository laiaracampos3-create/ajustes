import streamlit as st
import pandas as pd
import datetime
import urllib.parse
import io
import re

# 1. Configuração da Página
st.set_page_config(
    page_title="Turin Transportes — Gestão de Ponto & Escalas",
    page_icon="🚌",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 2. Design System Personalizado (Identidade Turin - Verde #007106 + Grafite #0f172a)
st.markdown('''
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
        background-color: #f8fafc;
        color: #0f172a;
    }
    
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Header Principal com Verde Turin */
    .header-container {
        background: linear-gradient(135deg, #0f172a 0%, #004d04 100%);
        padding: 28px 36px;
        border-radius: 12px;
        color: white;
        margin-bottom: 24px;
        border-left: 6px solid #007106;
        box-shadow: 0 4px 12px rgba(0, 113, 6, 0.15);
    }
    .header-brand {
        font-size: 28px;
        font-weight: 800;
        letter-spacing: 2px;
        color: #ffffff;
        margin: 0;
        text-transform: uppercase;
    }
    .header-brand span {
        color: #22c55e;
    }
    .header-subtitle {
        font-size: 14px;
        color: #cbd5e1;
        margin-top: 6px;
        font-weight: 400;
    }
    
    /* Cards de Métricas */
    .metric-card {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-top: 4px solid #007106;
        border-radius: 10px;
        padding: 20px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.04);
    }
    .metric-label {
        font-size: 12px;
        font-weight: 600;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .metric-value {
        font-size: 26px;
        font-weight: 700;
        color: #0f172a;
        margin-top: 6px;
    }
    .metric-status-ok { color: #007106; }
    .metric-status-alert { color: #dc2626; }
    .metric-status-warning { color: #d97706; }
    
    /* Botões Customizados */
    .btn-whatsapp {
        display: block;
        width: 100%;
        background-color: #25D366;
        color: white !important;
        font-weight: 600;
        font-size: 15px;
        text-align: center;
        padding: 12px 20px;
        border-radius: 8px;
        text-decoration: none;
        box-shadow: 0 2px 4px rgba(37, 211, 102, 0.2);
    }
    .btn-whatsapp-sec {
        display: block;
        width: 100%;
        background-color: #007106;
        color: white !important;
        font-weight: 600;
        font-size: 15px;
        text-align: center;
        padding: 12px 20px;
        border-radius: 8px;
        text-decoration: none;
    }
    
    section[data-testid="stSidebar"] {
        background-color: #ffffff;
        border-right: 1px solid #e2e8f0;
    }
    </style>
''', unsafe_allow_html=True)

# Header Executivo Turin
st.markdown('''
    <div class="header-container">
        <div class="header-brand">TURIN <span>TRANSPORTES</span></div>
        <div class="header-subtitle">Sistema de Auditoria de Ponto, Jornadas de Motoristas & Gestão de Inconsistências</div>
    </div>
''', unsafe_allow_html=True)

# Upload Duplo (Planilha do Flit + Planilha de Contatos)
col_up1, col_up2 = st.columns(2)
with col_up1:
    uploaded_file = st.file_uploader("1. Relatório de marcações do Flit (.xlsx ou .csv)", type=["xlsx", "csv"])

with col_up2:
    uploaded_contacts = st.file_uploader("2. Lista de Contatos/WhatsApp (Opcional - Matrícula e Telefone)", type=["xlsx", "csv"])

# Leitura da Base de Contatos
df_contatos = None
if uploaded_contacts is not None:
    try:
        if uploaded_contacts.name.endswith('.csv'):
            df_contatos = pd.read_csv(uploaded_contacts)
        else:
            df_contatos = pd.read_excel(uploaded_contacts)
        
        col_matr = [c for c in df_contatos.columns if 'matr' in c.lower()]
        col_tel = [c for c in df_contatos.columns if 'tel' in c.lower() or 'whats' in c.lower() or 'cel' in c.lower() or 'fone' in c.lower()]
        
        if col_matr and col_tel:
            df_contatos = df_contatos[[col_matr[0], col_tel[0]]].rename(columns={col_matr[0]: 'Matricula', col_tel[0]: 'Telefone_Cadastrado'})
            df_contatos['Matricula'] = pd.to_numeric(df_contatos['Matricula'], errors='coerce')
            st.success(f"✅ Base com {len(df_contatos)} contatos cadastrados e vinculada!")
        else:
            st.warning("⚠️ A planilha de contatos precisa ter colunas 'Matrícula' e 'Telefone'.")
            df_contatos = None
    except Exception as e:
        st.error(f"Erro ao ler lista de contatos: {str(e)}")

# Funções Auxiliares
def extrair_hora_prevista(escala_str):
    if not isinstance(escala_str, str):
        return None
    matches = re.findall(r'(\d{1,2}:\d{2})', escala_str)
    return matches[0] if matches else None

def batidas_esperadas_por_escala(escala_str):
    if not isinstance(escala_str, str):
        return 4
    if re.search(r'adm|escritório|manutenção|08:00 ás 17:00|07:00 ás 17:00', escala_str, re.IGNORECASE):
        return 2
    return 4

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
    elif qtd == 2:
        e1 = row.get('Entrada_Real', '')
        s1 = row.get('Saida_Real', '')
        return f"{e1} às {s1} (Apenas 1 pegada / incompleto)"
    
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
            st.error(f"Arquivo inválido. A planilha precisa conter: {', '.join(cols_obrigatorias)}")
        else:
            # 1. Cruzamento com Telefones Cadastrados
            df['Matricula'] = pd.to_numeric(df['Matricula'], errors='coerce')
            if df_contatos is not None:
                df = df.merge(df_contatos, on='Matricula', how='left')

            # 2. Tratamento e Ordenação
            df['Data_dt'] = pd.to_datetime(df['Data'], format='%d/%m/%Y', errors='coerce')
            df_sorted = df.sort_values(by=['Matricula', 'Data_dt', 'Hora'])

            meta_cols = [c for c in ['Matricula', 'Colaborador', 'Empresa', 'Departamento', 'Cargo', 'Escala', 'Telefone_Cadastrado'] if c in df.columns]

            # 3. Pivotamento e Agrupamento
            grouped = df_sorted.groupby(meta_cols + ['Data', 'Data_dt'])['Hora'].apply(list).reset_index()

            grouped['Qtd_Batidas'] = grouped['Hora'].apply(len)
            grouped['Entrada_Real'] = grouped['Hora'].apply(lambda x: x[0] if len(x) > 0 else "")
            grouped['Saida_Real'] = grouped['Hora'].apply(lambda x: x[-1] if len(x) > 1 else "")
            grouped['Hora_Prevista'] = grouped['Escala'].apply(extrair_hora_prevista)
            grouped['Batidas_Esperadas'] = grouped['Escala'].apply(batidas_esperadas_por_escala)

            max_batidas = grouped['Hora'].apply(len).max()
            for i in range(max_batidas):
                rotulo = f"Entrada {i//2 + 1}" if i % 2 == 0 else f"Saída {i//2 + 1}"
                grouped[f"Batida {i+1} ({rotulo})"] = grouped['Hora'].apply(lambda x: x[i] if len(x) > i else "")

            # Classificação de Auditoria
            def classificar_status(row):
                qtd = row['Qtd_Batidas']
                esp = row['Batidas_Esperadas']
                
                if qtd % 2 != 0:
                    return f"⚠️ Ímpar ({qtd} batida(s) no dia)"
                
                if esp == 4 and qtd < 4:
                    return f"⚠️ Incompleto ({qtd} de 4 batidas registradas)"
                
                prev = row['Hora_Prevista']
                real = row['Entrada_Real']
                if prev and real:
                    try:
                        t_prev = datetime.datetime.strptime(prev, '%H:%M')
                        t_real = datetime.datetime.strptime(real, '%H:%M')
                        diff = abs((t_real - t_prev).total_seconds()) / 60.0
                        if diff > 15:
                            return f"🚨 Desvio de Entrada ({prev} prev. vs {real} real)"
                    except:
                        pass
                return "✅ Conforme"

            grouped['Status_Auditoria'] = grouped.apply(classificar_status, axis=1)
            grouped['Sugestao_Escala_7h20'] = grouped.apply(sugerir_escala_clt, axis=1)

            df_base = grouped.drop(columns=['Hora', 'Data_dt']).sort_values(by=['Colaborador', 'Data'])

            # 4. Sidebar (Filtros)
            st.sidebar.markdown("### ⚙️ Painel de Filtros")

            if 'Departamento' in df_base.columns:
                deptos = ['Todos os Departamentos'] + sorted(list(df_base['Departamento'].dropna().unique()))
                depto_sel = st.sidebar.selectbox("Filtrar Departamento:", deptos)
                if depto_sel != 'Todos os Departamentos':
                    df_base = df_base[df_base['Departamento'] == depto_sel]

            filtro_status = st.sidebar.radio(
                "Exibir na Tabela:", 
                ["Todos os Registros", "Apenas Batidas Pendentes / Incompletas", "Apenas ✅ Conformes"]
            )
            
            if filtro_status == "Apenas Batidas Pendentes / Incompletas":
                df_base = df_base[df_base['Status_Auditoria'].str.contains('⚠️|🚨')]
            elif filtro_status == "Apenas ✅ Conformes":
                df_base = df_base[df_base['Status_Auditoria'] == '✅ Conforme']

            busca = st.sidebar.text_input("🔍 Buscar Colaborador / Matrícula:")
            if busca:
                df_base = df_base[
                    df_base['Colaborador'].astype(str).str.contains(busca, case=False, na=False) |
                    df_base['Matricula'].astype(str).str.contains(busca, case=False, na=False)
                ]

            # 5. Métricas Executivas
            total = len(df_base)
            desvios = len(df_base[df_base['Status_Auditoria'].str.contains('🚨')])
            incompletos = len(df_base[df_base['Status_Auditoria'].str.contains('⚠️')])
            conformes = total - desvios - incompletos

            c1, c2, c3, c4 = st.columns(4)
            c1.markdown(f'<div class="metric-card"><div class="metric-label">Total de Jornadas</div><div class="metric-value">{total}</div></div>', unsafe_allow_html=True)
            c2.markdown(f'<div class="metric-card"><div class="metric-label">Jornadas Conformes</div><div class="metric-value metric-status-ok">{conformes}</div></div>', unsafe_allow_html=True)
            c3.markdown(f'<div class="metric-card"><div class="metric-label">Desvios de Escala</div><div class="metric-value metric-status-warning">{desvios}</div></div>', unsafe_allow_html=True)
            c4.markdown(f'<div class="metric-card"><div class="metric-label">Batidas Pendentes / Incompletas</div><div class="metric-value metric-status-alert">{incompletos}</div></div>', unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            # 6. Abas de Exibição
            aba1, aba2 = st.tabs(["💬 Central de Cobrança WhatsApp", "📊 Espelho Completo Pivotado"])

            with aba1:
                df_pendencias = df_base[df_base['Status_Auditoria'].str.contains('⚠️')].copy()
                
                if len(df_pendencias) == 0:
                    st.success("Nenhuma pendência de marcação faltante ou incompleta encontrada!")
                else:
                    cols_group = ['Matricula', 'Colaborador']
                    if 'Telefone_Cadastrado' in df_pendencias.columns:
                        cols_group.append('Telefone_Cadastrado')

                    cobranca_colab = df_pendencias.groupby(cols_group)['Data'].apply(list).reset_index()
                    cobranca_colab['Qtd_Dias_Pendentes'] = cobranca_colab['Data'].apply(len)
                    cobranca_colab['Datas_Pendentes'] = cobranca_colab['Data'].apply(lambda x: ", ".join(x))
                    
                    st.markdown(f"##### Encontrados **{len(cobranca_colab)} colaboradores** com batidas faltantes ou incompletas.")
                    
                    lista_opcoes = [f"{r['Matricula']} - {r['Colaborador']}" for _, r in cobranca_colab.iterrows()]
                    colab_selecionado = st.selectbox("Selecione o colaborador para notificar:", lista_opcoes)
                    
                    if colab_selecionado:
                        matr_sel = int(colab_selecionado.split(' - ')[0])
                        dados_colab = cobranca_colab[cobranca_colab['Matricula'] == matr_sel].iloc[0]
                        
                        nome = dados_colab['Colaborador']
                        datas = dados_colab['Datas_Pendentes']
                        qtd = dados_colab['Qtd_Dias_Pendentes']
                        
                        tel_padrao = str(dados_colab.get('Telefone_Cadastrado', ''))
                        if tel_padrao == 'nan' or tel_padrao == 'None':
                            tel_padrao = ''

                        col_tel, col_msg = st.columns([1, 2])
                        
                        with col_tel:
                            st.markdown("##### 📞 Contato do Funcionário")
                            num_tel = st.text_input("DDD + Número do WhatsApp:", value=tel_padrao, placeholder="Ex: 31988887777", key="tel_input")
                            num_limpo = re.sub(r'\D', '', num_tel)
                            if num_limpo and not num_limpo.startswith('55'):
                                num_limpo = '55' + num_limpo

                        msg = (
                            f"🚌 *Turin Transportes - Notificação de Ponto*\n\n"
                            f"Olá, *{nome}* (Matrícula: {matr_sel})!\n\n"
                            f"Identificamos *{qtd} dia(s)* com marcações incompletas/faltantes no sistema Flit:\n"
                            f"📅 *Datas com pendência:* {datas}\n\n"
                            f"Por favor, acesse o aplicativo do Flit Gestor para incluir as batidas ou envie os comprovantes para regularizarmos seu fechamento."
                        )

                        with col_msg:
                            st.markdown("##### 📝 Prévia da Mensagem")
                            st.text_area("Mensagem que será enviada:", value=msg, height=140)
                            
                            msg_encoded = urllib.parse.quote(msg)
                            
                            if num_limpo:
                                url_wa = f"https://api.whatsapp.com/send?phone={num_limpo}&text={msg_encoded}"
                                st.markdown(f'<a href="{url_wa}" target="_blank" class="btn-whatsapp">📲 Abrir Conversa no WhatsApp com {nome}</a>', unsafe_allow_html=True)
                            else:
                                url_wa_geral = f"https://web.whatsapp.com/send?text={msg_encoded}"
                                st.markdown(f'<a href="{url_wa_geral}" target="_blank" class="btn-whatsapp-sec">📲 Abrir WhatsApp Web (Selecionar Contato)</a>', unsafe_allow_html=True)

            with aba2:
                st.markdown("##### 📋 Tabela Geral de Ponto Pivotada")
                st.dataframe(df_base, use_container_width=True, hide_index=True)

            # Exportação
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                if len(df_pendencias) > 0:
                    cobranca_colab.to_excel(writer, index=False, sheet_name='Resumo_Cobrança_WhatsApp')
                df_base.to_excel(writer, index=False, sheet_name='Base_Pivotada_Completa')

            st.markdown("<br>", unsafe_allow_html=True)
            st.download_button(
                label="📥 Baixar Relatório Consolidado em Excel (.xlsx)",
                data=output.getvalue(),
                file_name="fechamento_ponto_turin.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e:
        st.error(f"Erro ao processar o arquivo: {str(e)}")
