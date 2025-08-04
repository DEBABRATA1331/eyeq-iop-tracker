from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import psycopg2
from psycopg2.extras import RealDictCursor
import os
import smtplib
from email.mime.text import MIMEText
import random
import uuid
from datetime import datetime, timedelta
import time

app = Flask(__name__)
app.secret_key = os.urandom(24)

# ------------------ DATABASE CONFIG ------------------
DATABASE_CONFIG = {
    'dbname': 'eyeq_db',
    'user': 'eyeq_user',
    'password': '@Truesilver8',
    'host': 'localhost',
    'port': '5432'
}

def get_db_connection():
    return psycopg2.connect(**DATABASE_CONFIG)

# ------------------ DATABASE SETUP ------------------
def init_db():
    with get_db_connection() as con:
        with con.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id UUID PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    phone TEXT NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS iop_logs (
                    id SERIAL PRIMARY KEY,
                    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    iop REAL,
                    blue_light REAL,
                    screen_time REAL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            con.commit()

# ------------------ EMAIL OTP SENDER ------------------
def send_email_otp(email):
    otp = str(random.randint(100000, 999999))
    msg = MIMEText(f"Your Eye-Q OTP is: {otp}")
    msg['Subject'] = "Eye-Q OTP Verification"
    msg['From'] = "crackerdeba@gmail.com"
    msg['To'] = email

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login("crackerdeba@gmail.com", "your_app_password")  # Use Gmail App Password!
            server.send_message(msg)
        return otp
    except Exception as e:
        print("Email sending failed:", e)
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
        session['otp_expiry'] = (datetime.now() + timedelta(minutes=5)).timestamp()
        session['email'] = email

        flash("OTP sent to your email.", "info")
        return redirect(url_for('verify_otp'))

    return render_template('login.html')


@app.route('/verify_otp', methods=['GET', 'POST'])
def verify_otp():
    if request.method == 'POST':
        entered = request.form['otp'].strip()
        correct = session.get('otp')
        expiry = session.get('otp_expiry')

        if not expiry or datetime.now().timestamp() > expiry:
            flash("OTP expired. Please login again.", "warning")
            return redirect(url_for('login'))

        if entered == correct:
            email = session['email']
            user_id = str(uuid.uuid4())

            try:
                with get_db_connection() as con:
                    with con.cursor() as cur:
                        cur.execute("""
                            INSERT INTO users (id, email)
                            VALUES (%s, %s)
                            ON CONFLICT (email) DO NOTHING;
                        """, (user_id, email))
                        con.commit()
            except Exception as e:
                print("DB error:", e)
                flash("Database error occurred.", "danger")
                return redirect(url_for('login'))

            # Clear OTP session data
            session.pop('otp', None)
            session.pop('otp_expiry', None)

            session['authenticated'] = True
            session['email'] = email
            flash("Login successful!", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Incorrect OTP. Please try again.", "danger")

    return render_template('verify_otp.html')


@app.route('/resend_otp')
def resend_otp():
    if not session.get('email'):
        flash("Session expired. Please login again.", "warning")
        return redirect(url_for('login'))

    new_otp = send_email_otp(session['email'])
    if new_otp:
        session['otp'] = new_otp
        session['otp_expiry'] = (datetime.now() + timedelta(minutes=5)).timestamp()
        flash("OTP resent to your email.", "info")
    else:
        flash("Failed to resend OTP.", "danger")
    return redirect(url_for('verify_otp'))

@app.route('/dashboard')
def dashboard():
    if not session.get('authenticated'):
        return redirect(url_for('login'))

    email = session['email']
    with get_db_connection() as con:
        with con.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id FROM users WHERE email = %s", (email,))
            user = cur.fetchone()
            if not user:
                flash("User not found.", "danger")
                return redirect(url_for('login'))

            user_id = user['id']
            cur.execute("""
                SELECT iop, blue_light, screen_time, timestamp
                FROM iop_logs
                WHERE user_id=%s
                ORDER BY timestamp DESC LIMIT 10
            """, (user_id,))
            rows = cur.fetchall()

    iop_values = [row['iop'] for row in rows][::-1]
    blue_values = [row['blue_light'] for row in rows][::-1]
    screen_values = [row['screen_time'] for row in rows][::-1]
    timestamps = [row['timestamp'].strftime('%H:%M') for row in rows][::-1]
    latest = rows[-1] if rows else None

    alerts = []
    if latest:
        if latest['iop'] > 21:
            alerts.append("High IOP detected! Consult a doctor.")
        if latest['blue_light'] > 25:
            alerts.append("High blue light exposure. Take a break!")
        if latest['screen_time'] > 5:
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
        start_date = datetime.strptime(start, "%Y-%m-%d") if start else datetime.now() - timedelta(days=7)
        end_date = datetime.strptime(end, "%Y-%m-%d") if end else datetime.now()
    except:
        start_date = datetime.now() - timedelta(days=7)
        end_date = datetime.now()

    with get_db_connection() as con:
        with con.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id FROM users WHERE email = %s", (email,))
            user = cur.fetchone()
            if not user:
                flash("User not found.", "danger")
                return redirect(url_for('login'))

            user_id = user['id']
            cur.execute("""
                SELECT iop, blue_light, screen_time, timestamp
                FROM iop_logs
                WHERE user_id = %s AND timestamp BETWEEN %s AND %s
                ORDER BY timestamp DESC
            """, (user_id, start_date, end_date))
            logs = cur.fetchall()

    return render_template("history.html", logs=logs,
                           start=start_date.strftime("%Y-%m-%d"),
                           end=end_date.strftime("%Y-%m-%d"))

@app.route('/report')
def report():
    if not session.get('authenticated'):
        return redirect(url_for('login'))

    email = session['email']
    with get_db_connection() as con:
        with con.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id FROM users WHERE email = %s", (email,))
            user = cur.fetchone()
            if not user:
                flash("User not found.", "danger")
                return redirect(url_for('login'))

            user_id = user['id']
            cur.execute("""
                SELECT iop, blue_light, screen_time, timestamp
                FROM iop_logs
                WHERE user_id=%s
                ORDER BY timestamp DESC LIMIT 10
            """, (user_id,))
            rows = cur.fetchall()

    iop_values = [row['iop'] for row in rows][::-1]
    timestamps = [row['timestamp'].strftime('%H:%M') for row in rows][::-1]
    latest = rows[-1] if rows else None

    alerts = []
    if latest:
        if latest['iop'] > 21:
            alerts.append("High IOP detected! Consult a doctor.")
        if latest['blue_light'] > 25:
            alerts.append("High blue light exposure. Take a break!")
        if latest['screen_time'] > 5:
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

    if not email or iop is None:
        return jsonify({'status': 'error', 'msg': 'Missing required data'}), 400

    with get_db_connection() as con:
        with con.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE email = %s", (email,))
            user = cur.fetchone()
            if not user:
                return jsonify({'status': 'error', 'msg': 'User not found'}), 404

            user_id = user[0]
            cur.execute("""
                INSERT INTO iop_logs (user_id, iop, blue_light, screen_time)
                VALUES (%s, %s, %s, %s)
            """, (user_id, iop, blue_light, screen_time))
            con.commit()

    return jsonify({'status': 'success', 'msg': 'Data stored'})

@app.route('/api/latest_data')
def latest_data():
    email = session.get('email')
    with get_db_connection() as con:
        with con.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id FROM users WHERE email = %s", (email,))
            user = cur.fetchone()
            if not user:
                return jsonify({})

            user_id = user['id']
            cur.execute("""
                SELECT iop, blue_light, screen_time, timestamp
                FROM iop_logs
                WHERE user_id=%s
                ORDER BY timestamp DESC LIMIT 1
            """, (user_id,))
            row = cur.fetchone()
    return jsonify(row or {})

# ------------------ MAIN ------------------

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
