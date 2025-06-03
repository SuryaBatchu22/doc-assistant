import os
from flask import Flask, render_template, redirect, url_for
from dotenv import load_dotenv
from app.utils import db, mail, login_manager
from app.models import User

# Load environment variables
load_dotenv()

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY")
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite3'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

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
    app.run(debug=True)
