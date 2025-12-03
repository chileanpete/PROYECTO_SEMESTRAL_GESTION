import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import pycountry_convert as pc
from geopy.geocoders import Nominatim

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Dashboard COVID-19", layout="wide")

# --- CARGA DE DATOS OPTIMIZADA ---
@st.cache_data
def get_continent(country_name):
    """Asigna continente basado en el nombre del país."""
    try:
        # Mapeo manual extendido para JHU
        corrections = {
            "US": "United States", "Korea, South": "South Korea", "Taiwan*": "Taiwan",
            "Burma": "Myanmar", "Congo (Kinshasa)": "Congo", "Congo (Brazzaville)": "Congo",
            "Cote d'Ivoire": "Ivory Coast", "West Bank and Gaza": "Israel",
            "Russia": "Russian Federation", "Vietnam": "Viet Nam", "Laos": "Lao People's Democratic Republic",
            "Syria": "Syrian Arab Republic", "Iran": "Iran, Islamic Republic of",
            "Tanzania": "Tanzania, United Republic of", "Venezuela": "Venezuela, Bolivarian Republic of",
            "Bolivia": "Bolivia, Plurinational State of", "Brunei": "Brunei Darussalam",
            "United Kingdom": "United Kingdom", "France": "France"
        }
        country_name = corrections.get(country_name, country_name)
        country_alpha2 = pc.country_name_to_country_alpha2(country_name)
        continent_code = pc.country_alpha2_to_continent_code(country_alpha2)
        continents = {
            'NA': 'North America', 'SA': 'South America', 'AS': 'Asia',
            'OC': 'Oceania', 'EU': 'Europe', 'AF': 'Africa'
        }
        return continents.get(continent_code, "Others")
    except:
        return "Others"

COUNTRY_COORDS = {
    "France": {"lat": 46.2276, "long": 2.2137},
    "United Kingdom": {"lat": 55.3781, "long": -3.4360},
    "Denmark": {"lat": 56.2639, "long": 9.5018},
    "Netherlands": {"lat": 52.1326, "long": 5.2913},
    "US": {"lat": 37.0902, "long": -95.7129},
    "United States": {"lat": 37.0902, "long": -95.7129}
}

@st.cache_data
def load_data():
    # Cargar datos y asegurar tipos
    df = pd.read_csv("covid_2020_2022.csv", parse_dates=["file_date"])

    # Asegurar que existan todas las columnas necesarias
    if "active" not in df.columns:
        df["active"] = df["confirmed"] - df["deaths"] - df["recovered"]
    
    # Crear columna de continente
    unique_countries = df["country_region"].unique()
    continent_map = {c: get_continent(c) for c in unique_countries}
    df["Continent"] = df["country_region"].map(continent_map)
    
    return df

try:
    df = load_data()
except FileNotFoundError:
    st.error("No se encontró el archivo de datos. Ejecuta la etapa de generación primero.")
    st.stop()

# --- TÍTULO ---
st.title("Tendencias Epidemiológicas Globales COVID-19 (2020-2022)")
st.markdown("---")

# --- FILTROS ---
st.sidebar.header("Filtros")

#Filtro de Continente
all_continents = sorted(df["Continent"].unique())
selected_continents = st.sidebar.multiselect("Filtrar por Continente", all_continents)

#Filtro de País (Dependiente del continente seleccionado)
if selected_continents:
    filtered_countries = df[df["Continent"].isin(selected_continents)]["country_region"].unique()
else:
    filtered_countries = df["country_region"].unique()

selected_countries = st.sidebar.multiselect("Filtrar por País", sorted(filtered_countries))

#Filtro de Fechas
min_date = df["file_date"].min().date()
max_date = df["file_date"].max().date()
start_date, end_date = st.sidebar.date_input("Rango de Fechas", [min_date, max_date], min_value=min_date, max_value=max_date)

# --- FILTRADO DEL DATAFRAME ---
mask_date = (df["file_date"].dt.date >= start_date) & (df["file_date"].dt.date <= end_date)
df_filtered = df.loc[mask_date]

if selected_continents:
    df_filtered = df_filtered[df_filtered["Continent"].isin(selected_continents)]
if selected_countries:
    df_filtered = df_filtered[df_filtered["country_region"].isin(selected_countries)]

# --- KPIs (INDICADORES CLAVE) ---
df_last_day = df_filtered[df_filtered["file_date"].dt.date == end_date]

if not df_last_day.empty:
    kpi_confirmed = df_last_day["confirmed"].sum()
    kpi_deaths = df_last_day["deaths"].sum()
else:
    kpi_confirmed = 0
    kpi_deaths = 0

# Tasa de Letalidad
fatality_rate = (kpi_deaths / kpi_confirmed * 100) if kpi_confirmed > 0 else 0

cols = st.columns(3)
cols[0].metric("Total Confirmados", f"{kpi_confirmed:,.0f}")
cols[1].metric("Total Fallecidos", f"{kpi_deaths:,.0f}", delta_color="inverse")
cols[2].metric("Tasa de Letalidad", f"{fatality_rate:.2f}%")

st.markdown("---")

# --- EVOLUCION TEMPORAL --
st.subheader("Evolución Temporal Comparativa")

# Agrupar por fecha para la línea de tiempo
timeline = df_filtered.groupby("file_date")[["confirmed", "deaths", "recovered", "active"]].sum().reset_index()

if not timeline.empty:
    # Pivotar para Plotly (formato largo)
    timeline_long = timeline.melt(id_vars="file_date", var_name="Estado", value_name="Casos")
    
    fig_evol = px.line(timeline_long, x="file_date", y="Casos", color="Estado",
                       color_discrete_map={
                           "confirmed": "#3366CC", # Azul
                           "active": "#FF9900",    # Naranja
                           "recovered": "#109618", # Verde
                           "deaths": "#DC3912"     # Rojo
                       },
                       title="Curvas de Evolución")
    st.plotly_chart(fig_evol, use_container_width=True)
else:
    st.warning("No hay datos para el rango seleccionado.")

st.markdown("---")

# --- MAPA Y RANKING ---
st.markdown("---")
st.subheader("Mapa Global (Casos Confirmados)")

if not df_last_day.empty:
  country_totals = df_last_day.groupby("country_region")[["confirmed", "lat", "long_"]].agg({
        "confirmed": "sum",
        "lat": "first", # Temporal
        "long_": "first" # Temporal
    }).reset_index()

def fix_coords(row):
        if row["country_region"] in COUNTRY_COORDS:
            return pd.Series([COUNTRY_COORDS[row["country_region"]]["lat"], COUNTRY_COORDS[row["country_region"]]["long"]])
        else:
            # Si no está en manual, intentamos tomar la coordenada del registro con más casos de ese país
            # (Para esto necesitamos volver al df original filtrado)
            try:
                country_data = df_last_day[df_last_day["country_region"] == row["country_region"]]
                best_row = country_data.sort_values("confirmed", ascending=False).iloc[0]
                return pd.Series([best_row["lat"], best_row["long_"]])
            except:
                return pd.Series([row["lat"], row["long_"]])

country_totals[["lat", "long_"]] = country_totals.apply(fix_coords, axis=1)
    
# Limpiar nulos finales
map_data = country_totals.dropna(subset=["lat", "long_"])

if not map_data.empty:
    fig_map = px.scatter_geo(map_data, lat="lat", lon="long_", size="confirmed",
                                 color="confirmed", hover_name="country_region",
                                 color_continuous_scale="Reds", size_max=35,
                                 projection="natural earth",
                                 title="Distribución Geográfica")
    fig_map.update_layout(margin={"r":0,"t":30,"l":0,"b":0})
    st.plotly_chart(fig_map, use_container_width=True)
else:
    st.info("Sin datos geográficos.")
    
# --- CONCLUSION AUTOMATICA ---
col_analysis, col_ranking = st.columns([1, 1]) 

with col_analysis:
    st.subheader("Conclusiones")
    
    if not timeline.empty and len(timeline) > 1:
        # 1. Tasa de Crecimiento
        start_val = timeline.iloc[0]["confirmed"]
        end_val = timeline.iloc[-1]["confirmed"]
        
        if start_val > 0:
            growth_rate = ((end_val - start_val) / start_val) * 100
        else:
            growth_rate = 0 if end_val == 0 else 100
            
        st.info(f"""
        **Tasa de Crecimiento:**
        
        En el periodo del **{start_date}** al **{end_date}**, los casos aumentaron un **{growth_rate:.2f}%**.
        
        * Casos Iniciales: {start_val:,.0f}
        * Casos Finales: {end_val:,.0f}
        """)

        st.write("") 

        # 2. Indicador de Rebrote
        timeline["new_cases"] = timeline["confirmed"].diff().fillna(0)
        timeline["7d_avg"] = timeline["new_cases"].rolling(window=7).mean()
        
        if len(timeline) >= 14:
            current_week_avg = timeline["7d_avg"].iloc[-1]
            prev_week_avg = timeline["7d_avg"].iloc[-8]
            rebound_ratio = current_week_avg / prev_week_avg if prev_week_avg > 0 else 0
            
            if rebound_ratio > 1.2:
                st.error(f"**ALERTA DE REBROTE DETECTADA**\n\nÍndice de rebrote: **{rebound_ratio:.2f}**. Los casos están creciendo rápidamente en la última semana del periodo seleccionado.")
            elif rebound_ratio > 1.0:
                st.warning(f"**Tendencia al Alza**\n\nÍndice de rebrote: **{rebound_ratio:.2f}**. Ligero incremento de casos en la última semana.")
            else:
                st.success(f"**Tendencia Estable o a la Baja**\n\nÍndice de rebrote: **{rebound_ratio:.2f}**. La velocidad de contagio está disminuyendo.")
        else:
            st.write("Se necesitan al menos 14 días de datos para calcular el índice de rebrote.")
    else:
        st.write("Datos insuficientes para generar una conclusión.")

# --- RANKING ---
with col_ranking:
    st.subheader("Top Países (Casos Activos)")
    # Ranking por casos ACTIVOS
    if not df_last_day.empty:
        top_active = df_last_day.groupby("country_region")["active"].max().sort_values(ascending=False).head(10).reset_index()
    
        if not top_active.empty:
            fig_rank = px.bar(top_active, x="active", y="country_region", orientation='h',
                              color="active", color_continuous_scale="Oranges",
                              title="Países con mayor casos activos.")
            fig_rank.update_layout(yaxis={'categoryorder':'total ascending'}, margin={"r":0,"t":30,"l":0,"b":0})
            st.plotly_chart(fig_rank, use_container_width=True)
        else:
            st.info("No hay datos para el ranking.")
    else:
        st.info("No hay datos para el ranking.")