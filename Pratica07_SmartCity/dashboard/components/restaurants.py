"""Aba de restaurantes: busca por proximidade ($geoNear) e estatísticas (aggregation)."""

import folium
import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from streamlit_folium import st_folium

TIPOS = ["Chicken", "Meat", "Fast Food", "Sandwiches", "Burgers", "Grilled", "Oriental",
         "Pizza", "Japonesa", "Italiana", "Mexicana", "Doces & Bolos"]


@st.cache_data(ttl=60)
def _get(url, params=None):
    try:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    except requests.RequestException:
        return None


def render_restaurants(api_url):
    stats = _get(f"{api_url}/restaurantes/stats")
    if not stats or not stats.get("total"):
        st.info("A collection `restaurantes` está vazia. Importe com `python scripts/import_restaurantes.py`.")
        return

    st.subheader("🍔 Restaurantes próximos (MongoDB $geoNear)")
    c1, c2, c3, c4 = st.columns(4)
    lat = c1.number_input("Latitude", value=-23.5505, format="%.4f", key="r_lat")
    lon = c2.number_input("Longitude", value=-46.6333, format="%.4f", key="r_lon")
    max_km = c3.number_input("Raio (km)", min_value=1.0, max_value=20000.0, value=2000.0, step=50.0, key="r_km")
    limite = c4.number_input("Máx. resultados", 1, 500, 25, key="r_lim")
    c5, c6, c7 = st.columns(3)
    tipo = c5.selectbox("Tipo de cozinha", ["(todos)"] + TIPOS, key="r_tipo")
    aberto = c6.selectbox("Situação", ["(todos)", "Abertos", "Fechados"], key="r_aberto")
    nota = c7.slider("Nota mínima", 0.0, 10.0, 0.0, 0.5, key="r_nota")

    params = {"lon": lon, "lat": lat, "max_km": max_km, "limit": int(limite)}
    if tipo != "(todos)":
        params["tipo"] = tipo
    if aberto != "(todos)":
        params["aberto"] = aberto == "Abertos"
    if nota > 0:
        params["rating_min"] = nota
    rest = _get(f"{api_url}/restaurantes/near", params) or []

    if not rest:
        st.warning("Nenhum restaurante no raio informado. Aumente o raio: os dados gerados pelo Faker "
                   "estão espalhados pelo mundo todo (veja o README).")
    else:
        m = folium.Map(location=[lat, lon], zoom_start=4 if max_km > 500 else 11)
        folium.Marker([lat, lon], tooltip="Você está aqui",
                      icon=folium.Icon(color="red", icon="user", prefix="fa")).add_to(m)
        for r in rest:
            rlon, rlat = r["coordinates"]
            cor = "green" if r.get("isOpen") else "gray"
            folium.Marker(
                [rlat, rlon],
                tooltip=f"{r['title']} — {r['distance_km']} km",
                popup=folium.Popup(
                    f"<b>{r['title']}</b><br>{', '.join(r['type'])}<br>Nota: {r['rating']} "
                    f"({r['reviewsCount']} avaliações)<br>Taxa de entrega: {r['deliveryFee']}<br>"
                    f"{r.get('street')}, {r.get('neighborhood')} — {r.get('city')}/{r.get('state')}<br>"
                    f"{'🟢 Aberto' if r.get('isOpen') else '⚫ Fechado'}", max_width=300),
                icon=folium.Icon(color=cor, icon="cutlery", prefix="fa"),
            ).add_to(m)
        st_folium(m, height=450, use_container_width=True, returned_objects=[], key="mapa_rest")

        df = pd.DataFrame(rest)
        df["type"] = df["type"].apply(", ".join)
        st.dataframe(df[["title", "distance_km", "type", "rating", "reviewsCount", "deliveryFee", "isOpen",
                         "city", "state"]], hide_index=True, width="stretch")

    # ---------------- Estatísticas (aggregation pipeline) -------------------
    st.markdown("---")
    st.subheader("📊 Estatísticas gerais")
    m1, m2, m3 = st.columns(3)
    m1.metric("Restaurantes", stats["total"])
    m2.metric("Abertos", stats["abertos"].get("true", 0))
    m3.metric("Fechados", stats["abertos"].get("false", 0))

    g1, g2 = st.columns(2)
    por_tipo = pd.DataFrame(stats["por_tipo"]).rename(columns={"_id": "Tipo"})
    fig = px.bar(por_tipo, x="total", y="Tipo", orientation="h", color="rating_medio",
                 color_continuous_scale="Viridis", labels={"total": "Restaurantes", "rating_medio": "Nota média"},
                 title="Restaurantes por tipo de cozinha")
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=420)
    g1.plotly_chart(fig, width="stretch")

    por_estado = pd.DataFrame(stats["por_estado"]).rename(columns={"_id": "UF"})
    fig2 = px.bar(por_estado, x="UF", y="total", title="Restaurantes por UF (endereço cadastrado)",
                  labels={"total": "Restaurantes"})
    fig2.update_layout(height=420)
    g2.plotly_chart(fig2, width="stretch")
