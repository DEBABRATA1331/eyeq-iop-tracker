# app.py — Option A (Website reads /eyeq_data)
# - Keeps your OTP login + users mapping
# - Reads live values from /eyeq_data
# - Reads history (if available) from /eyeq_data_history (optional)
# - /send_data now writes to /eyeq_data and appends to /eyeq_data_history for testing

import os
import json
import uuid
import random
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage

from dotenv import load_dotenv
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify
)

# Firebase Admin SDK (server-side)
import firebase_admin
from firebase_admin import credentials, db

# ------------------ ENV & CONFIG ------------------
load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")  # Gmail App Password recommended
FIREBASE_DB_URL = os.getenv("FIREBASE_DB_URL")
FIREBASE_CREDENTIALS = os.getenv("FIREBASE_CREDENTIALS")  # JSON string (preferred)
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")  # file path fallback

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
app.secret_key = SECRET_KEY

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
    return email.replace('.', ',').lower()

def get_users_ref():
    return db.reference("users")

def get_users_by_email_ref():
    return db.reference("users_by_email")

def get_eyeq_data_ref():
    """Current live snapshot the Pi writes to."""
    return db.reference("eyeq_data")

def get_eyeq_history_ref():
    """Optional history stream (this app will read if it exists; /send_data writes to it)."""
    return db.reference("eyeq_data_history")

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

# ------------------ EYEQ DATA READ/WRITE ------------------
def coerce_float(v, default=None):
    try:
        if v is None or v == "":
            return default
        return float(v)
    except Exception:
        return default

def fetch_eyeq_data():
    """
    Returns the current live dict at /eyeq_data, normalized with expected keys:
    iop, blue_light, screen_time, blink_rate, iop_status, blue_level, blue_lux, timestamp_iso, timestamp_epoch
    """
    raw = get_eyeq_data_ref().get() or {}
    # Known keys from your Pi payloads: blink_count, blue_level, blue_lux, iop/iop_value, iop_status, timestamp
    iop_val = raw.get("iop") or raw.get("iop_value")
    ts_iso = raw.get("timestamp") or raw.get("timestamp_iso")
    # Normalize timestamp_epoch
    try:
        ts_epoch = int(datetime.fromisoformat(ts_iso.replace("Z", "")).timestamp()) if ts_iso else None
    except Exception:
        ts_epoch = None

    normalized = {
        "iop": coerce_float(iop_val),
        "blue_light": coerce_float(raw.get("blue_lux")),  # treat blue_lux as numeric blue light level
        "screen_time": coerce_float(raw.get("screen_time")),  # only if you ever set it
        "blink_rate": coerce_float(raw.get("blink_rate")),    # only if you ever set it
        "blink_count": int(raw.get("blink_count") or 0),
        "iop_status": raw.get("iop_status") or raw.get("status") or "--",
        "blue_level": raw.get("blue_level") or "Unknown",
        "blue_lux": coerce_float(raw.get("blue_lux")),
        "timestamp_iso": ts_iso or "",
        "timestamp_epoch": ts_epoch,
        # passthroughs
        "device_id": raw.get("device_id") or "",
    }
    return normalized

def fetch_eyeq_history(limit=50, start_epoch=None, end_epoch=None):
    """
    Reads /eyeq_data_history ordered by timestamp_epoch.
    If your Pi doesn’t write this node, you’ll simply get [].
    """
    ref = get_eyeq_history_ref()
    q = ref.order_by_child("timestamp_epoch")
    if start_epoch is not None and end_epoch is not None:
        snap = q.start_at(start_epoch).end_at(end_epoch).get()
    else:
        snap = q.limit_to_last(limit).get()
    if not snap:
        return []

    rows = list(snap.values())
    rows.sort(key=lambda r: r.get("timestamp_epoch", 0))
    # Coerce expected numeric fields
    for r in rows:
        r["iop"] = coerce_float(r.get("iop"))
        r["blue_light"] = coerce_float(r.get("blue_light"))
        r["screen_time"] = coerce_float(r.get("screen_time"))
        r["blink_rate"] = coerce_float(r.get("blink_rate"))
    return rows

def append_eyeq_history(row: dict):
    """Append one item into /eyeq_data_history with a generated id."""
    log_id = row.get("id") or str(uuid.uuid4())
    get_eyeq_history_ref().child(log_id).set({**row, "id": log_id})
    return log_id

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

    # Read the live snapshot directly from /eyeq_data
    latest = fetch_eyeq_data()

    # Also try to get a short tail from history if it exists (optional)
    rows = fetch_eyeq_history(limit=10)
    # If history is empty, build a minimal single-point series from latest (if any)
    if not rows and latest and latest.get("timestamp_epoch"):
        rows = [latest]

    # Build series for charts
    iop_values = [r.get("iop") for r in rows]
    blue_values = [r.get("blue_light") for r in rows]
    screen_values = [r.get("screen_time") for r in rows]
    blink_values = [r.get("blink_rate") for r in rows]

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

    alerts = []
    if latest:
        if latest.get("iop") is not None and latest["iop"] > 21:
            alerts.append("High IOP detected! Consult a doctor.")
        if latest.get("blue_light") is not None and latest["blue_light"] > 25:
            alerts.append("High blue light exposure. Take a break!")
        if latest.get("screen_time") is not None and latest["screen_time"] > 5:
            alerts.append("Reduce screen time to prevent eye strain.")
        if latest.get("blink_rate") is not None and latest["blink_rate"] < 15:
            alerts.append("Low blink rate detected — you might be straining your eyes.")

    return render_template(
        "dashboard.html",
        data=latest or {},
        alerts=alerts,
        iop={"values": iop_values, "timestamps": timestamps},
        blue_light={"values": blue_values, "timestamps": timestamps},
        screen_time={"values": screen_values, "timestamps": timestamps},
        blink_rate={"values": blink_values, "timestamps": timestamps}
    )

@app.route("/history")
def history():
    if not session.get("authenticated"):
        return redirect(url_for("login"))

    # Date range (optional)
    start = request.args.get("start")
    end = request.args.get("end")
    try:
        start_date = datetime.strptime(start, "%Y-%m-%d") if start else datetime.utcnow() - timedelta(days=7)
        end_date = datetime.strptime(end, "%Y-%m-%d") if end else datetime.utcnow()
    except Exception:
        start_date = datetime.utcnow() - timedelta(days=7)
        end_date = datetime.utcnow()

    start_epoch = int(start_date.timestamp())
    end_epoch = int(end_date.timestamp())

    logs = fetch_eyeq_history(start_epoch=start_epoch, end_epoch=end_epoch)

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

    # Use last 10 historical points if available; otherwise, include latest only
    rows = fetch_eyeq_history(limit=10)
    latest = fetch_eyeq_data()
    if not rows and latest and latest.get("timestamp_epoch"):
        rows = [latest]

    iop_values, blue_values, screen_values, blink_values, timestamps = [], [], [], [], []

    for r in rows:
        iop_values.append(r.get("iop"))
        blue_values.append(r.get("blue_light"))
        screen_values.append(r.get("screen_time"))
        blink_values.append(r.get("blink_rate"))

        t_iso = r.get("timestamp_iso")
        if t_iso:
            try:
                ts = datetime.fromisoformat(t_iso.replace("Z", ""))
                timestamps.append(ts.strftime("%Y-%m-%d %H:%M"))
            except Exception:
                timestamps.append("")
        else:
            timestamps.append("")

    latest_row = rows[-1] if rows else (latest or {})

    alerts = []
    if latest_row:
        if latest_row.get("iop") is not None and latest_row["iop"] > 21:
            alerts.append("High IOP detected. Please consult a doctor.")
        if latest_row.get("blue_light") is not None and latest_row["blue_light"] > 25:
            alerts.append("High blue light exposure. Consider reducing screen brightness or using protective eyewear.")
        if latest_row.get("screen_time") is not None and latest_row["screen_time"] > 5:
            alerts.append("Long screen time detected. Take regular breaks.")
        br = latest_row.get("blink_rate")
        if br is not None:
            if br < 8:
                alerts.append("Very low blink rate detected — risk of dry eyes.")
            elif br < 15:
                alerts.append("Low blink rate detected — try following the 20-20-20 rule.")

    # Optional: show user name if present
    email = session.get("email")
    user = get_user_by_email(email) if email else None
    patient_name = session.get("patient_name") or (user.get("name", "") if user else "")

    return render_template(
        "report.html",
        data=latest_row or {},
        alerts=alerts,
        report_date=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        patient_name=patient_name,
        iop={"values": iop_values, "timestamps": timestamps},
        blue_light={"values": blue_values, "timestamps": timestamps},
        screen_time={"values": screen_values, "timestamps": timestamps},
        blink_rate={"values": blink_values, "timestamps": timestamps},
    )

@app.route("/set_patient_name", methods=["POST"])
def set_patient_name():
    if not session.get("authenticated"):
        return jsonify({"ok": False, "msg": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    name = (data.get("patient_name") or "").strip()
    session["patient_name"] = name
    return jsonify({"ok": True, "patient_name": name})

@app.route("/hospitals")
def hospitals():
    if not session.get("authenticated"):
        return redirect(url_for("login"))
    return render_template("hospitals.html")

# -------- Optional: test ingestion endpoint (writes to /eyeq_data + /eyeq_data_history) --------
@app.route("/send_data", methods=["POST"])
def send_data():
    data = request.get_json() or {}

    # Accept any subset; coerce as needed
    iop = coerce_float(data.get("iop"))
    blue_light = coerce_float(data.get("blue_light") or data.get("blue_lux"))
    screen_time = coerce_float(data.get("screen_time"))
    blink_rate = coerce_float(data.get("blink_rate"))
    iop_status = data.get("iop_status") or data.get("status") or "--"
    blue_level = data.get("blue_level") or "Unknown"
    device_id = data.get("device_id") or ""

    now = datetime.utcnow()
    epoch = int(now.timestamp())
    ts_iso = now.isoformat() + "Z"
    log_id = str(uuid.uuid4())

    # Compose normalized row
    row = {
        "id": log_id,
        "iop": iop,
        "blue_light": blue_light,
        "screen_time": screen_time,
        "blink_rate": blink_rate,
        "iop_status": iop_status,
        "blue_level": blue_level,
        "blue_lux": blue_light,
        "device_id": device_id,
        "timestamp_iso": ts_iso,
        "timestamp_epoch": epoch,
    }

    # Set live snapshot
    get_eyeq_data_ref().set(row)
    # Append to history (so history/report have data)
    append_eyeq_history(row)

    return jsonify({"status": "success", "msg": "Data stored", "data": row})

@app.route("/api/latest_data")
def latest_data():
    row = fetch_eyeq_data()
    return jsonify(row or {})

# ------------------ MAIN ------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
