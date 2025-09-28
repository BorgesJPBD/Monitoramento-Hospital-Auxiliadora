# app.py (APENAS FLASK)
from flask import Flask, request, jsonify, session, redirect, url_for
import os
from datetime import timedelta

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.secret_key = os.getenv("FLASK_SECRET", "troque_essa_chave")
app.permanent_session_lifetime = timedelta(hours=8)

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "0906Jp04##")
USER_PASSWORD  = os.getenv("USER_PASSWORD", "user123")
USERS = {
    "Admin":   {"name": "Administrador", "password": ADMIN_PASSWORD, "role": "admin"},
    "usuario": {"name": "Usuário",       "password": USER_PASSWORD,  "role": "viewer"},
}

@app.route("/")
def login_page():
    return app.send_static_file("index.html")

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    user = (data.get("username") or "").strip()
    pwd  = (data.get("password") or "")
    if user in USERS and pwd == USERS[user]["password"]:
        session.permanent = True
        session["user"] = {"username": user, "name": USERS[user]["name"], "role": USERS[user]["role"]}
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "Credenciais inválidas."}), 401

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login_page"))
    host = request.host.split(":")[0]  # usa o mesmo IP que você acessou o login
    return redirect(f"http://{host}:8501")

@app.route("/healthz")
def healthz():
    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
