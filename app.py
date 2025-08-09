import os
import uuid
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from email.message import EmailMessage
import smtplib
import urllib.parse as up

# Firebase
import firebase_admin
from firebase_admin import credentials, db

load_dotenv()
app = Flask(__name__)
app.secret_key = os.urandom(24)

service_account_info = {
   "type": "service_account",
  "project_id": "eyeq-7e199",
  "private_key_id": "1d8c08fd5bbd82147344216048a493b1fd8d0807",
  "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC3XBPFGRVydr1w\nJhcfZa1iWe0iEHHnmsUJmhkR2mQxqFreOJzMUGpOIezbdleCjDgKgtgXORXeUMFS\njDp9kpuy0Gf52VwzxHkPcIjUqnZKXxSnxz2lvsBAL+EemTgnkexzMLQv6KS8anJe\nH/7LeA82ghmBLCyPh6VYDf96C1JfExzaA3DQ76GdtABKGJH+xPK5Gp4wM6wGwCF2\n4ygjFoDHV9zrN8TaQjCGTU/Mvp7aoswIGHSTaeS47REJtQE5v+AR2EoItD8/JoVH\niqiRznA9Y7OlNAkwxDN87iGTohj19uqHNX+rZslbh0KTfXHlvtVV0LuBFL5jWBu1\nIZW8DtzFAgMBAAECggEABdZuILPMPYEvRc9IpCzCCOQRCykX30ZLqKMZ0jowP257\nOiD2SQD0aXlmB5Ssc5EQRbFlvNOJ8TKD/SNOx2mwAFDnRoqXh2RlcErmaFLnAjYl\nu7O5sDmy+DguBCHfqk7YhtBRpEbVW9RNwNZm78ZqQZOByV2FK6qnZnbHn/SVUkaF\nEVIeeJ7hdvosESIQzbGJIteZzrpzrGlfDOViDFEOcgbbwktlDNrG7afC6c5P/MuA\ngyr66RDK1+yb2qWm2s1eVbqYG0Kc9Sp3Fa5SruSM2Ule1tkb7UlvlRj0pFhVhQZe\nzBKgQo3ph/wH7DbJvx4KFZeBObUBLtbyxxUQbCs/fwKBgQD5c4K8OwEISowgw+HZ\nLoZ8ioXF9VY8ExboorMmC9LlBNCAVmUs/52PtQj5s4S/IPJ1o/JVYRo2QcdSm01s\nGcKmcSL1270KOW6ytRGfGq173qyP4kUAWqtcvuMHHaxkD5dhlu643cCdOCyfwiya\nVYnGUgmrcfl+nvwBLdbswegGUwKBgQC8LGJs9vB9fab6awVYd54fRMKHlHX1F0xJ\nTF++J9CcyuVfBDWgOl1+Gn3fBCgMIJGQplfNmYhwO7VSjWJOdYpd/pPaivu4VN1l\nuZ+UU/LKzAImvZpXnknPQQOW9TImWOvLoSYJteMElQWe7Didaw6xMxCj0T2d5F3e\nSD8gVE99hwKBgEIs/J/G3209qZL/pCijiRX9AaQUg74IKmmoz/Hl7RrIfi+tu8WG\nQlxfYHQtxaeWq/u9dIpl6jg+lww5Gv70jojtNqMWmj3eIpnSI0ycHS3hUtIQ6tE/\nPHqsQTogCx24bSZ8jfQJEBIlVuFC9+Yxjw1Hsj0DTXbj4mLFsGC6yDz1AoGAJ30E\n9qrnkt4ggWKeD4+inhs2227bRiCqgKNHYEdIru6hLcxbWJGG9ySmD3v2z3yyL3HI\n8Ttr92mARp+m5qIh9FGtQ2pxIqCkiWlnxJ/NTqN7PBgD4Kk2Agk5sJ8p9AQrD2N0\n8Qq7ZkXDlTMrOlWyEpuNvWL2lEDNNg1hOe6Xc9cCgYEAntEGV8sKhqdFcJoT3w+z\n+R0YBogE2GuoLi6mfuq8GGWfnwbreOyXtCoQlBlvtDNEH6zFLXtq2qtKjoFjYRhL\nfnu+VcivZwBnN/kvwP4ujlDgM+chb3IbXbU/r6vDa+ytrFFQkTm9Azt6vgLGcO8P\ni4H0WDCz8ioOCVXXkjLR9aU=\n-----END PRIVATE KEY-----\n",
  "client_email": "firebase-adminsdk-fbsvc@eyeq-7e199.iam.gserviceaccount.com",
  "client_id": "112101320504053783181",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-fbsvc%40eyeq-7e199.iam.gserviceaccount.com",
  "universe_domain": "googleapis.com"

}

# 🔹 Your Firebase Realtime Database URL
FIREBASE_DB_URL = "https://eyeq-7e199-default-rtdb.firebaseio.com/"

# Initialize Firebase
cred = credentials.Certificate(service_account_info)
firebase_admin.initialize_app(cred, {
    'databaseURL': FIREBASE_DB_URL
})

if not FIREBASE_DB_URL:
    raise ValueError("FIREBASE_DB_URL environment variable not found")

# Initialize Firebase app once
if not firebase_admin._apps:
    if SERVICE_ACCOUNT_PATH:
        cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
        firebase_admin.initialize_app(cred, {
            'databaseURL': FIREBASE_DB_URL
        })
    else:
        # Let firebase-admin use GOOGLE_APPLICATION_CREDENTIALS if set
        firebase_admin.initialize_app(options={'databaseURL': FIREBASE_DB_URL})


def email_to_key(email: str) -> str:
    """Create a safe key from email for use under users_by_email.
    Replace '.' with ',' etc. Keep deterministic."""
    return email.replace('.', ',').lower()


# ------------------ SIMPLE DB HELPERS ------------------
def get_users_ref():
    return db.reference("users")


def get_users_by_email_ref():
    return db.reference("users_by_email")  # maps email_key -> uid


def get_iop_logs_ref(uid: str):
    return db.reference(f"iop_logs/{uid}")  # child = log_id => {iop, blue_light, screen_time, timestamp_iso, timestamp_epoch}


def get_reports_ref(uid: str):
    return db.reference(f"reports/{uid}")


def get_alerts_ref(uid: str):
    return db.reference(f"alerts/{uid}")


def get_devices_ref(uid: str):
    return db.reference(f"devices/{uid}")


def get_activity_logs_ref(uid: str):
    return db.reference(f"activity_logs/{uid}")


# User functions
def create_user_if_not_exists(email: str, name: str = None) -> str:
    """Return uid for email. If user does not exist, create user and mapping."""
    email_key = email_to_key(email)
    map_ref = get_users_by_email_ref().child(email_key)
    uid = map_ref.get()
    if uid:
        return uid

    # Create new user
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
    if not uid:
        return None
    return get_users_ref().child(uid).get()


# IOP log functions
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
        "timestamp_epoch": epoch
    }
    get_iop_logs_ref(uid).child(log_id).set(log_obj)
    return log_obj


def get_latest_logs(uid: str, limit=10):
    """
    Realtime DB returns items keyed by id. Use order_by_child timestamp_epoch and limit_to_last.
    Returns list sorted ascending by timestamp (oldest first).
    """
    ref = get_iop_logs_ref(uid)
    snapshot = ref.order_by_child("timestamp_epoch").limit_to_last(limit).get()
    if not snapshot:
        return []
    # snapshot is dict of log_id -> log_obj
    logs = list(snapshot.values())
    # sort ascending by timestamp_epoch
    logs.sort(key=lambda r: r.get("timestamp_epoch", 0))
    return logs


def get_logs_between(uid: str, start_epoch: int, end_epoch: int):
    ref = get_iop_logs_ref(uid)
    snapshot = ref.order_by_child("timestamp_epoch").start_at(start_epoch).end_at(end_epoch).get()
    if not snapshot:
        return []
    logs = list(snapshot.values())
    logs.sort(key=lambda r: r.get("timestamp_epoch", 0), reverse=True)  # return DESC as in original SQL
    return logs


def get_latest_log(uid: str):
    logs = get_latest_logs(uid, limit=1)
    return logs[-1] if logs else None


# ------------------ EMAIL OTP SENDER ------------------
def send_email_otp(to_email):
    otp = ''.join(str(random.randint(0, 9)) for _ in range(6))
    EMAIL_USER = os.environ.get("EMAIL_USER", "crackerdeba@gmail.com")
    EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")  # MUST be stored in env

    if not EMAIL_PASSWORD:
        app.logger.error("EMAIL_PASSWORD environment variable not set. Can't send OTP.")
        return None

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
        app.logger.info(f"OTP sent to {to_email}. OTP was {otp}")
        return otp
    except Exception as e:
        app.logger.exception("Failed to send OTP")
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

        # Create user mapping if not exists (optional here)
        create_user_if_not_exists(email)

        flash("OTP sent to your email.", "info")
        return redirect(url_for('verify_otp'))

    return render_template('login.html')


@app.route('/verify_otp', methods=['GET', 'POST'])
def verify_otp():
    if request.method == 'POST':
        entered = request.form['otp'].strip()
        correct = session.get('otp')
        expiry = session.get('otp_expiry')

        if not expiry or datetime.utcnow().timestamp() > expiry:
            flash("OTP expired. Please login again.", "warning")
            return redirect(url_for('login'))

        if entered == correct:
            email = session['email']
            user = get_user_by_email(email)
            if not user:
                # The create earlier should have created the user; but create now just in case
                uid = create_user_if_not_exists(email)
                user = get_users_ref().child(uid).get()

            session['authenticated'] = True
            flash("Login successful!", "success")
            return redirect(url_for('dashboard'))

        flash("Incorrect OTP.", "danger")
        return redirect(url_for('verify_otp'))

    return render_template('verify_otp.html')


@app.route('/resend_otp')
def resend_otp():
    if not session.get('email'):
        flash("Session expired. Please login again.", "warning")
        return redirect(url_for('login'))

    new_otp = send_email_otp(session['email'])
    if new_otp:
        session['otp'] = new_otp
        session['otp_expiry'] = (datetime.utcnow() + timedelta(minutes=5)).timestamp()
        flash("OTP resent to your email.", "info")
    else:
        flash("Failed to resend OTP.", "danger")
    return redirect(url_for('verify_otp'))


@app.route('/dashboard')
def dashboard():
    if not session.get('authenticated'):
        return redirect(url_for('login'))

    email = session['email']
    user = get_user_by_email(email)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for('login'))

    user_id = user['id']
    rows = get_latest_logs(user_id, limit=10)  # ascending oldest->newest

    # Prepare chart arrays similar to your original
    iop_values = [r.get('iop') for r in rows]
    blue_values = [r.get('blue_light') for r in rows]
    screen_values = [r.get('screen_time') for r in rows]
    timestamps = []
    for r in rows:
        t_iso = r.get('timestamp_iso')
        if t_iso:
            try:
                # try to parse ISO string and format HH:MM
                ts = datetime.fromisoformat(t_iso.replace("Z", ""))
                timestamps.append(ts.strftime('%H:%M'))
            except:
                timestamps.append("")
        else:
            timestamps.append("")

    latest = rows[-1] if rows else None

    alerts = []
    if latest:
        if latest.get('iop') is not None and latest['iop'] > 21:
            alerts.append("High IOP detected! Consult a doctor.")
        if latest.get('blue_light') is not None and latest['blue_light'] > 25:
            alerts.append("High blue light exposure. Take a break!")
        if latest.get('screen_time') is not None and latest['screen_time'] > 5:
            alerts.append("Reduce screen time to prevent eye strain.")

    return render_template("dashboard.html",
                           data=latest,
                           alerts=alerts,
                           iop={"values": iop_values, "timestamps": timestamps},
                           blue_light={"values": blue_values, "timestamps": timestamps},
                           screen_time={"values": screen_values, "timestamps": timestamps})


@app.route('/history')
def history():
    if not session.get('authenticated'):
        return redirect(url_for('login'))

    email = session['email']
    start = request.args.get('start')
    end = request.args.get('end')

    try:
        start_date = datetime.strptime(start, "%Y-%m-%d") if start else datetime.utcnow() - timedelta(days=7)
        end_date = datetime.strptime(end, "%Y-%m-%d") if end else datetime.utcnow()
    except:
        start_date = datetime.utcnow() - timedelta(days=7)
        end_date = datetime.utcnow()

    user = get_user_by_email(email)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for('login'))

    user_id = user['id']
    start_epoch = int(start_date.timestamp())
    # for end, include the whole day -> add 86399 seconds to end_date if user only provided date
    end_epoch = int(end_date.timestamp())

    logs = get_logs_between(user_id, start_epoch, end_epoch)

    return render_template("history.html",
                           logs=logs,
                           start=start_date.strftime("%Y-%m-%d"),
                           end=end_date.strftime("%Y-%m-%d"))


@app.route('/report')
def report():
    if not session.get('authenticated'):
        return redirect(url_for('login'))

    email = session['email']
    user = get_user_by_email(email)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for('login'))

    user_id = user['id']
    rows = get_latest_logs(user_id, limit=10)
    iop_values = [r.get('iop') for r in rows]
    timestamps = []
    for r in rows:
        t_iso = r.get('timestamp_iso')
        if t_iso:
            try:
                ts = datetime.fromisoformat(t_iso.replace("Z", ""))
                timestamps.append(ts.strftime("%H:%M"))
            except:
                timestamps.append("")
        else:
            timestamps.append("")

    latest = rows[-1] if rows else None

    alerts = []
    if latest:
        if latest.get('iop') is not None and latest['iop'] > 21:
            alerts.append("High IOP detected! Consult a doctor.")
        if latest.get('blue_light') is not None and latest['blue_light'] > 25:
            alerts.append("High blue light exposure. Take a break!")
        if latest.get('screen_time') is not None and latest['screen_time'] > 5:
            alerts.append("Reduce screen time to prevent eye strain.")

    return render_template("report.html",
                           data=latest,
                           alerts=alerts,
                           iop={"values": iop_values, "timestamps": timestamps})


@app.route('/hospitals')
def hospitals():
    if not session.get('authenticated'):
        return redirect(url_for('login'))
    return render_template("hospitals.html")


@app.route('/send_data', methods=['POST'])
def send_data():
    data = request.get_json()
    email = data.get('email')
    iop = data.get('iop')
    blue_light = data.get('blue_light')
    screen_time = data.get('screen_time')
    device_id = data.get('device_id')

    if not email or iop is None:
        return jsonify({'status': 'error', 'msg': 'Missing required data'}), 400

    user = get_user_by_email(email)
    if not user:
        return jsonify({'status': 'error', 'msg': 'User not found'}), 404

    user_id = user['id']
    inserted = insert_iop_log(user_id, iop, blue_light, screen_time, device_id)
    return jsonify({'status': 'success', 'msg': 'Data stored', 'data': inserted})


@app.route('/api/latest_data')
def latest_data():
    email = session.get('email')
    if not email:
        return jsonify({})
    user = get_user_by_email(email)
    if not user:
        return jsonify({})
    user_id = user['id']
    row = get_latest_log(user_id)
    return jsonify(row or {})


# ------------------ MAIN ------------------
if __name__ == "__main__":
    # app.run(host='0.0.0.0', port=10000)
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
