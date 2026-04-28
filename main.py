"""
Dashboard de Acompanhamento Pedagógico — Check-in Mensal
QualiSaúde / UFRN

Instalação:
    pip install streamlit pandas gspread google-auth plotly

Como rodar:
    streamlit run main.py

Para automação (atualização automática):
    O dashboard lê os dados direto do Google Sheets a cada 5 minutos.
    Não é necessário exportar CSV manualmente.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import json
import os

# ===============================================================
# CONFIGURAÇÃO — edite apenas este bloco
# ===============================================================

# ID da sua planilha Google Sheets
# (encontre na URL: docs.google.com/spreadsheets/d/SEU_ID/edit)

# Nomes das abas
ABA_DASHBOARD = "Dashboard"
ABA_ALUNOS    = "Alunos"

# Caminho para o arquivo de credenciais do Google 
CREDENCIAIS_PATH = "credenciais_google.json"

# Configurações de email — conta que ENVIA os alertas
from dotenv import load_dotenv
load_dotenv()

EMAIL_REMETENTE = os.getenv("EMAIL_REMETENTE")
EMAIL_SENHA     = os.getenv("EMAIL_SENHA")
SMTP_HOST       = os.getenv("SMTP_HOST")
SMTP_PORT       = int(os.getenv("SMTP_PORT", 587))
SPREADSHEET_ID  = os.getenv("SPREADSHEET_ID")
CREDENCIAIS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH")

# Limiares de alerta
DIAS_REUNIAO_ATENCAO = 21
DIAS_REUNIAO_CRITICO = 30
DIAS_CORRECAO_ALERTA = 14

# ===============================================================
# CONEXÃO COM GOOGLE SHEETS
# ===============================================================

def conectar_sheets():
    """Conecta ao Google Sheets usando conta de serviço."""
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    try:
        creds = Credentials.from_service_account_file(CREDENCIAIS_PATH, scopes=scopes)
        client = gspread.authorize(creds)
        return client.open_by_key(SPREADSHEET_ID)
    except FileNotFoundError:
        st.error(
            "❌ Arquivo de credenciais não encontrado.\n\n"
            "Siga as instruções no final do código para gerar o arquivo `credenciais_google.json`."
        )
        st.stop()
    except Exception as e:
        st.error(f"❌ Erro ao conectar ao Google Sheets: {e}")
        st.stop()

@st.cache_data(ttl=300)  # atualiza a cada 5 minutos automaticamente
def carregar_dados():
    """Carrega e processa os dados do Google Sheets."""
    ss = conectar_sheets()

    # ── Dashboard (dados processados pelo Apps Script) ──
    aba_dash  = ss.worksheet(ABA_DASHBOARD)
    raw_dash  = aba_dash.get_all_values()

    # A linha 0 é o resumo "Atualizado em...", linha 1 é o cabeçalho
    cabecalho = raw_dash[1]
    linhas    = raw_dash[2:]
    df = pd.DataFrame(linhas, columns=cabecalho)
    df = df[df['Aluno'].str.strip() != '']  # remove linhas vazias

    # ── Alunos (para cruzar turma e email do orientador) ──
    aba_alunos = ss.worksheet(ABA_ALUNOS)
    raw_alunos = aba_alunos.get_all_records()
    df_alunos  = pd.DataFrame(raw_alunos)

    # Limpa espaços nos emails e nomes
    for col in df_alunos.columns:
        if df_alunos[col].dtype == object:
            df_alunos[col] = df_alunos[col].str.strip()

    return df, df_alunos

def processar(df, df_alunos):
    """Limpa tipos, cruza turma e calcula campos derivados."""

    # Normaliza nome do aluno para cruzamento (maiúsculas, sem espaços extras)
    df['_nome_key'] = df['Aluno'].str.upper().str.strip()
    df_alunos['_nome_key'] = df_alunos['Nome do Aluno'].str.upper().str.strip()

    # Cruza turma e email do orientador
    mapa = df_alunos.set_index('_nome_key')[['turma', 'Email do Orientador']].to_dict('index')

    df['Turma'] = df['_nome_key'].map(lambda n: mapa.get(n, {}).get('turma', '—'))
    df['Email Orientador'] = df['_nome_key'].map(
        lambda n: mapa.get(n, {}).get('Email do Orientador', '')
    )

    # Converte numéricos
    df['Dias sem reunião'] = pd.to_numeric(df['Dias sem reunião'], errors='coerce')
    df['Dias aguardando']  = pd.to_numeric(df['Dias aguardando'],  errors='coerce')
    df['Qtd trabalhos']    = pd.to_numeric(df['Qtd trabalhos'],    errors='coerce')

    # Formata turma como inteiro (remove .0)
    df['Turma'] = pd.to_numeric(df['Turma'], errors='coerce').fillna(0).astype(int)
    df['Turma'] = df['Turma'].apply(lambda t: f"Turma {t}" if t > 0 else "—")

    # Abreviação do nome orientador (2 primeiros nomes); discentes usam nome completo
    df['Orientador curto'] = df['Orientador'].str.title().str.split().str[:2].str.join(' ')

    # Corrige "dias sem reunião" para discentes que não preencheram (NaN / valores absurdos)
    # Se o valor for NaN ou maior que 3650 (>10 anos — claramente inválido), zera para NaN
    df.loc[df['Dias sem reunião'] > 3650, 'Dias sem reunião'] = pd.NA

    return df.drop(columns=['_nome_key'])

# ===============================================================
# ENVIO DE EMAIL PARA ORIENTADORES
# ===============================================================

def enviar_email_orientador(email_orientador, nome_orientador, nome_aluno, dias):
    """Envia alerta ao orientador cujo aluno está há mais de 30 dias sem reunião."""
    if not EMAIL_SENHA:
        return False, "Senha de email não configurada."
    if not email_orientador or '@' not in email_orientador:
        return False, "Email do orientador inválido."

    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"[QualiSaúde] Alerta de acompanhamento — {nome_aluno}"
    msg['From']    = EMAIL_REMETENTE
    msg['To']      = email_orientador.strip()

    corpo_txt = (
        f"Olá, professor(a) {nome_orientador}.\n\n"
        f"Notamos que já fazem mais de 30 dias desde a última reunião com o(a) aluno(a) "
        f"orientado(a) {nome_aluno} ({dias} dias sem registro de reunião).\n\n"
        f"Pedimos que verifique e, se possível, regularize o acompanhamento.\n\n"
        f"Obrigado!\n\nEquipe QualiSaúde / UFRN"
    )

    corpo_html = f"""
    <html><body style="font-family:Arial,sans-serif;color:#333;max-width:600px;margin:0 auto">
      <div style="background:#1a3a6b;color:white;padding:20px;border-radius:8px 8px 0 0">
        <h2 style="margin:0">⚠ Alerta de Acompanhamento</h2>
        <p style="margin:6px 0 0;opacity:.8">Programa de Graduação | QualiSaúde / UFRN</p>
      </div>
      <div style="background:#f8f9fa;padding:24px;border:1px solid #dadce0">
        <p>Olá, professor(a) <strong>{nome_orientador}</strong>.</p>
        <p>Notamos que já fazem <strong style="color:#dc2626">{dias} dias</strong> desde
        a última reunião com o(a) aluno(a) orientado(a)
        <strong>{nome_aluno}</strong>.</p>
        <div style="background:#fff3cd;border-left:4px solid #ffc107;padding:12px;margin:16px 0">
          Pedimos que verifique e, se possível, regularize o acompanhamento.
        </div>
        <p>Obrigado!</p>
      </div>
      <div style="font-size:12px;color:#888;padding:12px;background:#f1f3f4;
                  border:1px solid #dadce0;border-top:none;border-radius:0 0 8px 8px">
        Email automático — Programa de Graduação | QualiSaúde / UFRN
      </div>
    </body></html>"""

    msg.attach(MIMEText(corpo_txt, 'plain', 'utf-8'))
    msg.attach(MIMEText(corpo_html, 'html',  'utf-8'))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
            smtp.starttls()
            smtp.login(EMAIL_REMETENTE, EMAIL_SENHA)
            smtp.sendmail(EMAIL_REMETENTE, email_orientador.strip(), msg.as_string())
        return True, "OK"
    except Exception as e:
        return False, str(e)

def disparar_alertas_orientadores(df):
    """Verifica discentes críticos e envia email aos orientadores."""
    criticos = df[df['Dias sem reunião'].notna() & (df['Dias sem reunião'] >= DIAS_REUNIAO_CRITICO)].copy()
    resultados = []
    for _, row in criticos.iterrows():
        ok, msg = enviar_email_orientador(
            email_orientador  = row.get('Email Orientador', ''),
            nome_orientador   = row.get('Orientador curto', row.get('Orientador', '')),
            nome_aluno        = row.get('Aluno', ''),
            dias              = int(row['Dias sem reunião'])
        )
        resultados.append({'Aluno': row['Aluno'], 'Orientador': row['Orientador'],
                           'Enviado': '✅ Sim' if ok else '❌ Falhou', 'Detalhe': msg})
    return pd.DataFrame(resultados)

# ===============================================================
# COMPONENTES VISUAIS
# ===============================================================

def card_kpi(col, valor, label, sub, cor):
    cores = {
        'azul':     ('#1a3a6b', '#e8f0fe'),
        'verde':    ('#16a34a', '#f0fdf4'),
        'amarelo':  ('#ca8a04', '#fefce8'),
        'vermelho': ('#dc2626', '#fef2f2'),
    }
    txt, bg = cores.get(cor, ('#333', '#f8f9fa'))
    col.markdown(f"""
    <div style="background:{bg};border-radius:12px;padding:20px 22px;
                border-left:4px solid {txt};margin-bottom:4px">
      <div style="font-size:32px;font-weight:700;color:{txt}">{valor}</div>
      <div style="font-size:14px;font-weight:600;color:{txt};margin-top:2px">{label}</div>
      <div style="font-size:12px;color:#888;margin-top:4px">{sub}</div>
    </div>""", unsafe_allow_html=True)

def badge(texto, tipo):
    cores = {
        'ok':      ('#16a34a', '#f0fdf4'),
        'atencao': ('#ca8a04', '#fefce8'),
        'critico': ('#dc2626', '#fef2f2'),
        'neutro':  ('#64748b', '#f1f5f9'),
    }
    txt, bg = cores.get(tipo, ('#333', '#eee'))
    return f'<span style="background:{bg};color:{txt};padding:3px 10px;border-radius:20px;font-size:12px;font-weight:600">{texto}</span>'

# ===============================================================
# INTERFACE PRINCIPAL
# ===============================================================

st.set_page_config(
    page_title="Dashboard — Check-in Mensal | QualiSaúde",
    page_icon="",
    layout="wide",
)

# Carrega logo em base64
import base64, pathlib
_logo_path = pathlib.Path(__file__).parent / "logo_quali.jpg"
_logo_b64 = ""
if _logo_path.exists():
    _logo_b64 = base64.b64encode(_logo_path.read_bytes()).decode()

_logo_tag = (
    f'<img src="data:image/jpeg;base64,{_logo_b64}" '
    f'style="height:60px;object-fit:contain;margin-right:18px;filter:brightness(0) invert(1)">'
    if _logo_b64 else ""
)

# Header
st.markdown(f"""
<div style="background:linear-gradient(135deg,#0f2a5e,#1a3a6b);color:white;
            padding:28px 32px;border-radius:12px;margin-bottom:24px;
            display:flex;align-items:center">
  {_logo_tag}
  <div>
    <h1 style="margin:0;font-size:22px">Acompanhamento Pedagógico — Check-in Mensal</h1>
    <p style="margin:6px 0 0;opacity:.7;font-size:14px">
      Programa de Mestrado | QualiSaúde / UFRN
    </p>
  </div>
</div>""", unsafe_allow_html=True)

# Carrega dados
with st.spinner("Conectando ao Google Sheets..."):
    df_raw, df_alunos = carregar_dados()
    df = processar(df_raw, df_alunos)

ts = datetime.now().strftime("%d/%m/%Y às %H:%M")
st.caption(f"🕐 Dados atualizados automaticamente a cada 5 minutos · Última leitura: {ts}")

# ── Filtros ──
col_f1, col_f2, col_f3 = st.columns([2, 2, 1])
with col_f1:
    turmas_disp = sorted(df['Turma'].unique().tolist())
    turma_sel = st.selectbox("Filtrar por turma", ["Todas"] + turmas_disp)
with col_f2:
    orient_disp = sorted(df['Orientador curto'].unique().tolist())
    orient_sel = st.selectbox("Filtrar por orientador", ["Todos"] + orient_disp)
with col_f3:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Atualizar dados"):
        st.cache_data.clear()
        st.rerun()

dfv = df.copy()
if turma_sel  != "Todas": dfv = dfv[dfv['Turma'] == turma_sel]
if orient_sel != "Todos": dfv = dfv[dfv['Orientador curto'] == orient_sel]

# ── KPIs ──
total   = len(dfv)
ok      = len(dfv[dfv['Status geral'].str.contains('OK', na=False)])
atencao = len(dfv[dfv['Status geral'].str.contains('Monitorar', na=False)])
critico = len(dfv[dfv['Status geral'].str.contains('Requer', na=False)])

c1, c2, c3, c4 = st.columns(4)
card_kpi(c1, total,   "Total de respostas",    f"{len(df_alunos)} cadastrados no programa", "azul")
card_kpi(c2, ok,      "✅ Situação OK",      f"{round(ok/total*100) if total else 0}% dos discentes", "verde")
card_kpi(c3, atencao, "⚠️ Em atenção",       "monitorar de perto", "amarelo")
card_kpi(c4, critico, "🚨 Situação crítica", "requer ação imediata", "vermelho")

st.markdown("---")

# ── Gráficos ──
# Apenas o gráfico de status geral (pizza) — gráfico "Situação por orientador" removido
st.markdown("#### Status geral dos discentes")
contagem = dfv['Status geral'].value_counts().reset_index()
contagem.columns = ['Status', 'Qtd']
cor_map = {'🔴 Requer ação': '#dc2626', '🟡 Monitorar': '#ca8a04', '🟢 OK': '#16a34a'}
fig = px.pie(contagem, names='Status', values='Qtd',
             color='Status', color_discrete_map=cor_map, hole=0.55)
fig.update_layout(margin=dict(t=0,b=0,l=0,r=0), legend=dict(orientation='h',y=-0.1))
st.plotly_chart(fig, use_container_width=True)

col_g3, col_g4 = st.columns(2)

with col_g3:
    st.markdown("#### Dias sem reunião por discente")
    df_reun = dfv[dfv['Dias sem reunião'].notna()].sort_values('Dias sem reunião', ascending=False)
    fig3 = px.bar(df_reun, x='Dias sem reunião', y='Aluno',
                  orientation='h',
                  color='Dias sem reunião',
                  color_continuous_scale=[[0,'#16a34a'],[0.5,'#ca8a04'],[1,'#dc2626']],
                  range_color=[0, max(df_reun['Dias sem reunião'].max(), 35)])
    fig3.add_vline(x=DIAS_REUNIAO_CRITICO, line_dash='dash', line_color='#dc2626',
                   annotation_text='Crítico (30d)')
    fig3.add_vline(x=DIAS_REUNIAO_ATENCAO, line_dash='dash', line_color='#ca8a04',
                   annotation_text='Atenção (21d)')
    fig3.update_layout(margin=dict(t=0,b=0), coloraxis_showscale=False,
                       yaxis=dict(autorange='reversed'))
    st.plotly_chart(fig3, use_container_width=True)

with col_g4:
    st.markdown("#### Dias aguardando correção")
    df_corr = dfv[dfv['Dias aguardando'].notna()].sort_values('Dias aguardando', ascending=False)
    if df_corr.empty:
        st.success("🎉 Nenhum trabalho aguardando correção com prazo registrado!")
    else:
        fig4 = px.bar(df_corr, x='Dias aguardando', y='Aluno',
                      orientation='h',
                      color='Dias aguardando',
                      color_continuous_scale=[[0,'#ca8a04'],[1,'#dc2626']],
                      range_color=[0, max(df_corr['Dias aguardando'].max(), 15)])
        fig4.add_vline(x=DIAS_CORRECAO_ALERTA, line_dash='dash', line_color='#dc2626',
                       annotation_text=f'Alerta ({DIAS_CORRECAO_ALERTA}d)')
        fig4.update_layout(margin=dict(t=0,b=0), coloraxis_showscale=False,
                           yaxis=dict(autorange='reversed'))
        st.plotly_chart(fig4, use_container_width=True)

st.markdown("---")

# ── Tabela detalhada ──
st.markdown("#### Situação detalhada por discente")

tab_critico, tab_atencao, tab_ok, tab_todos = st.tabs(
    ["🔴 Críticos", "🟡 Em atenção", "🟢 OK", "📄 Todos"]
)

COLUNAS_TABELA = [
    'Turma', 'Aluno', 'Orientador', 'Última reunião',
    'Dias sem reunião', 'Status reunião',
    'Tem pendentes?', 'Qtd trabalhos', 'Postagem mais antiga',
    'Dias aguardando', 'Status correção', 'Status geral'
]
# Filtra colunas existentes
cols_ok = [c for c in COLUNAS_TABELA if c in dfv.columns]

def mostrar_tabela(subset):
    if subset.empty:
        st.info("Nenhum aluno nesta categoria.")
    else:
        st.dataframe(subset[cols_ok].reset_index(drop=True), hide_index=True, use_container_width=True)

with tab_critico:
    mostrar_tabela(dfv[dfv['Status geral'].str.contains('Requer', na=False)])
with tab_atencao:
    mostrar_tabela(dfv[dfv['Status geral'].str.contains('Monitorar', na=False)])
with tab_ok:
    mostrar_tabela(dfv[dfv['Status geral'].str.contains('OK', na=False)])
with tab_todos:
    mostrar_tabela(dfv)

st.markdown("---")

# ── Painel de alertas por email ──
st.markdown("#### 📧 Alertas para orientadores")

criticos_df = dfv[dfv['Dias sem reunião'].notna() & (dfv['Dias sem reunião'] >= DIAS_REUNIAO_CRITICO)]
if criticos_df.empty:
    st.success("Nenhum discente com mais de 30 dias sem reunião. Nenhum alerta necessário.")
else:
    st.warning(
        f"**{len(criticos_df)} discente(s)** com mais de {DIAS_REUNIAO_CRITICO} dias sem reunião. "
        f"Os orientadores serão notificados por email ao clicar no botão abaixo."
    )
    st.dataframe(
        criticos_df[['Turma','Aluno','Orientador','Dias sem reunião','Email Orientador']].reset_index(drop=True),
        hide_index=True, use_container_width=True
    )

    if not EMAIL_SENHA:
        st.info(
            "🔑 Configure a `EMAIL_SENHA` no código para habilitar o envio automático. "
            "Veja as instruções no final deste arquivo."
        )
    else:
        if st.button("🚀 Enviar alertas agora para os orientadores", type="primary"):
            with st.spinner("Enviando emails..."):
                resultado = disparar_alertas_orientadores(dfv)
            st.dataframe(resultado, hide_index=True, use_container_width=True)
            enviados = len(resultado[resultado['Enviado'] == '✅ Sim'])
            st.success(f"✅ {enviados} email(s) enviado(s) de {len(resultado)} orientadores notificados.")

# ── Rodapé ──
st.markdown("---")
st.caption(
    "Sistema de Check-in Mensal — Programa de Graduação | QualiSaúde / UFRN  ·  "
    "Dados lidos diretamente do Google Sheets a cada 5 minutos."
)