from flask import Flask, render_template, request, redirect, session, jsonify
import os
import json
import subprocess
import threading
import zipfile
import py7zr
import shutil
from datetime import datetime

app = Flask(__name__)
app.secret_key = "avi-vps-hosting_secret_key_2026"

CONFIG_FILE = "config.json"
UPLOAD_FOLDER = "uploads"

running_processes = {}

# AUTO CREATE

if not os.path.exists(CONFIG_FILE):

    with open(CONFIG_FILE, "w") as f:

        json.dump({
            "maintenance": False,
            "users": {}
        }, f, indent=4)

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# LOAD CONFIG

def load_config():

    with open(CONFIG_FILE, "r") as f:
        return json.load(f)

# SAVE CONFIG

def save_config(data):

    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=4)

# HOME

@app.route("/")
def home():

    return render_template("index.html")

# LOGIN

@app.route("/login", methods=["POST"])
def login():

    username = request.form.get("username")
    password = request.form.get("password")

    data = load_config()

    if username not in data["users"]:
        return "Invalid Username"

    user = data["users"][username]

    if user["password"] != password:
        return "Wrong Password"

    if user["banned"]:
        return "User Banned"

    expire = datetime.strptime(user["expire"], "%Y-%m-%d")

    if datetime.now() > expire:
        return "Server Expired"

    session["user"] = username

    return redirect("/dashboard")

# DASHBOARD

@app.route("/dashboard")
def dashboard():

    if "user" not in session:
        return redirect("/")

    username = session["user"]

    return render_template(
        "dashboard.html",
        username=username
    )

# LOGOUT

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/")

# ADMIN PANEL

@app.route("/zrxadmin", methods=["GET", "POST"])
def admin():

    data = load_config()

    # ADMIN LOGIN

    if request.method == "POST":

        action = request.form.get("action")

        # LOGIN

        if action == "admin_login":

            email = request.form.get("email")
            password = request.form.get("password")

            if email == "admin@avi.com" and password == "admin123":

                session["admin"] = True

        # CREATE USER

        elif action == "create_user":

            if not session.get("admin"):
                return "Unauthorized"

            username = request.form.get("username")
            password = request.form.get("password")
            expire = request.form.get("expire")

            data["users"][username] = {

                "password": password,
                "expire": expire,
                "banned": False,
                "main_file": "bot.py",
                "requirements": "requirements.txt"
            }

            save_config(data)

            # USER FOLDER

            user_folder = os.path.join(
                UPLOAD_FOLDER,
                username
            )

            os.makedirs(user_folder, exist_ok=True)

        # BAN USER

        elif action == "ban_user":

            username = request.form.get("username")

            data["users"][username]["banned"] = True

            save_config(data)

        # UNBAN USER

        elif action == "unban_user":

            username = request.form.get("username")

            data["users"][username]["banned"] = False

            save_config(data)

    return render_template(
        "admin.html",
        users=data["users"],
        admin=session.get("admin")
    )

# FILE UPLOAD

@app.route("/upload", methods=["POST"])
def upload():

    if "user" not in session:
        return redirect("/")

    username = session["user"]

    user_folder = os.path.join(
        UPLOAD_FOLDER,
        username
    )

    file = request.files["file"]

    path = os.path.join(
        user_folder,
        file.filename
    )

    file.save(path)

    # ZIP EXTRACT

    if file.filename.endswith(".zip"):

        with zipfile.ZipFile(path, "r") as zip_ref:

            zip_ref.extractall(user_folder)

        os.remove(path)

    # 7Z EXTRACT

    if file.filename.endswith(".7z"):

        with py7zr.SevenZipFile(path, mode="r") as z:

            z.extractall(path=user_folder)

        os.remove(path)

    return redirect("/dashboard")

# START BOT

@app.route("/start")
def start_bot():

    if "user" not in session:
        return redirect("/")

    username = session["user"]

    data = load_config()

    user = data["users"][username]

    main_file = user["main_file"]

    user_folder = os.path.join(
        UPLOAD_FOLDER,
        username
    )

    path = os.path.join(
        user_folder,
        main_file
    )

    if not os.path.exists(path):
        return "Main File Not Found"

    process = subprocess.Popen(

        ["python", path],

        cwd=user_folder,

        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True

    )

    running_processes[username] = process

    return redirect("/dashboard")

# STOP BOT

@app.route("/stop")
def stop_bot():

    if "user" not in session:
        return redirect("/")

    username = session["user"]

    process = running_processes.get(username)

    if process:
        process.kill()

    return redirect("/dashboard")

# RESTART BOT

@app.route("/restart")
def restart_bot():

    if "user" not in session:
        return redirect("/")

    username = session["user"]

    process = running_processes.get(username)

    if process:
        process.kill()

    return redirect("/start")

# FILE LIST

@app.route("/files")
def files():

    if "user" not in session:
        return redirect("/")

    username = session["user"]

    user_folder = os.path.join(
        UPLOAD_FOLDER,
        username
    )

    files = os.listdir(user_folder)

    return jsonify(files)

# DELETE FILE

@app.route("/delete_file", methods=["POST"])
def delete_file():

    if "user" not in session:
        return redirect("/")

    username = session["user"]

    filename = request.form.get("filename")

    path = os.path.join(
        UPLOAD_FOLDER,
        username,
        filename
    )

    if os.path.isfile(path):

        os.remove(path)

    elif os.path.isdir(path):

        shutil.rmtree(path)

    return redirect("/dashboard")

# CREATE FOLDER

@app.route("/create_folder", methods=["POST"])
def create_folder():

    if "user" not in session:
        return redirect("/")

    username = session["user"]

    folder = request.form.get("folder")

    path = os.path.join(
        UPLOAD_FOLDER,
        username,
        folder
    )

    os.makedirs(path, exist_ok=True)

    return redirect("/dashboard")

# CREATE FILE

@app.route("/create_file", methods=["POST"])
def create_file():

    if "user" not in session:
        return redirect("/")

    username = session["user"]

    filename = request.form.get("filename")

    path = os.path.join(
        UPLOAD_FOLDER,
        username,
        filename
    )

    with open(path, "w") as f:
        f.write("")

    return redirect("/dashboard")

# RUN

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )