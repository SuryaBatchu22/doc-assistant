# DOC Assistant - RAG Assistant (Retrieval-Augmented Generation)

An intelligent assistant web app built with Flask, LangChain, and Groq to answer questions from uploaded PDF documents using Large Language Models (LLMs). Supports guest and user modes, session chat history, profile editing, and secure login with password recovery.

---

## Features

-  Upload PDFs and ask questions contextually.
-  Registered and Guest users supported.
-  Sessions saved for logged-in users.
-  Email/password login with forgot password.
-  Edit profile and change password options.
-  LangChain + HuggingFace embeddings + Groq API.
-  Voice input and stylish, responsive UI.

---

##  Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/your-username/doc-assistant.git
cd doc-assistant
```

### 2. Create and activate virtual environment

```bash
python -m venv rag_venv
source rag_venv/bin/activate  # On Windows: rag_venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Setup environment variables

Create a `.env` file in the root with:

```
SECRET_KEY=your_flask_secret_key
MAIL_USERNAME=your_email@gmail.com
MAIL_PASSWORD=your_app_password
```

---

##  Project Structure

```
rag_webapp/
│
├── app/
│   ├── models.py
│   ├── routes.py
│   ├── rag_engine.py
│   ├── utils.py
│   └── ...
│
├── static/
│   ├── style.css
│   ├── auth.css
│   └── scripts.js
│
├── templates/
│   ├── index.html
│   ├── login.html
│   ├── signup.html
│   ├── forgot-password.html
│   ├── edit-profile.html
│   └── change-password.html
│
├── main.py
├── requirements.txt
├── .env
├── .gitignore
└── README.md
```

---

##  Email Setup

Enable 2FA for your Google account and generate an **App Password**.

Use that in `.env` as `MAIL_PASSWORD`.

---

##  Running the App

```bash
python main.py
```

Visit: `http://127.0.0.1:5000`

---

##  Security Tips

- Never commit `.env` file.
- Use hashed passwords (Flask-Login + Werkzeug).
- Limit file types to `.pdf`.

---

## License

This project is licensed under the [MIT License](LICENSE).  
© 2025 Surya Batchu. You are free to use, modify, and distribute this project with proper credit.

