import streamlit as st
import pandas as pd 

@st.cache_data
def carregar_dados():
    df = pd.read_csv('Check-in Mensal — Programa de Graduação - Dashboard (1).csv', skiprows=1)
    return df

dados = carregar_dados()

# corrigir colunas
dados['Qtd trabalhos'] = pd.to_numeric(dados['Qtd trabalhos'], errors='coerce')

#corrigir os nomes
dados['Aluno'] = (
    dados['Aluno']
    .fillna('')
    .str.split()
    .str[:2]
    .str.join(' ')
    .str.title()
)

dados['Orientador'] = (
    dados['Orientador']
    .fillna('')
    .str.split()
    .str[:2]
    .str.join(' ')
    .str.title()
)

dados['Dias aguardando'] = pd.to_numeric(dados['Dias aguardando'], errors='coerce')
dados['Dias sem reunião'] = pd.to_numeric(dados['Dias sem reunião'], errors='coerce')

#verificar atrasados
atrasados = dados[dados['Status correção'] == '🔴 Atrasado']
#docentes sem atrasos
em_dia = dados[dados['Status correção'] == '🟢 Sem pendência']

def mostrar_atrasados():
    if atrasados.empty:
        st.success("Nenhum docente atrasado! Todos estão em dia.")
    else:
        st.error(f"{len(atrasados)} docente(s) com pendência!")
        st.dataframe(atrasados[['Aluno', 'Orientador','Status correção','Postagem mais antiga', 'Dias aguardando','Última reunião' ]], hide_index=True)

def mostrar_em_dia():
    if em_dia.empty:
        st.success("Nenhum docente em dia! Todos estão atrasados.")
    else:
        st.info(f"{len(em_dia)} docente(s) sem pendência!")
        st.dataframe(em_dia[['Aluno', 'Orientador', 'Status correção', 'Última reunião']], hide_index=True)


def situacao_orientador():
    # criar coluna de risco
    def classificar(dias):
        if pd.isna(dias):
            return "Sem dados"
        elif dias > 30:
            return "🔴 Crítico"
        elif dias > 15:
            return "🟠 Atenção"
        else:
            return "🟢 OK"

    dados['Nível'] = dados['Dias sem reunião'].apply(classificar)

    # separações
    critico = dados[dados['Nível'] == "🔴 Crítico"]
    atencao = dados[dados['Nível'] == "🟠 Atenção"]
    ok = dados[dados['Nível'] == "🟢 OK"]

    # RESUMO GERAL
    st.markdown("### Situação dos Orientadores")

    col1, col2, col3 = st.columns(3)
    col1.success(f"🟢 OK: {len(ok)}")
    col2.warning(f"🟠 Atenção: {len(atencao)}")
    col3.error(f"🔴 Crítico: {len(critico)}")

    # 🔴 CRÍTICOS
    if not critico.empty:
        st.markdown("#### 🔴 Casos Críticos (> 30 dias)")
        st.dataframe(
            critico.sort_values(by='Dias sem reunião', ascending=False)[
                ['Aluno', 'Orientador', 'Dias sem reunião', 'Última reunião']
            ],
            hide_index=True
        )

    # 🟠 ATENÇÃO
    if not atencao.empty:
        st.markdown("#### 🟠 Atenção (15–30 dias)")
        st.dataframe(
            atencao.sort_values(by='Dias sem reunião', ascending=False)[
                ['Aluno', 'Orientador', 'Dias sem reunião', 'Última reunião']
            ],
            hide_index=True
        )

    # 🟢 OK
    if not ok.empty:
        st.markdown("#### 🟢 Em dia (até 15 dias)")
        st.dataframe(
            ok.sort_values(by='Dias sem reunião', ascending=False)[
                ['Aluno', 'Orientador', 'Dias sem reunião', 'Última reunião']
            ],
            hide_index=True
        )
# interface

st.title("Dashboard")
st.header("Análise de Check-ins Mensais")

st.markdown("#### Docentes com trabalhos atrasados:")
mostrar_atrasados()
st.markdown("#### Docentes em dia:")
mostrar_em_dia()
st.markdown("#### Alertas sobre o Orientador:")
situacao_orientador()

