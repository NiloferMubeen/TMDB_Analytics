import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine, text
from streamlit_option_menu import option_menu

st.set_page_config(page_title="Reel Insights", layout="wide")

# ---------- Database connection (same as your notebooks) ----------
engine = create_engine("postgresql+psycopg2://postgres:1234@localhost/tmdb")


def run_query(sql, params=None):
    return pd.read_sql(text(sql), engine, params=params)


# ---------- Sidebar menu ----------
with st.sidebar:
    page = option_menu(
        "Reel Insights",
        ["Filters", "Dashboard", "Query Explorer"],
        icons=["funnel", "bar-chart", "database"],
    )

# ---------- Load data (one row per movie, genres joined into one string) ----------
movies_sql = """
SELECT m.movie_id, m.title, m.original_language, m.release_date, m.runtime,
       m.budget, m.revenue, m.popularity, m.vote_average, m.vote_count,
       COALESCE(STRING_AGG(g.genre_name, ', '), '') AS genres
FROM movies m
LEFT JOIN movie_genres mg ON m.movie_id = mg.movie_id
LEFT JOIN genres g ON mg.genre_id = g.genre_id
GROUP BY m.movie_id, m.title, m.original_language, m.release_date, m.runtime,
         m.budget, m.revenue, m.popularity, m.vote_average, m.vote_count
"""


def get_filtered_movies():
    """Shows the filter widgets and returns the movies matching them."""
    df = run_query(movies_sql)

    all_genres = run_query("SELECT genre_name FROM genres ORDER BY genre_name")["genre_name"].tolist()
    all_languages = sorted(df["original_language"].dropna().unique())

    c1, c2, c3, c4 = st.columns(4)
    genres = c1.multiselect("Genre", all_genres)
    language = c2.selectbox("Language", ["All"] + all_languages)
    min_rating = c3.slider("Minimum rating", 0.0, 10.0, 0.0, 0.1)
    min_votes = c4.slider("Minimum vote count", 0, int(df["vote_count"].max()), 0)

    # apply the filters
    df = df[(df["vote_average"] >= min_rating) & (df["vote_count"] >= min_votes)]
    if language != "All":
        df = df[df["original_language"] == language]
    if genres:
        df = df[df["genres"].apply(lambda s: any(g in s.split(", ") for g in genres))]
    return df


# =====================================================
# PAGE 1 - FILTERS
# =====================================================
if page == "Filters":
    st.title("Filter Movies")
    filtered = get_filtered_movies()
    st.write(f"**{len(filtered)} movies match your filters**")
    st.dataframe(filtered, width="stretch")


# =====================================================
# PAGE 2 - DASHBOARD
# =====================================================
elif page == "Dashboard":
    st.title("Dashboard")
    filtered = get_filtered_movies()

    if filtered.empty:
        st.warning("No movies match the current filters.")
        st.stop()

    # actors for the filtered movies
    cast = run_query('SELECT movie_id, actor_name FROM "cast"')
    cast = cast[cast["movie_id"].isin(filtered["movie_id"])]

    # one row per (movie, genre)
    genre_rows = filtered.assign(genre=filtered["genres"].str.split(", ")).explode("genre")
    genre_rows = genre_rows[genre_rows["genre"] != ""]

    # KPIs
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Movies", len(filtered))
    k2.metric("Genres Represented", genre_rows["genre"].nunique())
    k3.metric("Total Actors", cast["actor_name"].nunique())
    k4.metric("Average Rating", round(filtered["vote_average"].mean(), 2))

    # Charts row 1
    col1, col2 = st.columns(2)

    top10 = filtered.sort_values("revenue", ascending=False).head(10)
    col1.plotly_chart(
        px.bar(top10, x="revenue", y="title", orientation="h", title="Top 10 Movies by Revenue")
        .update_yaxes(autorange="reversed"),
        width="stretch",
    )

    genre_counts = genre_rows["genre"].value_counts().reset_index()
    genre_counts.columns = ["genre", "movies"]
    col2.plotly_chart(
        px.pie(genre_counts, names="genre", values="movies", hole=0.4, title="Genre Distribution"),
        width="stretch",
    )

    # Chart row 2 (budget/revenue of 0 means "unknown", so leave them out)
    known = filtered[(filtered["budget"] > 0) & (filtered["revenue"] > 0)]
    st.plotly_chart(
        px.scatter(known, x="budget", y="revenue", hover_name="title", title="Budget vs Revenue"),
        width="stretch",
    )

    # Text insight
    best_genre = genre_rows.groupby("genre")["revenue"].mean().idxmax()
    st.info(
        f"In this selection, **{best_genre}** has the highest average revenue. "
        f"The top-grossing movie is **{top10.iloc[0]['title']}**, "
        f"and the average rating is **{filtered['vote_average'].mean():.2f}**."
    )


# =====================================================
# PAGE 3 - QUERY EXPLORER
# =====================================================
else:
    st.title("Query Explorer")

    # each entry: (sql, function that builds the chart from the result dataframe)
    queries = {
        "1. Action movies released after 2015": (
            """
            SELECT m.title, m.release_date
            FROM movies m
            JOIN movie_genres mg ON m.movie_id = mg.movie_id
            JOIN genres g ON mg.genre_id = g.genre_id
            WHERE g.genre_name = 'Action' AND m.release_date > '2015-12-31'
            ORDER BY m.release_date
            """,
            lambda df: px.bar(
                df.assign(year=pd.to_datetime(df["release_date"]).dt.year)["year"].value_counts().sort_index().reset_index(),
                x="year", y="count", title="Action movies per release year",
            ),
        ),
        "2. Top 10 highest-grossing movies with genres": (
            """
            SELECT m.title, m.revenue, STRING_AGG(g.genre_name, ', ') AS genres
            FROM movies m
            JOIN movie_genres mg ON m.movie_id = mg.movie_id
            JOIN genres g ON g.genre_id = mg.genre_id
            GROUP BY m.movie_id, m.title, m.revenue
            ORDER BY m.revenue DESC
            LIMIT 10
            """,
            lambda df: px.bar(df, x="title", y="revenue", hover_data=["genres"], title="Top 10 by revenue"),
        ),
        "3. Average budget & revenue per genre": (
            """
            SELECT g.genre_name, AVG(m.budget) AS avg_budget, AVG(m.revenue) AS avg_revenue
            FROM movies m
            JOIN movie_genres mg ON m.movie_id = mg.movie_id
            JOIN genres g ON mg.genre_id = g.genre_id
            GROUP BY g.genre_name
            ORDER BY avg_revenue DESC
            """,
            lambda df: px.bar(df, x="genre_name", y=["avg_budget", "avg_revenue"], barmode="group",
                              title="Average budget vs revenue by genre"),
        ),
        "4. Top 10 actors by number of movies": (
            """
            SELECT actor_name, COUNT(movie_id) AS total_movies
            FROM "cast"
            GROUP BY actor_name
            ORDER BY total_movies DESC
            LIMIT 10
            """,
            lambda df: px.bar(df, x="actor_name", y="total_movies", title="Most frequent actors"),
        ),
        "5. Directors with more than 3 movies": (
            """
            SELECT person_name, COUNT(DISTINCT movie_id) AS movies_directed
            FROM crew
            WHERE job = 'Director'
            GROUP BY person_name
            HAVING COUNT(DISTINCT movie_id) > 3
            ORDER BY movies_directed DESC
            """,
            lambda df: px.bar(df, x="person_name", y="movies_directed", title="Directors with 4+ movies"),
        ),
        "6. Top 10 most used keywords": (
            """
            SELECT keyword_name, COUNT(*) AS usage_count
            FROM movie_keywords
            GROUP BY keyword_name
            ORDER BY usage_count DESC
            LIMIT 10
            """,
            lambda df: px.bar(df, x="keyword_name", y="usage_count", title="Most used keywords"),
        ),
        "7. High budget but low revenue movies": (
            """
            SELECT title, budget, revenue
            FROM movies
            WHERE budget > (SELECT AVG(budget) FROM movies WHERE budget > 0)
              AND revenue < (SELECT AVG(revenue) FROM movies WHERE revenue > 0)
            ORDER BY budget DESC
            """,
            lambda df: px.scatter(df, x="budget", y="revenue", hover_name="title",
                                  title="Above-average budget, below-average revenue"),
        ),
        "8. Actors who worked with a director": (
            """
            SELECT c.actor_name, COUNT(DISTINCT c.movie_id) AS movies_together
            FROM "cast" c
            JOIN crew cr ON c.movie_id = cr.movie_id
            WHERE cr.job = 'Director' AND cr.person_name = :director
            GROUP BY c.actor_name
            ORDER BY movies_together DESC, c.actor_name
            """,
            lambda df: px.bar(df.head(15), x="actor_name", y="movies_together",
                              title="Actors with the most movies together (top 15)"),
        ),
        "9. Genre with the highest average rating (20+ movies)": (
            """
            SELECT g.genre_name, AVG(m.vote_average) AS avg_rating, COUNT(DISTINCT m.movie_id) AS movie_count
            FROM movies m
            JOIN movie_genres mg ON m.movie_id = mg.movie_id
            JOIN genres g ON mg.genre_id = g.genre_id
            GROUP BY g.genre_name
            HAVING COUNT(DISTINCT m.movie_id) >= 20
            ORDER BY avg_rating DESC
            """,
            lambda df: px.bar(df, x="genre_name", y="avg_rating", title="Average rating by genre"),
        ),
        "10. Top 10 movies with the most keywords": (
            """
            SELECT m.title, COUNT(mk.keyword_id) AS keyword_count
            FROM movies m
            JOIN movie_keywords mk ON m.movie_id = mk.movie_id
            GROUP BY m.movie_id, m.title
            ORDER BY keyword_count DESC
            LIMIT 10
            """,
            lambda df: px.bar(df, x="title", y="keyword_count", title="Movies with the most keywords"),
        ),
    }

    choice = st.selectbox("Choose a query", list(queries.keys()))
    sql, make_chart = queries[choice]

    # Query 8 needs a director name
    params = None
    if choice.startswith("8."):
        director = st.text_input("Director name", "Christopher Nolan")
        params = {"director": director}

    result = run_query(sql, params)

    st.subheader("Result")
    st.dataframe(result, width="stretch")

    st.subheader("Visualization")
    if result.empty:
        st.warning("This query returned no rows.")
    else:
        st.plotly_chart(make_chart(result), width="stretch")