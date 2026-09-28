import folium
import streamlit as st
from streamlit_folium import st_folium


def _popup(item):
    html = f"<b>{item['name']}</b><br>Categoria: {item['category']}<br>"
    if item.get("distance_m") is not None:
        html += f"Distância: {item['distance_m']:.0f} m<br>"
    for key, value in item.get("properties", {}).items():
        html += f"{key}: {value}<br>"
    return folium.Popup(html, max_width=300)


def render_map(data, categories, centro=(-23.5505, -46.6333), raio=None):
    """Mapa interativo com pontos, linhas e polígonos (GeoJSON -> Folium)."""
    m = folium.Map(location=list(centro), zoom_start=13 if raio else 12, tiles="OpenStreetMap")
    cores = {c["name"]: c.get("color") or "#3388ff" for c in categories}

    if raio:  # mostra o círculo da busca por proximidade
        folium.Circle(location=list(centro), radius=raio, color="#444", weight=1, fill=True,
                      fill_opacity=0.05, tooltip=f"Raio de busca: {raio} m").add_to(m)
        folium.Marker(location=list(centro), tooltip="Centro da busca",
                      icon=folium.Icon(color="black", icon="crosshairs", prefix="fa")).add_to(m)

    for item in data:
        geom = item["geometry"]
        cor = cores.get(item["category"], "#3388ff")
        gtype = geom["type"]
        if gtype == "Point":
            lon, lat = geom["coordinates"]
            folium.CircleMarker(location=[lat, lon], radius=7, popup=_popup(item), tooltip=item["name"],
                                color=cor, fill=True, fill_color=cor, fill_opacity=0.8).add_to(m)
        elif gtype in ("Polygon", "MultiPolygon", "LineString", "MultiLineString", "MultiPoint"):
            # GeoJson do Folium entende qualquer geometria e já trata a ordem [lon, lat]
            folium.GeoJson(
                {"type": "Feature", "geometry": geom, "properties": {}},
                style_function=lambda _f, c=cor: {"color": c, "fillColor": c, "weight": 2, "fillOpacity": 0.3},
                popup=_popup(item), tooltip=item["name"],
            ).add_to(m)

    st_folium(m, height=600, use_container_width=True, returned_objects=[])

    # Legenda com as cores reais de cada categoria
    presentes = {d["category"] for d in data}
    itens = [f'<span style="display:inline-block;width:12px;height:12px;background:{cores.get(c, "#3388ff")};'
             f'border-radius:2px;margin:0 6px 0 14px"></span>{c.title()}' for c in sorted(presentes)]
    st.markdown("**Legenda:** " + "".join(itens), unsafe_allow_html=True)
