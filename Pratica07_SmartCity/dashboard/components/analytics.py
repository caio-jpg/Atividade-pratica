import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime

def render_analytics(data, analytics_data):
    """Renderizar gráficos e análises estatísticas"""
    
    # Converter dados para DataFrame
    df = pd.DataFrame(data)
    
    # Métricas principais
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total de Registros", len(df))
    
    with col2:
        num_categories = df['category'].nunique()
        st.metric("Categorias", num_categories)
    
    with col3:
        points = len([d for d in data if d['geometry']['type'] == 'Point'])
        st.metric("Pontos", points)
    
    with col4:
        polygons = len([d for d in data if d['geometry']['type'] == 'Polygon'])
        st.metric("Polígonos", polygons)
    
    st.markdown("---")
    
    # Gráficos
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📊 Distribuição por Categoria")
        
        category_counts = df['category'].value_counts().reset_index()
        category_counts.columns = ['Categoria', 'Contagem']
        
        fig = px.pie(
            category_counts,
            values='Contagem',
            names='Categoria',
            hole=0.4,
            color_discrete_sequence=px.colors.qualitative.Set3
        )
        fig.update_traces(textposition='inside', textinfo='percent+label')
        fig.update_layout(height=400)
        st.plotly_chart(fig, width="stretch")
    
    with col2:
        st.subheader("📈 Top 10 Categorias")
        
        fig = px.bar(
            category_counts.head(10),
            x='Contagem',
            y='Categoria',
            orientation='h',
            color='Categoria',
            color_discrete_sequence=px.colors.qualitative.Pastel
        )
        fig.update_layout(height=400, showlegend=False)
        st.plotly_chart(fig, width="stretch")
    
    st.markdown("---")
    
    # Análise temporal
    if analytics_data and 'temporal_data' in analytics_data:
        st.subheader("📅 Evolução Temporal")
        
        temporal_df = pd.DataFrame(analytics_data['temporal_data'])
        
        if not temporal_df.empty:
            temporal_df['data'] = temporal_df['_id'].apply(
                lambda x: f"{x['year']}-{x['month']:02d}"
            )
            temporal_df = temporal_df.sort_values('data')
            
            fig = px.line(
                temporal_df,
                x='data',
                y='count',
                markers=True,
                title='Cadastros por Mês'
            )
            fig.update_layout(height=400, xaxis_title="Mês", yaxis_title="Quantidade")
            st.plotly_chart(fig, width="stretch")
    
    st.markdown("---")
    
    # Tabela de dados
    st.subheader("📋 Dados Detalhados")
    
    # Preparar dados para tabela
    table_data = []
    for item in data:
        table_data.append({
            'Nome': item['name'],
            'Categoria': item['category'],
            'Tipo': item['geometry']['type'],
            'Timestamp': item.get('timestamp', 'N/A')
        })
    
    table_df = pd.DataFrame(table_data)
    st.dataframe(table_df, width="stretch", height=300)
    
    # Download
    csv = table_df.to_csv(index=False)
    st.download_button(
        label="📥 Baixar CSV",
        data=csv,
        file_name="smart_city_data.csv",
        mime="text/csv"
    )