import os
from uuid import uuid4

from flask import Blueprint, request, jsonify, render_template
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

from .rag_engine import (
    upload_pdf_to_storage,
    index_pdf_from_storage_path,
    get_retriever,
    get_qa_chain,
    ask_question,
)

# Optional helper if you implemented it in rag_engine.py
try:
    from .rag_engine import delete_storage_paths  # noqa: F401
except Exception:
    delete_storage_paths = None  # type: ignore

from .models import User, ChatLog, Document, ChatSession
from flask_mail import Message
from app.utils import db, mail
import random
import string

routes = Blueprint("routes", __name__)

ALLOWED_EXTENSIONS = {"pdf"}

# We no longer use a local user_vectors cache (pgvector persists)
user_chains = {}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# --------------------- Auth Routes ---------------------
@routes.route("/signup", methods=["GET"])
def show_signup():
    return render_template("signup.html")


@routes.route("/signup", methods=["POST"])
def process_signup():
    data = request.json or {}
    required_fields = ["first_name", "last_name", "email", "password"]

    if not all(data.get(field) for field in required_fields):
        return jsonify({"error": "All fields are required."}), 400

    if User.query.filter_by(email=data["email"]).first():
        return jsonify({"error": "Email already registered."}), 409

    user = User(
        first_name=data["first_name"].strip(),
        last_name=data["last_name"].strip(),
        email=data["email"].strip().lower(),
        password=generate_password_hash(data["password"]),
    )
    db.session.add(user)
    db.session.commit()
    return jsonify({"message": "Signup successful"})


@routes.route("/login", methods=["GET"])
def show_login():
    return render_template("login.html")


@routes.route("/login", methods=["POST"])
def process_login():
    data = request.json or {}
    email = (data.get("email") or "").strip().lower()
    password = (data.get("password") or "").strip()

    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password, password):
        return jsonify({"error": "Invalid email or password."}), 401

    login_user(user)
    return jsonify({"message": "Login successful", "user_id": user.id})


@routes.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return jsonify({"message": "Logged out"})


@routes.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "GET":
        return render_template("forgot-password.html")

    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    if not email:
        return jsonify({"error": "Email is required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "Enter a valid registered email address"}), 404

    new_password = "".join(random.choices(string.ascii_letters + string.digits, k=6))

    try:
        msg = Message(
            subject="Your New RAG Assistant Password",
            recipients=[email],
            body=(
                f"Hello {user.first_name},\n\n"
                f"Your new temporary password is: {new_password}\n\n"
                f"Please log in and change your password from the profile menu.\n\n— RAG Assistant"
            ),
        )
        mail.send(msg)

        user.password = generate_password_hash(new_password)
        db.session.commit()
        return jsonify({"message": "Password sent successfully"})
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")
        return jsonify({"error": "Failed to send email. Please try again later."}), 500


# ---------------- Edit Profile Info ----------------
@routes.route("/profile-info", methods=["GET"])
@login_required
def get_profile_info():
    return jsonify({"first_name": current_user.first_name, "last_name": current_user.last_name})


@routes.route("/edit-profile", methods=["GET", "POST"])
@login_required
def edit_profile():
    if request.method == "GET":
        return render_template("edit-profile.html", user=current_user)

    data = request.get_json() or {}
    first = (data.get("first_name") or "").strip()
    last = (data.get("last_name") or "").strip()

    if not first or not last:
        return jsonify({"error": "First and last name are required."}), 400

    if not all(c.isalpha() or c == "." for c in first):
        return jsonify({"error": "First name contains invalid characters."}), 400
    if not all(c.isalpha() or c == "." for c in last):
        return jsonify({"error": "Last name contains invalid characters."}), 400

    current_user.first_name = first
    current_user.last_name = last
    db.session.commit()
    return jsonify({"message": "Profile updated successfully."})


# --------- change-password ---------------
@routes.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "GET":
        return render_template("change-password.html")

    data = request.json or {}
    old_password = (data.get("old_password") or "").strip()
    new_password = (data.get("new_password") or "").strip()

    if not old_password or not new_password:
        return jsonify({"error": "Both old and new passwords are required"}), 400

    user = User.query.get(current_user.id)
    if not check_password_hash(user.password, old_password):
        return jsonify({"error": "Incorrect current password"}), 400
    if len(new_password) < 6:
        return jsonify({"error": "New password must be at least 6 characters"}), 400

    user.password = generate_password_hash(new_password)
    db.session.commit()
    return jsonify({"message": "Password updated successfully"})


# --------------------- Session Management ---------------------
@routes.route("/session", methods=["POST"])
@login_required
def create_session():
    data = request.json or {}
    title = data.get("title", "New Chat")
    session_obj = ChatSession(user_id=current_user.id, title=title)
    db.session.add(session_obj)
    db.session.commit()
    return jsonify({"session_id": session_obj.id, "title": session_obj.title})


@routes.route("/sessions", methods=["GET"])
@login_required
def list_sessions():
    sessions = (
        ChatSession.query.filter_by(user_id=current_user.id)
        .order_by(ChatSession.created_at.desc())
        .all()
    )
    return jsonify([{"id": s.id, "title": s.title, "created_at": s.created_at.isoformat()} for s in sessions])


@routes.route("/session/<int:session_id>", methods=["DELETE"])
@login_required
def delete_session(session_id):
    session_to_delete = ChatSession.query.filter_by(id=session_id, user_id=current_user.id).first()
    if not session_to_delete:
        return jsonify({"error": "Session not found"}), 404

    # Delete chat logs
    ChatLog.query.filter_by(session_id=session_id).delete()

    # Delete PDFs for this session (Storage) and DB Document rows
    try:
        from .rag_engine import delete_storage_for_session, delete_embeddings_namespace

        # Files live under <owner>/<session_namespace>
        owner_id = str(current_user.id)
        session_namespace = str(session_id)

        removed = delete_storage_for_session(owner_id, session_namespace)
        print(f"[DELETE] Removed {removed} storage objects for user {owner_id}, session {session_id}")

        # Remove vector embeddings/collection for this session
        deleted_coll = delete_embeddings_namespace(session_namespace)
        print(f"[DELETE] Embedding collection deleted? {deleted_coll}")

        # Remove Document rows that pointed to those files
        Document.query.filter_by(user_id=current_user.id, session_id=session_id).delete()
    except Exception as e:
        print(f"[DELETE] Error cleaning storage/embeddings: {e}")

    # Remove session + cached chain
    db.session.delete(session_to_delete)
    db.session.commit()
    user_chains.pop((current_user.id, session_id), None)

    return jsonify({"message": "Session and its contents deleted"})

@routes.route("/session/<int:session_id>", methods=["PUT"])
@login_required
def rename_session(session_id):
    data = request.json or {}
    new_title = (data.get("title") or "").strip()
    if not new_title:
        return jsonify({"error": "Title is required"}), 400

    session_obj = ChatSession.query.filter_by(id=session_id, user_id=current_user.id).first()
    if not session_obj:
        return jsonify({"error": "Session not found"}), 404

    session_obj.title = new_title
    db.session.commit()
    return jsonify({"message": "Title updated", "title": new_title})


# --------------------- File Upload ---------------------
@routes.route("/upload", methods=["POST"])
def upload_file():
    try:
        guest_id = request.form.get("guest_id")
        user_id = current_user.id if current_user.is_authenticated else guest_id or "guest"

        raw_session_id = request.form.get("session_id")

        # Normalize session id for guests / users
        if not current_user.is_authenticated:
            session_id = f"{user_id}_session"
        else:
            try:
                session_id = int(raw_session_id) if raw_session_id is not None else None
            except (TypeError, ValueError):
                session_id = None

        files = request.files.getlist("file")
        if not files:
            return jsonify({"error": "No file provided"}), 400

        uploaded_storage_paths = []
        uploaded_filenames = []

        # Upload to Supabase Storage + create Document rows (logged-in users)
        for file in files:
            if not file or not allowed_file(file.filename):
                continue

            # display name only (for logs/UI); storage will add a unique prefix
            display_name = secure_filename(file.filename) or "document.pdf"

            # >>> key change: include session subfolder <<<
            storage_path = upload_pdf_to_storage(file, str(user_id), subdir=str(session_id))
            uploaded_storage_paths.append(storage_path)
            uploaded_filenames.append(display_name)

            if isinstance(user_id, int) and session_id is not None:
                # reuse 'filename' column to store the storage path
                doc = Document(user_id=user_id, session_id=session_id, filename=storage_path)
                db.session.add(doc)

        if not uploaded_storage_paths:
            return jsonify({"error": "No valid PDFs"}), 400

        if isinstance(user_id, int):
            db.session.commit()
            if session_id is None:
                new_title = f"New Chat ({uploaded_filenames[0]})"
                new_session = ChatSession(user_id=user_id, title=new_title)
                db.session.add(new_session)
                db.session.commit()
                session_id = new_session.id

            # Log uploaded file names
            for filename in uploaded_filenames:
                log = ChatLog(user_id=user_id, session_id=session_id, question="", answer=f"🗂 Uploaded File: {filename}")
                db.session.add(log)
            db.session.commit()

            # Index each PDF into pgvector
            for storage_path in uploaded_storage_paths:
                index_pdf_from_storage_path(
                    storage_path,
                    owner_id=str(user_id),
                    title=os.path.basename(storage_path),
                    namespace=str(session_id),
                )
            # Do NOT build LLM chain here; /ask will build on first question

        else:
            # Guest flow
            for storage_path in uploaded_storage_paths:
                index_pdf_from_storage_path(
                    storage_path,
                    owner_id=str(user_id),
                    title=os.path.basename(storage_path),
                    namespace=str(session_id),
                )
            # Do not build chain here; /ask will build on first question

        print(f"[UPLOAD] user_id: {user_id}, session_id: {session_id}")
        print(f"[UPLOAD] uploaded: {uploaded_filenames}")
        return jsonify({"message": "Documents uploaded and indexed successfully", "session_id": session_id})

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"[UPLOAD ERROR] {type(e).__name__}: {e}\n{tb}")
        return jsonify({"error": f"{type(e).__name__}: {str(e)}"}), 500


# --------------------- Ask ---------------------
@routes.route("/ask", methods=["POST"])
def ask():
    data = request.json or {}
    query = (data.get("question") or "").strip()
    session_id = data.get("session_id")

    if not query:
        return jsonify({"error": "No question provided"}), 400

    guest_id = request.headers.get("X-Guest-ID")
    user_id = current_user.id if current_user.is_authenticated else guest_id or "guest"
    print(f"[ASK] Guest ID: {guest_id}, user_id: {user_id}, session_id: {session_id}")

    if not current_user.is_authenticated:
        session_id = f"{user_id}_session"
    else:
        try:
            session_id = int(session_id)
        except (TypeError, ValueError):
            session_id = None

    # Build chain on demand
    if current_user.is_authenticated:
        qa_chain = user_chains.get((user_id, session_id))
        if not qa_chain:
            print(f"[ASK] Building chain for user {user_id}, session {session_id}")
            retriever = get_retriever(k=6, namespace=str(session_id))
            qa_chain = get_qa_chain(retriever)
            user_chains[(user_id, session_id)] = qa_chain
    else:
        qa_chain = user_chains.get(session_id)
        if not qa_chain:
            print(f"[ASK] Building guest chain for session {session_id}")
            retriever = get_retriever(k=6, namespace=str(session_id))
            qa_chain = get_qa_chain(retriever)
            user_chains[session_id] = qa_chain

    if not qa_chain:
        return jsonify({"error": "No documents indexed for this session"}), 400

    try:
        answer = ask_question(qa_chain, query)

        if isinstance(user_id, int) and session_id is not None:
            log = ChatLog(user_id=user_id, session_id=session_id, question=query, answer=answer)
            db.session.add(log)
            db.session.commit()

        return jsonify({"answer": answer})
    except Exception as e:
        print(f"[ASK ERROR] {e}")
        return jsonify({"error": str(e)}), 500


# --------------------- History ---------------------
@routes.route("/history/<int:session_id>", methods=["GET"])
@login_required
def session_history(session_id):
    logs = (
        ChatLog.query.filter_by(user_id=current_user.id, session_id=session_id)
        .order_by(ChatLog.timestamp)
        .all()
    )
    return jsonify([{"question": log.question, "answer": log.answer, "time": log.timestamp.isoformat()} for log in logs])


# --------------------- Reload Chains ---------------------
@routes.route("/reload_chains", methods=["POST"])
@login_required
def reload_chains():
    """
    For stability, we DON'T build LLM chains here (to avoid failing the route).
    We just clear caches so /ask will rebuild on-demand.
    """
    user_id = current_user.id
    sessions = ChatSession.query.filter_by(user_id=user_id).all()

    for session in sessions:
        user_chains.pop((user_id, session.id), None)

    return jsonify({"message": "Chain caches cleared; they will rebuild on next question"})


# --------------------- Guest Cleanup ---------------------
@routes.route("/cleanup_guest", methods=["POST"])
def cleanup_guest():
    import json
    data = json.loads(request.data) if request.data else {}
    guest_id = data.get("guest_id")
    if not guest_id:
        return jsonify({"error": "Missing guest ID"}), 400

    # Remove in-memory chain
    user_chains.pop(guest_id, None)

    # Remove Storage files and embeddings for this guest's session namespace
    try:
        from .rag_engine import delete_storage_for_session, delete_embeddings_namespace
        owner_id = str(guest_id)
        session_namespace = f"{guest_id}_session"

        removed = delete_storage_for_session(owner_id, session_namespace)
        deleted_coll = delete_embeddings_namespace(session_namespace)
        print(f"[GUEST CLEANUP] removed={removed}, collection_deleted={deleted_coll}")
    except Exception as e:
        print(f"[GUEST CLEANUP ERROR] {e}")

    return jsonify({"message": f"Guest {guest_id} cleaned up"})