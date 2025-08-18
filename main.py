import os
from flask import Flask, render_template, redirect, url_for
from dotenv import load_dotenv
from app.utils import db, mail, login_manager
from app.models import User

# Load environment variables
load_dotenv()

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY")

# --- DB: prefer DATABASE_URL (Postgres), else fallback to SQLite ---
db_url = os.getenv("DATABASE_URL")
if db_url and db_url.startswith("postgres://"):
    # Some providers give old scheme; SQLAlchemy expects postgresql://
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url or 'sqlite:///db.sqlite3'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_size": 3,
    "max_overflow": 0,
    "pool_pre_ping": True,
    "pool_recycle": 1800,
}


# Mail config
app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_USERNAME")

# Initialize all extensions
db.init_app(app)
mail.init_app(app)
login_manager.init_app(app)
login_manager.login_view = "routes.show_login"

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

from app.routes import routes
app.register_blueprint(routes)

@app.route("/")
def index():
    return redirect(url_for("routes.show_login"))

@app.route("/chat")
def chat():
    return render_template("index.html")

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True, use_reloader=False)
