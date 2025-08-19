# DOC Assistant — Retrieval‑Augmented PDF Assistant

This is a small web app that lets you chat with your PDFs. You upload one or more files, the app finds the most relevant passages, and a fast Groq model writes an answer that stays grounded in your documents. It supports guests and registered users, keeps session history for people who sign in, and runs well on a free Render service.

## What you can use it for

* Study and revision: drop in lecture notes or chapters and ask focused questions.
* Reports and manuals: query long PDFs like policies, product manuals, or research.
* Portfolio piece: deploy it and show an end‑to‑end RAG system (auth, storage, database, vector search, LLM, deployment).
* Lightweight team knowledge base: persistent sessions for users, quick trials for guests.

## Core features

* Contextual Q\&A over PDFs (vector retrieval + LLM answer)
* User and guest modes

  * Logged‑in: sessions, chat history, and uploaded docs persist
  * Guest: temporary sessions that clean up on exit
* Email/password sign‑in with “forgot password” via a Gmail App Password
* Persistent storage

  * Supabase Storage for the raw PDFs
  * Supabase Postgres with pgvector for embeddings (one collection per session)
* Built for stability and performance on free hosting

  * Remote Hugging Face Endpoint embeddings (low memory usage on Render)
  * Groq llama3‑8b‑8192 as the LLM
  * Retries and timeouts for flaky networks; the frontend handles non‑JSON 502/504 responses
  * Sanitizes NUL bytes in odd PDFs to prevent database errors
* Responsive UI with optional voice input

## What changed compared to the original README

* Database moved from local SQLite to Supabase Postgres with pgvector for durable storage and scalable vector search.
* Files moved off local disk to Supabase Storage (a `pdfs` bucket).
* Embeddings run on Hugging Face’s hosted endpoint to avoid memory spikes on free hosts.
* Added stability measures: retrying embeddings, LLM timeouts, better frontend error handling, and a NUL‑byte cleaner.
* Deployment instructions tuned for Render Free (gunicorn, health check, low concurrency).

## Tech at a glance

Flask, SQLAlchemy, Flask‑Login, Flask‑Mail.
LangChain, Groq, Supabase Postgres (pgvector), Supabase Storage.
Hugging Face Endpoint embeddings, pypdf, Gunicorn, Tenacity.

---

## Environment variables

Create a `.env` file in the project root:

```
# Flask
SECRET_KEY=your_flask_secret_key

# Mail (Gmail App Password)
MAIL_USERNAME=your_email@gmail.com
MAIL_PASSWORD=your_gmail_app_password

# Groq
GROQ_API_KEY=your_groq_key

# Hugging Face (remote embeddings)
HUGGINGFACEHUB_API_TOKEN=hf_xxx
EMBED_BACKEND=hf_inference
EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2

# Supabase
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_SERVICE_ROLE=your_service_role_key
PDF_BUCKET=pdfs

# Postgres (Supabase Transaction Pooler)
DATABASE_URL=postgresql://USER:PASSWORD@aws-1-...pooler.supabase.com:6543/postgres
```

Use the Transaction Pooler connection for web apps, not the Session Pooler.

---

## Set up and run locally

```bash
git clone https://github.com/your-username/doc-assistant.git
cd doc-assistant

python -m venv rag_venv
# macOS/Linux
source rag_venv/bin/activate
# Windows
.\rag_venv\Scripts\activate

pip install --upgrade pip
pip install -r requirements.txt

python main.py
```

Now open `http://127.0.0.1:5000` in your browser.

---

## Supabase setup (once)

1. Create a project and note your SUPABASE\_URL and a Service Role key.
2. In Storage, create a bucket named `pdfs`.
3. In Database, copy the Transaction Pooler connection string and put it in `DATABASE_URL`.

---

## Deploy on Render (Free)

* Build command:
  `pip install --upgrade pip && pip install -r requirements.txt`
* Start command:
  `gunicorn --bind 0.0.0.0:$PORT main:app`
* Health check path: `/healthz`
* Environment variables: same values you use locally
* Optional stability settings:

  ```
  WEB_CONCURRENCY=1
  GUNICORN_CMD_ARGS=--workers 1 --threads 2 --timeout 120
  ```

---

## Project structure

```
rag_webapp/
├─ app/
│  ├─ models.py          # SQLAlchemy models: User, Document, ChatSession, ChatLog
│  ├─ routes.py          # Auth, upload, ask, sessions, history, cleanup
│  ├─ rag_engine.py      # Supabase Storage, pgvector, embeddings, QA chain, text sanitizers
│  └─ utils.py           # db, mail, login_manager setup
│
├─ static/
│  ├─ style.css
│  ├─ auth.css
│  └─ scripts.js         # network guards, guest handling, UI logic
│
├─ templates/
│  ├─ index.html
│  ├─ login.html
│  ├─ signup.html
│  ├─ forgot-password.html
│  ├─ edit-profile.html
│  └─ change-password.html
│
├─ main.py               # Flask app, blueprint register, /healthz, db.create_all
├─ requirements.txt
├─ .env                  # local only, never commit
├─ .gitignore
└─ README.md
```

---

## Quick troubleshooting

* 502/504 from Render or “Unexpected token '<' … not valid JSON” in the console: the platform returned an HTML error page. The frontend already guards this; retry the question and check that `/healthz` returns `ok`.
* Supabase error `MaxClientsInSessionMode`: switch your `DATABASE_URL` to the Transaction Pooler connection.
* Upload fails with “NUL (0x00) characters”: some PDFs contain hidden NUL bytes. The app removes them before inserting text; update to the latest code and redeploy if you still see this.

---

## License

This project is licensed under the [MIT License](LICENSE).  
© 2025 Surya Batchu. You are free to use, modify, and distribute this project with proper credit.

