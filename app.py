import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# ---------------------------------------------------------
# CONFIGURAÇÃO DA PÁGINA
# ---------------------------------------------------------
st.set_page_config(
    page_title="Gestão de Portfólio de LTs",
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
    
    # Tratamento de tipos e valores nulos para evitar erros no sort_values
    df = df.dropna(subset=['Ano', 'Custo total (R$)'])
    df['Ano_Int'] = pd.to_numeric(df['Ano'], errors='coerce')
    df = df.dropna(subset=['Ano_Int'])
    df['Ano_Int'] = df['Ano_Int'].astype(int)
    
    df['ID'] = df['ID'].astype(str)
    df['Obra_Label'] = df['ID'] + " - " + df['Nome']
    return df

# Permitir upload pela barra lateral ou carregar o arquivo local por padrão
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
# 2. PAINEL SUPERIOR: MATRIZ EDITÁVEL
# ---------------------------------------------------------
st.subheader("✍️ Matriz Editável de Aportes Financeiros")

obras_unicas = sorted(df_raw['Obra_Label'].unique())
obra_selecionada = st.selectbox("Selecione uma Linha de Transmissão para editar os aportes:", obras_unicas)

# Pivotar para formar a Matriz (Etapas x Anos) para a obra escolhida
df_obra = df_raw[df_raw['Obra_Label'] == obra_selecionada]
matriz_df = df_obra.pivot_table(
    index='Etapa', 
    columns='Ano_Int', 
    values='Custo total (R$)', 
    aggfunc='sum', 
    fill_value=0
)

st.caption("Altere ou redistribua os valores na tabela abaixo. O gráfico de Gantt abaixo será rebalanceado automaticamente em tempo real:")
matriz_editada = st.data_editor(matriz_df, use_container_width=True)

# ---------------------------------------------------------
# 3. CONSOLIDAÇÃO DOS DADOS (REBALANCEAMENTO E CONTINUIDADE)
# ---------------------------------------------------------
df_modificado = df_raw.copy()

# Atualizar os valores editados de volta no dataframe principal
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

# Garantir tipos numéricos estritos na coluna de anos
df_modificado['Ano_Int'] = pd.to_numeric(df_modificado['Ano_Int'], errors='coerce')
df_modificado = df_modificado.dropna(subset=['Ano_Int'])
df_modificado['Ano_Int'] = df_modificado['Ano_Int'].astype(int)

# Agrupar dados consolidados eliminando zeros
df_gantt = df_modificado[df_modificado['Custo total (R$)'] > 0].groupby(
    ['Obra_Label', 'Etapa', 'Ano_Int']
)['Custo total (R$)'].sum().reset_index()

# Algoritmo de Continuidade: Agrupar Anos Consecutivos para criar Barras Unificadas
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
# 4. PLOTAGEM DO GANTT COM SUB-LINHAS DINÂMICAS E BARRAS CONTÍNUAS
# ---------------------------------------------------------
st.divider()
st.subheader("📊 Cronograma Unificado do Portfólio (Gantt)")

fig, ax = plt.subplots(figsize=(14, 8), dpi=300)
ax.set_facecolor("#f8f9fa")

y_positions = {obra: i * 1.3 for i, obra in enumerate(obras_unicas[::-1])}
anos_globais = sorted(df_raw['Ano_Int'].unique())

for obra in obras_unicas:
    df_o = df_inter[df_inter['Obra'] == obra] if not df_inter.empty else pd.DataFrame()
    y_center = y_positions[obra]
    row_height = 0.85
    
    if not df_o.empty:
        etapas_na_obra = df_o['Etapa'].unique()
        n_etapas = len(etapas_na_obra)
        sub_height = row_height / max(n_etapas, 1)
        
        for i, (_, row) in enumerate(df_o.iterrows()):
            etapa = row['Etapa']
            ano_i = row['Ano_Inicio']
            ano_f = row['Ano_Fim']
            custo = row['Custo_Total']
            cor = CORES_ETAPAS.get(etapa, "#333333")
            
            idx_etapa = list(etapas_na_obra).index(etapa)
            sub_y = y_center + (row_height / 2) - (idx_etapa * sub_height) - (sub_height / 2)
            
            left = ano_i - 0.425
            width = (ano_f - ano_i + 1) - 0.15
            
            ax.barh(
                y=sub_y, 
                width=width, 
                left=left, 
                height=sub_height * 0.88, 
                color=cor, 
                edgecolor="white", 
                linewidth=0.8,
                zorder=3
            )
            
            duracao = f"{ano_i}-{ano_f}" if ano_i != ano_f else f"{ano_i}"
            custo_fmt = f"R$ {custo/1e3:.0f}k" if custo >= 1e3 else f"R$ {custo:.0f}"
            
            font_size = 7.5 if n_etapas <= 2 else 6
            ax.text(
                left + width / 2, 
                sub_y, 
                f"{etapa} ({duracao}): {custo_fmt}", 
                ha='center', 
                va='center', 
                color='white', 
                fontsize=font_size, 
                fontweight='bold',
                zorder=4
            )

# Formatação visual do gráfico
ax.set_yticks([y_positions[o] for o in obras_unicas[::-1]])
ax.set_yticklabels(obras_unicas[::-1], fontsize=9.5, fontweight='bold', color="#2c3e50")

ax.set_xticks(anos_globais)
ax.set_xticklabels([str(a) for a in anos_globais], fontsize=10, fontweight='bold', color="#2c3e50")

ax.set_xlabel("Eixo X: Anos do Cronograma", fontsize=11, fontweight='bold', labelpad=10, color="#2c3e50")
ax.set_ylabel("Eixo Y: Linhas de Transmissão", fontsize=11, fontweight='bold', labelpad=10, color="#2c3e50")

ax.grid(axis='x', color='#dcdde1', linestyle='--', linewidth=1, zorder=1)
ax.set_axisbelow(True)

# Legenda das Macroetapas
legend_patches = [
    mpatches.Patch(color=color, label=etapa) 
    for etapa, color in CORES_ETAPAS.items() 
    if not df_gantt.empty and etapa in df_gantt['Etapa'].unique()
]
ax.legend(
    handles=legend_patches, 
    title="Macroetapas", 
    bbox_to_anchor=(1.01, 1), 
    loc='upper left', 
    frameon=True, 
    facecolor='#ffffff', 
    edgecolor='#dcdde1'
)

st.pyplot(fig, use_container_width=True)
