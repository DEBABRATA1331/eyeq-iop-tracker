# app.py (env-only, no secrets in code)

import os
import json
import uuid
import random
import smtplib
from datetime import datetime, timedelta

from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from email.message import EmailMessage

# Firebase
import firebase_admin
from firebase_admin import credentials, db

# ------------------ ENV & CONFIG ------------------
load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")  # Gmail App Password recommended
FIREBASE_DB_URL = os.getenv("FIREBASE_DB_URL")
FIREBASE_CREDENTIALS = os.getenv("FIREBASE_CREDENTIALS")  # JSON string (preferred)
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")  # fallback path

missing = [k for k, v in {
    "SECRET_KEY": SECRET_KEY,
    "EMAIL_USER": EMAIL_USER,
    "EMAIL_PASSWORD": EMAIL_PASSWORD,
    "FIREBASE_DB_URL": FIREBASE_DB_URL
}.items() if not v]
if missing:
    raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

# ------------------ FLASK APP ------------------
app = Flask(__name__)
app.secret_key = SECRET_KEY  # stable key so sessions survive restarts

# ------------------ FIREBASE INIT ------------------
if not firebase_admin._apps:
    if FIREBASE_CREDENTIALS:
        try:
            cred_obj = credentials.Certificate(json.loads(FIREBASE_CREDENTIALS))
        except json.JSONDecodeError as e:
            raise ValueError("FIREBASE_CREDENTIALS is not valid JSON. Paste the full service-account JSON string.") from e
        firebase_admin.initialize_app(cred_obj, {"databaseURL": FIREBASE_DB_URL})
    elif GOOGLE_APPLICATION_CREDENTIALS and os.path.exists(GOOGLE_APPLICATION_CREDENTIALS):
        cred_obj = credentials.Certificate(GOOGLE_APPLICATION_CREDENTIALS)
        firebase_admin.initialize_app(cred_obj, {"databaseURL": FIREBASE_DB_URL})
    else:
        raise ValueError(
            "Provide Firebase credentials via FIREBASE_CREDENTIALS (JSON string) "
            "or GOOGLE_APPLICATION_CREDENTIALS (file path)."
        )

# ------------------ DB HELPERS ------------------
def email_to_key(email: str) -> str:
    # For users_by_email mapping keys
    return email.replace('.', ',').lower()

def get_users_ref():
    return db.reference("users")

def get_users_by_email_ref():
    return db.reference("users_by_email")

def get_iop_logs_ref(uid: str):
    return db.reference(f"iop_logs/{uid}")

def get_reports_ref(uid: str):
    return db.reference(f"reports/{uid}")

def get_alerts_ref(uid: str):
    return db.reference(f"alerts/{uid}")

def get_devices_ref(uid: str):
    return db.reference(f"devices/{uid}")

def get_activity_logs_ref(uid: str):
    return db.reference(f"activity_logs/{uid}")

# ------------------ USERS ------------------
def create_user_if_not_exists(email: str, name: str = None) -> str:
    email_key = email_to_key(email)
    map_ref = get_users_by_email_ref().child(email_key)
    uid = map_ref.get()
    if uid:
        return uid

    uid = str(uuid.uuid4())
    user_obj = {
        "id": uid,
        "email": email,
        "name": name or "",
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    get_users_ref().child(uid).set(user_obj)
    map_ref.set(uid)
    return uid

def get_user_by_email(email: str):
    email_key = email_to_key(email)
    uid = get_users_by_email_ref().child(email_key).get()
    if not uid:
        return None
    return get_users_ref().child(uid).get()

# ------------------ IOP LOGS ------------------
def insert_iop_log(uid: str, iop: float, blue_light: float = None, screen_time: float = None, device_id: str = None):
    now = datetime.utcnow()
    epoch = int(now.timestamp())
    log_id = str(uuid.uuid4())
    log_obj = {
        "id": log_id,
        "user_id": uid,
        "iop": float(iop) if iop is not None else None,
        "blue_light": float(blue_light) if blue_light is not None else None,
        "screen_time": float(screen_time) if screen_time is not None else None,
        "device_id": device_id or "",
        "timestamp_iso": now.isoformat() + "Z",
        "timestamp_epoch": epoch,
    }
    get_iop_logs_ref(uid).child(log_id).set(log_obj)
    return log_obj

def get_latest_logs(uid: str, limit=10):
    ref = get_iop_logs_ref(uid)
    snapshot = ref.order_by_child("timestamp_epoch").limit_to_last(limit).get()
    if not snapshot:
        return []
    logs = list(snapshot.values())
    logs.sort(key=lambda r: r.get("timestamp_epoch", 0))
    return logs

def get_logs_between(uid: str, start_epoch: int, end_epoch: int):
    ref = get_iop_logs_ref(uid)
    snapshot = ref.order_by_child("timestamp_epoch").start_at(start_epoch).end_at(end_epoch).get()
    if not snapshot:
        return []
    logs = list(snapshot.values())
    logs.sort(key=lambda r: r.get("timestamp_epoch", 0), reverse=True)
    return logs

def get_latest_log(uid: str):
    logs = get_latest_logs(uid, limit=1)
    return logs[-1] if logs else None

# ------------------ EMAIL OTP ------------------
def send_email_otp(to_email):
    otp = ''.join(str(random.randint(0, 9)) for _ in range(6))

    msg = EmailMessage()
    msg["Subject"] = "Your OTP Code"
    msg["From"] = EMAIL_USER
    msg["To"] = to_email
    msg.set_content(f"Your OTP is: {otp}")

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
            smtp.starttls()
            smtp.login(EMAIL_USER, EMAIL_PASSWORD)
            smtp.send_message(msg)
        print(f"OTP sent to {to_email}. OTP was: {otp}")
        return otp
    except Exception as e:
        print("Failed to send OTP:", e)
        return None

# ------------------ ROUTES ------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        if not email:
            flash("Email is required!", "danger")
            return redirect(url_for("login"))

        otp = send_email_otp(email)
        if not otp:
            flash("Failed to send OTP. Try again later.", "danger")
            return redirect(url_for("login"))

        session["otp"] = otp
        session["otp_expiry"] = (datetime.utcnow() + timedelta(minutes=5)).timestamp()
        session["email"] = email

        create_user_if_not_exists(email)

        flash("OTP sent to your email.", "info")
        return redirect(url_for("verify_otp"))
    return render_template("login.html")

@app.route("/verify_otp", methods=["GET", "POST"])
def verify_otp():
    if request.method == "POST":
        entered = request.form["otp"].strip()
        correct = session.get("otp")
        expiry = session.get("otp_expiry")

        if not expiry or datetime.utcnow().timestamp() > expiry:
            flash("OTP expired. Please login again.", "warning")
            return redirect(url_for("login"))

        if entered == correct:
            email = session["email"]
            user = get_user_by_email(email)
            if not user:
                uid = create_user_if_not_exists(email)
                user = get_users_ref().child(uid).get()

            session["authenticated"] = True
            flash("Login successful!", "success")
            return redirect(url_for("dashboard"))

        flash("Incorrect OTP.", "danger")
        return redirect(url_for("verify_otp"))
    return render_template("verify_otp.html")

@app.route("/resend_otp")
def resend_otp():
    if not session.get("email"):
        flash("Session expired. Please login again.", "warning")
        return redirect(url_for("login"))

    new_otp = send_email_otp(session["email"])
    if new_otp:
        session["otp"] = new_otp
        session["otp_expiry"] = (datetime.utcnow() + timedelta(minutes=5)).timestamp()
        flash("OTP resent to your email.", "info")
    else:
        flash("Failed to resend OTP.", "danger")
    return redirect(url_for("verify_otp"))

@app.route("/dashboard")
def dashboard():
    if not session.get("authenticated"):
        return redirect(url_for("login"))

    email = session["email"]
    user = get_user_by_email(email)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("login"))

    user_id = user["id"]
    rows = get_latest_logs(user_id, limit=10)

    iop_values = [r.get("iop") for r in rows]
    blue_values = [r.get("blue_light") for r in rows]
    screen_values = [r.get("screen_time") for r in rows]
    timestamps = []
    for r in rows:
        t_iso = r.get("timestamp_iso")
        if t_iso:
            try:
                ts = datetime.fromisoformat(t_iso.replace("Z", ""))
                timestamps.append(ts.strftime("%H:%M"))
            except Exception:
                timestamps.append("")
        else:
            timestamps.append("")

    latest = rows[-1] if rows else None

    alerts = []
    if latest:
        if latest.get("iop") is not None and latest["iop"] > 21:
            alerts.append("High IOP detected! Consult a doctor.")
        if latest.get("blue_light") is not None and latest["blue_light"] > 25:
            alerts.append("High blue light exposure. Take a break!")
        if latest.get("screen_time") is not None and latest["screen_time"] > 5:
            alerts.append("Reduce screen time to prevent eye strain.")

    return render_template(
        "dashboard.html",
        data=latest,
        alerts=alerts,
        iop={"values": iop_values, "timestamps": timestamps},
        blue_light={"values": blue_values, "timestamps": timestamps},
        screen_time={"values": screen_values, "timestamps": timestamps},
    )

@app.route("/history")
def history():
    if not session.get("authenticated"):
        return redirect(url_for("login"))

    email = session["email"]
    start = request.args.get("start")
    end = request.args.get("end")

    try:
        start_date = datetime.strptime(start, "%Y-%m-%d") if start else datetime.utcnow() - timedelta(days=7)
        end_date = datetime.strptime(end, "%Y-%m-%d") if end else datetime.utcnow()
    except Exception:
        start_date = datetime.utcnow() - timedelta(days=7)
        end_date = datetime.utcnow()

    user = get_user_by_email(email)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("login"))

    user_id = user["id"]
    start_epoch = int(start_date.timestamp())
    end_epoch = int(end_date.timestamp())

    logs = get_logs_between(user_id, start_epoch, end_epoch)

    return render_template(
        "history.html",
        logs=logs,
        start=start_date.strftime("%Y-%m-%d"),
        end=end_date.strftime("%Y-%m-%d"),
    )

@app.route("/report")
def report():
    if not session.get("authenticated"):
        return redirect(url_for("login"))

    email = session["email"]
    user = get_user_by_email(email)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("login"))

    user_id = user["id"]
    rows = get_latest_logs(user_id, limit=10)
    iop_values = [r.get("iop") for r in rows]
    timestamps = []
    for r in rows:
        t_iso = r.get("timestamp_iso")
        if t_iso:
            try:
                ts = datetime.fromisoformat(t_iso.replace("Z", ""))
                timestamps.append(ts.strftime("%H:%M"))
            except Exception:
                timestamps.append("")
        else:
            timestamps.append("")

    latest = rows[-1] if rows else None

    alerts = []
    if latest:
        if latest.get("iop") is not None and latest["iop"] > 21:
            alerts.append("High IOP detected! Consult a doctor.")
        if latest.get("blue_light") is not None and latest["blue_light"] > 25:
            alerts.append("High blue light exposure. Take a break!")
        if latest.get("screen_time") is not None and latest["screen_time"] > 5:
            alerts.append("Reduce screen time to prevent eye strain.")

    return render_template(
        "report.html",
        data=latest,
        alerts=alerts,
        iop={"values": iop_values, "timestamps": timestamps},
    )

@app.route("/hospitals")
def hospitals():
    if not session.get("authenticated"):
        return redirect(url_for("login"))
    return render_template("hospitals.html")

@app.route("/send_data", methods=["POST"])
def send_data():
    data = request.get_json()
    email = data.get("email")
    iop = data.get("iop")
    blue_light = data.get("blue_light")
    screen_time = data.get("screen_time")
    device_id = data.get("device_id")

    if not email or iop is None:
        return jsonify({"status": "error", "msg": "Missing required data"}), 400

    user = get_user_by_email(email)
    if not user:
        return jsonify({"status": "error", "msg": "User not found"}), 404

    user_id = user["id"]
    inserted = insert_iop_log(user_id, iop, blue_light, screen_time, device_id)
    return jsonify({"status": "success", "msg": "Data stored", "data": inserted})

@app.route("/api/latest_data")
def latest_data():
    email = session.get("email")
    if not email:
        return jsonify({})
    user = get_user_by_email(email)
    if not user:
        return jsonify({})
    user_id = user["id"]
    row = get_latest_log(user_id)
    return jsonify(row or {})

# ------------------ MAIN ------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
