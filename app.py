import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ---------------------------------------------------------
# CONFIGURAÇÃO DA PÁGINA
# ---------------------------------------------------------
st.set_page_config(
    page_title="Gestão de Portfólio de LTs (Interativo)",
    page_icon="⚡",
    layout="wide"
)

st.title("⚡ Gestão de Portfólio de Obras de Transmissão")

# ---------------------------------------------------------
# 1. CARREGAMENTO E TRATAMENTO DE DADOS
# ---------------------------------------------------------
@st.cache_data
def load_data(file_source):
    df = pd.read_excel(file_source, sheet_name="Base_Dados")
    
    # Tratamento de tipos e valores nulos
    df = df.dropna(subset=['Ano', 'Custo total (R$)'])
    df['Ano_Int'] = pd.to_numeric(df['Ano'], errors='coerce')
    df = df.dropna(subset=['Ano_Int'])
    df['Ano_Int'] = df['Ano_Int'].astype(int)
    
    df['ID'] = df['ID'].astype(str)
    df['Obra_Label'] = df['ID'] + " - " + df['Nome']
    return df

uploaded_file = st.sidebar.file_uploader("Carregue sua base de dados Excel", type=["xlsx", "xls"])
NOME_ARQUIVO_PADRAO = "base_dados_gantt_LT_ficticia-5.xlsx"

df_raw = None

if uploaded_file is not None:
    try:
        df_raw = load_data(uploaded_file)
    except Exception as e:
        st.error(f"Erro ao processar o arquivo enviado: {e}")
        st.stop()
else:
    try:
        df_raw = load_data(NOME_ARQUIVO_PADRAO)
    except Exception as e:
        st.info("💡 Faça o upload da base de dados Excel na barra lateral (ou certifique-se de que o arquivo padrão está no repositório).")
        st.stop()

# Cores oficiais das macroetapas
CORES_ETAPAS = {
    "Topografia": "#1f77b4",
    "Projetos": "#9467bd",
    "Fundiário": "#ff7f0e",
    "Meio ambiente": "#2ca02c",
    "Construção": "#d62728",
    "Processos": "#17becf",
    "Desativação": "#7f7f7f"
}

# ---------------------------------------------------------
# 2. PAINEL SUPERIOR: REORGANIZAÇÃO DE ANOS E VALORES
# ---------------------------------------------------------
st.subheader("✍️ Painel de Ajuste e Realocação Financeira")

obras_unicas = sorted(df_raw['Obra_Label'].unique())
obra_selecionada = st.selectbox("Selecione uma Linha de Transmissão para gerenciar os aportes:", obras_unicas)

# Pivotar para formar a Matriz (Etapas x Anos) para a obra escolhida
df_obra = df_raw[df_raw['Obra_Label'] == obra_selecionada]
matriz_df = df_obra.pivot_table(
    index='Etapa', 
    columns='Ano_Int', 
    values='Custo total (R$)', 
    aggfunc='sum', 
    fill_value=0
)

st.caption("💡 **Para mover ou alterar aportes:** Edite os valores diretamente nas colunas correspondentes aos anos. Ao zerar um ano e preencher outro, a barra do gráfico é remanejada automaticamente no gráfico interativo abaixo.")
matriz_editada = st.data_editor(matriz_df, use_container_width=True)

# ---------------------------------------------------------
# 3. CONSOLIDAÇÃO DOS DADOS
# ---------------------------------------------------------
df_modificado = df_raw.copy()

for etapa in matriz_editada.index:
    for ano in matriz_editada.columns:
        novo_valor = matriz_editada.loc[etapa, ano]
        mask = (df_modificado['Obra_Label'] == obra_selecionada) & \
               (df_modificado['Etapa'] == etapa) & \
               (df_modificado['Ano_Int'] == ano)
        if mask.any():
            df_modificado.loc[mask, 'Custo total (R$)'] = novo_valor
        elif novo_valor > 0:
            nova_linha = {
                'ID': obra_selecionada.split(' - ')[0],
                'Nome': obra_selecionada.split(' - ')[1],
                'Obra_Label': obra_selecionada,
                'Etapa': etapa,
                'Ano_Int': int(ano),
                'Custo total (R$)': novo_valor
            }
            df_modificado = pd.concat([df_modificado, pd.DataFrame([nova_linha])], ignore_index=True)

df_modificado['Ano_Int'] = pd.to_numeric(df_modificado['Ano_Int'], errors='coerce')
df_modificado = df_modificado.dropna(subset=['Ano_Int'])
df_modificado['Ano_Int'] = df_modificado['Ano_Int'].astype(int)

df_gantt = df_modificado[df_modificado['Custo total (R$)'] > 0].groupby(
    ['Obra_Label', 'Etapa', 'Ano_Int']
)['Custo total (R$)'].sum().reset_index()

# Consolidação de Anos Consecutivos
intervalos = []
for (obra, etapa), group in df_gantt.groupby(['Obra_Label', 'Etapa']):
    group = group.sort_values('Ano_Int')
    anos = group['Ano_Int'].tolist()
    custos = group.set_index('Ano_Int')['Custo total (R$)'].to_dict()
    
    start_year = anos[0]
    prev_year = anos[0]
    total_custo = custos[anos[0]]
    
    for ano in anos[1:]:
        if ano == prev_year + 1:
            prev_year = ano
            total_custo += custos[ano]
        else:
            intervalos.append({
                'Obra': obra,
                'Etapa': etapa,
                'Ano_Inicio': start_year,
                'Ano_Fim': prev_year,
                'Custo_Total': total_custo
            })
            start_year = ano
            prev_year = ano
            total_custo += custos[ano]
            
    intervalos.append({
        'Obra': obra,
        'Etapa': etapa,
        'Ano_Inicio': start_year,
        'Ano_Fim': prev_year,
        'Custo_Total': total_custo
    })

df_inter = pd.DataFrame(intervalos)

# ---------------------------------------------------------
# 4. GRÁFICO GANTT TOTALMENTE INTERATIVO COM PLOTLY
# ---------------------------------------------------------
st.divider()
st.subheader("📊 Cronograma Unificado Interativo (Plotly)")

if not df_inter.empty:
    fig = go.Figure()

    for _, row in df_inter.iterrows():
        duracao = f"{row['Ano_Inicio']}-{row['Ano_Fim']}" if row['Ano_Inicio'] != row['Ano_Fim'] else f"{row['Ano_Inicio']}"
        custo = row['Custo_Total']
        custo_fmt = f"R$ {custo/1e3:.0f}k" if custo >= 1e3 else f"R$ {custo:.0f}"
        
        x_start = row['Ano_Inicio'] - 0.4
        x_end = row['Ano_Fim'] + 0.4
        
        fig.add_trace(go.Bar(
            y=[row['Obra']],
            x=[x_end - x_start],
            base=[x_start],
            orientation='h',
            name=row['Etapa'],
            marker_color=CORES_ETAPAS.get(row['Etapa'], "#333333"),
            hoverinfo='text',
            hovertext=f"<b>Obra:</b> {row['Obra']}<br><b>Etapa:</b> {row['Etapa']}<br><b>Período:</b> {duracao}<br><b>Investimento:</b> {custo_fmt}",
            text=f"{row['Etapa']} ({duracao}): {custo_fmt}",
            textposition='inside',
            insidetextanchor='middle',
            showlegend=False
        ))

    anos_globais = sorted(df_raw['Ano_Int'].unique())
    fig.update_layout(
        height=600,
        barmode='stack',
        xaxis=dict(
            title="Anos do Cronograma",
            tickmode='array',
            tickvals=anos_globais,
            ticktext=[str(a) for a in anos_globais],
            range=[min(anos_globais) - 0.8, max(anos_globais) + 0.8],
            gridcolor='#dcdde1'
        ),
        yaxis=dict(
            title="Linhas de Transmissão",
            autorange="reversed"
        ),
        plot_bgcolor="#f8f9fa",
        margin=dict(l=50, r=50, t=30, b=50)
    )

    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("Nenhum dado encontrado para gerar o gráfico.")
