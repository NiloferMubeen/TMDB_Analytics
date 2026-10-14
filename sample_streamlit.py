import streamlit as st
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

movies_df = pd.read_csv(r'data\movies.csv')

st.set_page_config(layout='wide')

st.title("TMDB Movie Analytics")

c1,c2= st.columns(2)

with c1:
    
    st.subheader('Correlation Heatmap',divider='rainbow')
    num_cols = movies_df.select_dtypes(include="number").columns.drop("movie_id").tolist()

    fig, ax = plt.subplots(figsize=(8, 6))
    sns.heatmap(movies_df[num_cols].corr(), annot=True, fmt=".2f", cmap="coolwarm", center=0, ax=ax)

    st.pyplot(fig)


with c2:   
    st.subheader("Movies Released per Year",divider='rainbow')
    movies_df["release_date"] = pd.to_datetime(movies_df["release_date"])

    movies_per_year = movies_df.groupby(movies_df["release_date"].dt.year).size()
    fig, ax = plt.subplots()
    ax.plot(movies_per_year.index, movies_per_year.values)   
    
    ax.set_xlabel("Year")
    ax.set_ylabel("Number of Movies")
    st.pyplot(fig)
