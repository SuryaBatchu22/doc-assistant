import os
from flask import Blueprint, request, jsonify, session, render_template
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from .rag_engine import load_documents, build_vector_index, get_qa_chain, ask_question
from .models import User, ChatLog, Document, ChatSession
from flask_mail import Message
from app.utils import db, mail
import random
import string


routes = Blueprint("routes", __name__)

UPLOAD_FOLDER = os.path.join(os.getcwd(), "uploads")
ALLOWED_EXTENSIONS = {'pdf'}

user_vectors = {}
user_chains = {}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --------------------- Auth Routes ---------------------
@routes.route("/signup", methods=["GET"])
def show_signup():
    return render_template("signup.html")

@routes.route("/signup", methods=["POST"])
def process_signup():
    data = request.json
    required_fields = ["first_name", "last_name", "email", "password"]

    # Validate presence of all required fields
    if not all(data.get(field) for field in required_fields):
        return jsonify({"error": "All fields are required."}), 400

    # Check for existing email
    if User.query.filter_by(email=data["email"]).first():
        return jsonify({"error": "Email already registered."}), 409

    # Hash password and create new user
    user = User(
        first_name=data["first_name"],
        last_name=data["last_name"],
        email=data["email"],
        password=generate_password_hash(data["password"])
    )
    db.session.add(user)
    db.session.commit()

    return jsonify({"message": "Signup successful"})


@routes.route("/login", methods=["GET"])
def show_login():
    return render_template("login.html")

@routes.route("/login", methods=["POST"])
def process_login():
    data = request.json
    email = data.get("email")
    password = data.get("password")

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

    data = request.get_json()
    email = data.get("email", "").strip().lower()

    if not email:
        return jsonify({"error": "Email is required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "Enter a valid registered email address"}), 404

    # Generate a random 6-character password
    new_password = ''.join(random.choices(string.ascii_letters + string.digits, k=6))

    try:
        # Send email with new password
        msg = Message(
            subject="Your New RAG Assistant Password",
            recipients=[email],
            body=f"Hello {user.first_name},\n\nYour new temporary password is: {new_password}\n\nPlease log in and change your password from the profile menu.\n\n— RAG Assistant"
        )
        mail.send(msg)
        print(f"[EMAIL] Password sent to {email}")

        # Update user password in database
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
    return jsonify({
        "first_name": current_user.first_name,
        "last_name": current_user.last_name
    })

@routes.route("/edit-profile", methods=["GET", "POST"])
@login_required
def edit_profile():
    if request.method == "GET":
        return render_template("edit-profile.html", user=current_user)
    

    data = request.get_json()
    first = data.get("first_name", "").strip()
    last = data.get("last_name", "").strip()

    if not first or not last:
        return jsonify({"error": "First and last name are required."}), 400

    if not all(c.isalpha() or c == '.' for c in first):
        return jsonify({"error": "First name contains invalid characters."}), 400
    if not all(c.isalpha() or c == '.' for c in last):
        return jsonify({"error": "Last name contains invalid characters."}), 400

    current_user.first_name = first
    current_user.last_name = last
    db.session.commit()
    return jsonify({"message": "Profile updated successfully."})

#---------change-password---------------
@routes.route("/change-password", methods=["GET","POST"])
@login_required
def change_password():
    if request.method == "GET":
        return render_template("change-password.html")

    data = request.json
    old_password = data.get("old_password", "").strip()
    new_password = data.get("new_password", "").strip()

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
    data = request.json
    title = data.get("title", "New Chat")
    session_obj = ChatSession(user_id=current_user.id, title=title)
    db.session.add(session_obj)
    db.session.commit()
    return jsonify({"session_id": session_obj.id, "title": session_obj.title})

@routes.route("/sessions", methods=["GET"])
@login_required
def list_sessions():
    sessions = ChatSession.query.filter_by(user_id=current_user.id).order_by(ChatSession.created_at.desc()).all()
    return jsonify([
        {"id": s.id, "title": s.title, "created_at": s.created_at.isoformat()}
        for s in sessions
    ])

@routes.route("/session/<int:session_id>", methods=["DELETE"])
@login_required
def delete_session(session_id):
    session_to_delete = ChatSession.query.filter_by(id=session_id, user_id=current_user.id).first()
    if not session_to_delete:
        return jsonify({"error": "Session not found"}), 404

    ChatLog.query.filter_by(session_id=session_id).delete()

    user_id = current_user.id
    upload_dir = os.path.join(UPLOAD_FOLDER, str(user_id))
    try:
        documents = Document.query.filter_by(user_id=user_id, session_id=session_id).all()
        for doc in documents:
            file_path = os.path.join(upload_dir, doc.filename)
            if os.path.exists(file_path):
                os.remove(file_path)
        Document.query.filter_by(user_id=user_id, session_id=session_id).delete()
    except Exception as e:
        print(f"[DELETE] Error deleting uploaded files: {e}")

    db.session.delete(session_to_delete)
    db.session.commit()
    user_vectors.pop((user_id, session_id), None)
    user_chains.pop((user_id, session_id), None)

    return jsonify({"message": "Session and its contents deleted"})

@routes.route("/session/<int:session_id>", methods=["PUT"])
@login_required
def rename_session(session_id):
    data = request.json
    new_title = data.get("title", "").strip()
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
    guest_id = request.form.get("guest_id")
    user_id = current_user.id if current_user.is_authenticated else guest_id or "guest"
    
    # Ensure unique session ID for guest
    if not current_user.is_authenticated:
        session_id = f"{user_id}_session"


    session_id = request.form.get("session_id")

    try:
        session_id = int(session_id)
    except (TypeError, ValueError):
        session_id = None

    files = request.files.getlist("file")
    if not files:
        return jsonify({"error": "No file provided"}), 400

    session_folder = os.path.join(UPLOAD_FOLDER, str(user_id))
    os.makedirs(session_folder, exist_ok=True)

    all_docs = []
    uploaded_filenames = []

    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            path = os.path.join(session_folder, filename)
            file.save(path)
            all_docs.extend(load_documents([path]))
            uploaded_filenames.append(filename)

            if isinstance(user_id, int) and session_id is not None:
                 doc = Document(user_id=user_id, session_id=session_id, filename=filename)
                 db.session.add(doc)


    if not all_docs:
        return jsonify({"error": "No valid PDFs"}), 400

    if isinstance(user_id, int):  # only for real users
        db.session.commit()
        if session_id is None:
            new_title = f"New Chat ({uploaded_filenames[0]})"
            new_session = ChatSession(user_id=user_id, title=new_title)
            db.session.add(new_session)
            db.session.commit()
            session_id = new_session.id
        for filename in uploaded_filenames:
            log = ChatLog(
                user_id=user_id,
                session_id=session_id,
                question="",
                answer=f"🗂 Uploaded File: {filename}"
            )
            db.session.add(log)
        db.session.commit()
        user_vectors[(user_id, session_id)] = build_vector_index(all_docs, namespace=session_id)
        user_chains[(user_id, session_id)] = get_qa_chain(user_vectors[(user_id, session_id)])
    else:
        session_id = session_id or f"{user_id}_session"
        vector_store = build_vector_index(all_docs, namespace=session_id)
        qa_chain = get_qa_chain(vector_store)
        user_vectors[session_id] = vector_store
        user_chains[session_id] = qa_chain

    print(f"[UPLOAD] user_id: {user_id}, session_id: {session_id}")
    print(f"[UPLOAD] user_chains keys: {list(user_chains.keys())}")

    return jsonify({
        "message": "Documents uploaded and indexed successfully",
        "session_id": session_id
    })

# --------------------- Ask ---------------------
@routes.route("/ask", methods=["POST"])
def ask():
    data = request.json
    query = data.get("question", "").strip()
    session_id = data.get("session_id")

    if not query:
        return jsonify({"error": "No question provided"}), 400

    guest_id = request.headers.get("X-Guest-ID")
    user_id = current_user.id if current_user.is_authenticated else guest_id or "guest"
    print(f"[ASK] Guest ID: {guest_id}, user_id: {user_id}, session_id: {session_id}")
    print(f"[ASK] user_chains keys: {list(user_chains.keys())}")


    if not current_user.is_authenticated:
        session_id = f"{user_id}_session"
    else:
        try:
            session_id = int(session_id)
        except (TypeError, ValueError):
            session_id = None


    if current_user.is_authenticated:
        qa_chain = user_chains.get((user_id, session_id))
        if not qa_chain:
            print(f"[ASK] Rebuilding chain for user {user_id}, session {session_id}")
            documents = Document.query.filter_by(user_id=user_id, session_id=session_id).all()
            if not documents:
                return jsonify({"error": "No relevant documents found. Please upload any PDF to proceed."}), 400
            doc_paths = [os.path.join(UPLOAD_FOLDER, str(user_id), doc.filename) for doc in documents]
            all_docs = load_documents(doc_paths)
            if not all_docs:
                return jsonify({"error": "Failed to load stored documents. Please re-upload."}), 400
            vector_store = build_vector_index(all_docs)
            qa_chain = get_qa_chain(vector_store)
            user_chains[(user_id, session_id)] = qa_chain
    else:
        qa_chain = user_chains.get(session_id)


    if not qa_chain:
        return jsonify({"error": "No documents indexed for this session"}), 400

    try:
        answer = ask_question(qa_chain, query)

        if isinstance(user_id, int) and session_id is not None:
            log = ChatLog(
                user_id=user_id,
                session_id=session_id,
                question=query,
                answer=answer
            )
            db.session.add(log)
            db.session.commit()

        return jsonify({"answer": answer})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --------------------- History ---------------------
@routes.route("/history/<int:session_id>", methods=["GET"])
@login_required
def session_history(session_id):
    logs = ChatLog.query.filter_by(user_id=current_user.id, session_id=session_id).order_by(ChatLog.timestamp).all()
    return jsonify([
        {"question": log.question, "answer": log.answer, "time": log.timestamp.isoformat()}
        for log in logs
    ])

# --------------------- Reload Chains ---------------------
@routes.route("/reload_chains", methods=["POST"])
@login_required
def reload_chains():
    if not current_user.is_authenticated:
        return jsonify({"message": "Guest mode — skipping chain reload"})

    user_id = current_user.id
    sessions = ChatSession.query.filter_by(user_id=user_id).all()

    for session in sessions:
        documents = Document.query.filter_by(user_id=user_id, session_id=session.id).all()
        paths = [os.path.join(UPLOAD_FOLDER, str(user_id), doc.filename) for doc in documents]
        docs = load_documents(paths)
        if docs:
            vector = build_vector_index(docs)
            chain = get_qa_chain(vector)
            user_chains[(user_id, session.id)] = chain

    return jsonify({"message": "Chains reloaded"})

@routes.route("/cleanup_guest", methods=["POST"])
def cleanup_guest():
    import json
    if request.data:
        data = json.loads(request.data)
        guest_id = data.get("guest_id")
    else:
        guest_id = None

    if not guest_id:
        return jsonify({"error": "Missing guest ID"}), 400

    # ✅ Remove memory
    user_vectors.pop(guest_id, None)
    user_chains.pop(guest_id, None)

    # ✅ Delete uploaded files
    guest_folder = os.path.join(UPLOAD_FOLDER, guest_id)
    if os.path.exists(guest_folder):
        for file in os.listdir(guest_folder):
            try:
                os.remove(os.path.join(guest_folder, file))
            except Exception as e:
                print(f"[CLEANUP FILE ERROR] {e}")
        try:
            os.rmdir(guest_folder)
        except Exception as e:
            print(f"[CLEANUP DIR ERROR] {e}")

    print(f"[CLEANUP] Removed guest: {guest_id}")
    return jsonify({"message": f"Guest {guest_id} cleaned up"})

