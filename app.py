import os
import uuid
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from email.message import EmailMessage
import smtplib

# Firebase
import firebase_admin
from firebase_admin import credentials, db

# Load env vars from .env
load_dotenv()

# ------------------ CONFIG ------------------
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
FIREBASE_DB_URL = os.getenv("FIREBASE_DB_URL")
SERVICE_ACCOUNT_PATH = os.getenv("SERVICE_ACCOUNT_PATH")  # path to serviceAccount.json

if not all([EMAIL_USER, EMAIL_PASSWORD, FIREBASE_DB_URL, SERVICE_ACCOUNT_PATH]):
    raise ValueError("Missing one or more required environment variables.")

# ------------------ APP SETUP ------------------
app = Flask(__name__)
app.secret_key = SECRET_KEY

# Firebase init
cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
firebase_admin.initialize_app(cred, {
    'databaseURL': FIREBASE_DB_URL
})

# ------------------ HELPERS ------------------
def email_to_key(email: str) -> str:
    return email.replace('.', ',').lower()

def get_users_ref():
    return db.reference("users")

def get_users_by_email_ref():
    return db.reference("users_by_email")

def get_iop_logs_ref(uid: str):
    return db.reference(f"iop_logs/{uid}")

# ------------------ USER FUNCTIONS ------------------
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
        "created_at": datetime.utcnow().isoformat() + "Z"
    }
    get_users_ref().child(uid).set(user_obj)
    map_ref.set(uid)
    return uid

def get_user_by_email(email: str):
    email_key = email_to_key(email)
    uid = get_users_by_email_ref().child(email_key).get()
    return get_users_ref().child(uid).get() if uid else None

# ------------------ IOP LOG FUNCTIONS ------------------
def insert_iop_log(uid: str, iop: float, blue_light: float = None, screen_time: float = None, device_id: str = None):
    now = datetime.utcnow()
    log_id = str(uuid.uuid4())
    log_obj = {
        "id": log_id,
        "user_id": uid,
        "iop": float(iop) if iop is not None else None,
        "blue_light": float(blue_light) if blue_light is not None else None,
        "screen_time": float(screen_time) if screen_time is not None else None,
        "device_id": device_id or "",
        "timestamp_iso": now.isoformat() + "Z",
        "timestamp_epoch": int(now.timestamp())
    }
    get_iop_logs_ref(uid).child(log_id).set(log_obj)
    return log_obj

def get_latest_logs(uid: str, limit=10):
    snapshot = get_iop_logs_ref(uid).order_by_child("timestamp_epoch").limit_to_last(limit).get()
    logs = list(snapshot.values()) if snapshot else []
    logs.sort(key=lambda r: r.get("timestamp_epoch", 0))
    return logs

def get_latest_log(uid: str):
    logs = get_latest_logs(uid, limit=1)
    return logs[-1] if logs else None

# ------------------ EMAIL OTP ------------------
def send_email_otp(to_email):
    otp = ''.join(str(random.randint(0, 9)) for _ in range(6))
    msg = EmailMessage()
    msg['Subject'] = 'Your OTP Code'
    msg['From'] = EMAIL_USER
    msg['To'] = to_email
    msg.set_content(f'Your OTP is: {otp}')
    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as smtp:
            smtp.starttls()
            smtp.login(EMAIL_USER, EMAIL_PASSWORD)
            smtp.send_message(msg)
        print(f"OTP sent to {to_email}. OTP was: {otp}")
        return otp
    except Exception as e:
        print("Failed to send OTP:", e)
        return None

# ------------------ ROUTES ------------------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        if not email:
            flash("Email is required!", "danger")
            return redirect(url_for('login'))
        otp = send_email_otp(email)
        if not otp:
            flash("Failed to send OTP. Try again later.", "danger")
            return redirect(url_for('login'))
        session['otp'] = otp
        session['otp_expiry'] = (datetime.utcnow() + timedelta(minutes=5)).timestamp()
        session['email'] = email
        create_user_if_not_exists(email)
        flash("OTP sent to your email.", "info")
        return redirect(url_for('verify_otp'))
    return render_template('login.html')

@app.route('/verify_otp', methods=['GET', 'POST'])
def verify_otp():
    if request.method == 'POST':
        entered = request.form['otp'].strip()
        if datetime.utcnow().timestamp() > session.get('otp_expiry', 0):
            flash("OTP expired. Please login again.", "warning")
            return redirect(url_for('login'))
        if entered == session.get('otp'):
            user = get_user_by_email(session['email']) or create_user_if_not_exists(session['email'])
            session['authenticated'] = True
            flash("Login successful!", "success")
            return redirect(url_for('dashboard'))
        flash("Incorrect OTP.", "danger")
        return redirect(url_for('verify_otp'))
    return render_template('verify_otp.html')

@app.route('/dashboard')
def dashboard():
    if not session.get('authenticated'):
        return redirect(url_for('login'))
    user = get_user_by_email(session['email'])
    rows = get_latest_logs(user['id'], limit=10)
    latest = rows[-1] if rows else None
    alerts = []
    if latest:
        if latest.get('iop', 0) > 21:
            alerts.append("High IOP detected! Consult a doctor.")
        if latest.get('blue_light', 0) > 25:
            alerts.append("High blue light exposure. Take a break!")
        if latest.get('screen_time', 0) > 5:
            alerts.append("Reduce screen time to prevent eye strain.")
    timestamps = [datetime.fromisoformat(r.get('timestamp_iso').replace("Z", "")).strftime('%H:%M') for r in rows]
    return render_template("dashboard.html",
                           data=latest,
                           alerts=alerts,
                           iop={"values": [r.get('iop') for r in rows], "timestamps": timestamps},
                           blue_light={"values": [r.get('blue_light') for r in rows], "timestamps": timestamps},
                           screen_time={"values": [r.get('screen_time') for r in rows], "timestamps": timestamps})

@app.route('/send_data', methods=['POST'])
def send_data():
    data = request.get_json()
    email = data.get('email')
    if not email or data.get('iop') is None:
        return jsonify({'status': 'error', 'msg': 'Missing required data'}), 400
    user = get_user_by_email(email)
    if not user:
        return jsonify({'status': 'error', 'msg': 'User not found'}), 404
    inserted = insert_iop_log(user['id'], data['iop'], data.get('blue_light'), data.get('screen_time'), data.get('device_id'))
    return jsonify({'status': 'success', 'msg': 'Data stored', 'data': inserted})

@app.route('/api/latest_data')
def latest_data():
    email = session.get('email')
    user = get_user_by_email(email) if email else None
    return jsonify(get_latest_log(user['id']) if user else {})

# ------------------ MAIN ------------------
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
