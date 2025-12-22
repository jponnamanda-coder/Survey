import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# ---------------------------
# Database helpers
# ---------------------------
DB_NAME = "survey_app.db"

def get_conn():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # Admin table (simple demo login)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS admins(
        username TEXT PRIMARY KEY,
        password TEXT NOT NULL
    )
    """)

    # Surveys table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS surveys(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        created_at TEXT NOT NULL
    )
    """)

    # Questions table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS questions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        survey_id INTEGER NOT NULL,
        question_text TEXT NOT NULL,
        qtype TEXT NOT NULL, -- text, mcq, rating
        options TEXT,        -- comma-separated for mcq
        FOREIGN KEY(survey_id) REFERENCES surveys(id)
    )
    """)

    # Responses table (1 row = 1 question answered)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS responses(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        survey_id INTEGER NOT NULL,
        question_id INTEGER NOT NULL,
        respondent_name TEXT,
        answer TEXT NOT NULL,
        submitted_at TEXT NOT NULL,
        FOREIGN KEY(survey_id) REFERENCES surveys(id),
        FOREIGN KEY(question_id) REFERENCES questions(id)
    )
    """)

    # Insert default admin if not exists
    cur.execute("SELECT COUNT(*) FROM admins")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO admins(username, password) VALUES(?,?)", ("admin", "admin123"))

    conn.commit()
    conn.close()

def fetch_surveys():
    conn = get_conn()
    df = pd.read_sql_query("SELECT * FROM surveys ORDER BY id DESC", conn)
    conn.close()
    return df

def fetch_questions(survey_id: int):
    conn = get_conn()
    df = pd.read_sql_query(
        "SELECT * FROM questions WHERE survey_id=? ORDER BY id ASC",
        conn,
        params=(survey_id,)
    )
    conn.close()
    return df

def insert_survey(title, description):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO surveys(title, description, created_at) VALUES(?,?,?)",
        (title, description, datetime.now().isoformat(timespec="seconds"))
    )
    conn.commit()
    survey_id = cur.lastrowid
    conn.close()
    return survey_id

def insert_question(survey_id, question_text, qtype, options):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO questions(survey_id, question_text, qtype, options) VALUES(?,?,?,?)",
        (survey_id, question_text, qtype, options)
    )
    conn.commit()
    conn.close()

def insert_response(survey_id, question_id, respondent_name, answer):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO responses(survey_id, question_id, respondent_name, answer, submitted_at)
           VALUES(?,?,?,?,?)""",
        (survey_id, question_id, respondent_name, str(answer), datetime.now().isoformat(timespec="seconds"))
    )
    conn.commit()
    conn.close()

def admin_login(username, password):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM admins WHERE username=? AND password=?", (username, password))
    ok = cur.fetchone() is not None
    conn.close()
    return ok

def fetch_responses(survey_id: int):
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT r.id, r.respondent_name, r.answer, r.submitted_at,
               q.question_text, q.qtype
        FROM responses r
        JOIN questions q ON q.id = r.question_id
        WHERE r.survey_id=?
        ORDER BY r.submitted_at DESC
    """, conn, params=(survey_id,))
    conn.close()
    return df

# ---------------------------
# Streamlit app
# ---------------------------
st.set_page_config(page_title="Feedback & Survey System", page_icon="📝", layout="wide")
init_db()

if "role" not in st.session_state:
    st.session_state.role = "User"  # default role
if "admin_logged_in" not in st.session_state:
    st.session_state.admin_logged_in = False

st.title("📝 Feedback & Survey System (Streamlit + SQLite)")

with st.sidebar:
    st.header("Navigation")
    st.session_state.role = st.radio("Select Mode", ["User", "Admin"], index=0)

# ---------------------------
# USER MODE
# ---------------------------
if st.session_state.role == "User":
    st.subheader("👤 User: Submit Feedback / Survey")

    surveys_df = fetch_surveys()
    if surveys_df.empty:
        st.info("No surveys available yet. Please ask admin to create one.")
    else:
        survey_titles = surveys_df["title"].tolist()
        chosen_title = st.selectbox("Select a Survey", survey_titles)
        chosen_id = int(surveys_df.loc[surveys_df["title"] == chosen_title, "id"].iloc[0])

        st.write("**Description:**", surveys_df.loc[surveys_df["id"] == chosen_id, "description"].iloc[0])

        qdf = fetch_questions(chosen_id)
        if qdf.empty:
            st.warning("This survey has no questions yet.")
        else:
            respondent = st.text_input("Your Name (optional)", "")

            with st.form("survey_form"):
                answers = {}
                for _, q in qdf.iterrows():
                    qid = int(q["id"])
                    qtext = q["question_text"]
                    qtype = q["qtype"]
                    options = (q["options"] or "").strip()

                    st.markdown(f"**Q:** {qtext}")

                    if qtype == "text":
                        answers[qid] = st.text_area("Your answer", key=f"ans_{qid}")
                    elif qtype == "mcq":
                        opts = [o.strip() for o in options.split(",") if o.strip()]
                        if not opts:
                            opts = ["Option 1", "Option 2"]
                        answers[qid] = st.radio("Choose one", opts, key=f"ans_{qid}")
                    elif qtype == "rating":
                        answers[qid] = st.slider("Rate (1-5)", 1, 5, 3, key=f"ans_{qid}")
                    else:
                        answers[qid] = st.text_input("Answer", key=f"ans_{qid}")

                    st.divider()

                submitted = st.form_submit_button("Submit Responses ✅")

            if submitted:
                # Basic validation: ensure no empty answers for text
                empty_text = [qid for qid, ans in answers.items() if (ans is None or str(ans).strip() == "")]
                if empty_text:
                    st.error("Please answer all questions before submitting.")
                else:
                    for qid, ans in answers.items():
                        insert_response(chosen_id, qid, respondent.strip(), ans)
                    st.success("Thank you! Your responses have been submitted.")

# ---------------------------
# ADMIN MODE
# ---------------------------
else:
    st.subheader("🔐 Admin: Create Surveys & View Analytics")

    if not st.session_state.admin_logged_in:
        col1, col2 = st.columns(2)
        with col1:
            username = st.text_input("Admin Username", "admin")
        with col2:
            password = st.text_input("Admin Password", type="password")

        if st.button("Login"):
            if admin_login(username, password):
                st.session_state.admin_logged_in = True
                st.success("Admin login successful.")
                st.rerun()
            else:
                st.error("Invalid credentials. Try admin / admin123")
    else:
        tab1, tab2, tab3 = st.tabs(["➕ Create Survey", "📋 View Responses", "📊 Analytics"])

        # ---- Create Survey
        with tab1:
            st.write("Create a new survey with questions.")
            title = st.text_input("Survey Title")
            desc = st.text_area("Survey Description", "")

            st.markdown("### Add Questions")
            q_count = st.number_input("How many questions?", min_value=1, max_value=20, value=3, step=1)

            question_data = []
            for i in range(int(q_count)):
                st.markdown(f"**Question {i+1}**")
                q_text = st.text_input("Question Text", key=f"qtext_{i}")
                q_type = st.selectbox("Type", ["text", "mcq", "rating"], key=f"qtype_{i}")

                q_opts = ""
                if q_type == "mcq":
                    q_opts = st.text_input("Options (comma-separated)", "Excellent, Good, Average, Poor", key=f"qopts_{i}")

                question_data.append((q_text, q_type, q_opts))
                st.divider()

            if st.button("Create Survey ✅"):
                if not title.strip():
                    st.error("Survey title is required.")
                else:
                    sid = insert_survey(title.strip(), desc.strip())
                    for q_text, q_type, q_opts in question_data:
                        if q_text.strip():
                            insert_question(sid, q_text.strip(), q_type, q_opts.strip())
                    st.success(f"Survey created successfully! (Survey ID: {sid})")

        # ---- View Responses
        with tab2:
            surveys_df = fetch_surveys()
            if surveys_df.empty:
                st.info("No surveys available.")
            else:
                chosen = st.selectbox("Select Survey", surveys_df["title"].tolist(), key="admin_view_survey")
                sid = int(surveys_df.loc[surveys_df["title"] == chosen, "id"].iloc[0])

                rdf = fetch_responses(sid)
                st.write("### Responses")
                if rdf.empty:
                    st.warning("No responses yet for this survey.")
                else:
                    st.dataframe(rdf, use_container_width=True)
                    csv = rdf.to_csv(index=False).encode("utf-8")
                    st.download_button("⬇️ Download CSV", csv, file_name=f"survey_{sid}_responses.csv", mime="text/csv")

        # ---- Analytics
        with tab3:
            surveys_df = fetch_surveys()
            if surveys_df.empty:
                st.info("No surveys available.")
            else:
                chosen = st.selectbox("Select Survey for Analytics", surveys_df["title"].tolist(), key="admin_ana_survey")
                sid = int(surveys_df.loc[surveys_df["title"] == chosen, "id"].iloc[0])

                qdf = fetch_questions(sid)
                rdf = fetch_responses(sid)

                if rdf.empty:
                    st.warning("No responses yet to analyze.")
                else:
                    st.write("### Summary")
                    st.metric("Total Responses (answers)", len(rdf))
                    st.metric("Total Questions", len(qdf))

                    st.write("### Question-wise Analysis")
                    for _, q in qdf.iterrows():
                        qid = int(q["id"])
                        qtext = q["question_text"]
                        qtype = q["qtype"]

                        sub = rdf[rdf["question_text"] == qtext]

                        st.markdown(f"**{qtext}** ({qtype})")
                        if qtype == "rating":
                            # rating average
                            sub_num = pd.to_numeric(sub["answer"], errors="coerce").dropna()
                            if len(sub_num) > 0:
                                st.write(f"Average Rating: **{sub_num.mean():.2f} / 5**")
                                st.bar_chart(sub_num.value_counts().sort_index())
                            else:
                                st.write("No valid ratings yet.")
                        elif qtype == "mcq":
                            st.bar_chart(sub["answer"].value_counts())
                        else:
                            # text answers
                            st.dataframe(sub[["respondent_name", "answer", "submitted_at"]], use_container_width=True)

                        st.divider()

        if st.button("Logout"):
            st.session_state.admin_logged_in = False
            st.rerun()
