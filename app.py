from flask import Flask, render_template_string, request, redirect, session, url_for, flash
import sqlite3, requests, datetime, time, os
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(_name_)
app.secret_key = "supersecretkey-change-this"

# ------------------ PAYSTACK CONFIG ------------------
PAYSTACK_SECRET_KEY = "sk_live_a3b54b93adda7b63c4d63ceefd531b7e9bb22d6f"
PAYSTACK_PUBLIC_KEY = "pk_live_37c572730932ad4d495253ea03e2346f1f5b3aae"
PAYSTACK_INIT_URL = "https://api.paystack.co/transaction/initialize"
PAYSTACK_VERIFY_URL = "https://api.paystack.co/transaction/verify/"

# ------------------ WHATSAPP CONTACTS ------------------
ADMIN_WHATSAPP = "233247928766"
MANAGER_WHATSAPP = "233556429525"

# ------------------ DATABASE ------------------
DB_FILE = "datastore.db"

def db():
    return sqlite3.connect(DB_FILE)

def init_db():
    conn = db()
    c = conn.cursor()

    # super admin
    c.execute("""
      CREATE TABLE IF NOT EXISTS admins(
        id INTEGER PRIMARY KEY CHECK (id=1),
        email TEXT NOT NULL,
        password_hash TEXT NOT NULL
      )
    """)

    # agents
    c.execute("""
      CREATE TABLE IF NOT EXISTS agents(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        email TEXT NOT NULL
      )
    """)

    # wallets
    c.execute("""
      CREATE TABLE IF NOT EXISTS wallets(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_type TEXT NOT NULL,
        identifier TEXT NOT NULL,
        balance REAL NOT NULL DEFAULT 0,
        UNIQUE(user_type, identifier)
      )
    """)

    # purchases
    c.execute("""
      CREATE TABLE IF NOT EXISTS purchases(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT NOT NULL,
        network TEXT,
        bundle_gb INTEGER,
        recipient TEXT,
        full_name TEXT,
        mobile TEXT,
        location TEXT,
        dob TEXT,
        amount REAL NOT NULL,
        payer_type TEXT,
        payer_identifier TEXT,
        reference TEXT UNIQUE,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL
      )
    """)

    # transactions
    c.execute("""
      CREATE TABLE IF NOT EXISTS transactions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tx_type TEXT NOT NULL,
        user_type TEXT NOT NULL,
        identifier TEXT NOT NULL,
        amount REAL NOT NULL,
        reference TEXT UNIQUE,
        status TEXT NOT NULL,
        meta TEXT,
        created_at TEXT NOT NULL
      )
    """)

    # seed super admin
    c.execute("SELECT COUNT(*) FROM admins WHERE id=1")
    has_admin = c.fetchone()[0]
    if has_admin == 0:
        c.execute(
            "INSERT INTO admins(id, email, password_hash) VALUES (1, ?, ?)",
            ("adariyadominic@gmail.com", generate_password_hash("Dominic@##@"))
        )

    conn.commit()
    conn.close()

init_db()

# ------------------ HELPERS ------------------
def now_str():
    return datetime.datetime.now().isoformat(sep=" ", timespec="seconds")

def make_ref(prefix, parts):
    ts = int(time.time())
    clean_parts = ["".join(str(p).split()) for p in parts]
    return f"{prefix}-{'-'.join(clean_parts)}-{ts}"

def get_or_create_wallet(user_type, identifier):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT id, balance FROM wallets WHERE user_type=? AND identifier=?", (user_type, identifier))
    row = c.fetchone()
    if row:
        conn.close()
        return row[0], float(row[1])
    c.execute("INSERT INTO wallets(user_type, identifier, balance) VALUES (?,?,0)", (user_type, identifier))
    conn.commit()
    c.execute("SELECT id, balance FROM wallets WHERE user_type=? AND identifier=?", (user_type, identifier))
    row = c.fetchone()
    conn.close()
    return row[0], float(row[1])

def wallet_balance(user_type, identifier):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT balance FROM wallets WHERE user_type=? AND identifier=?", (user_type, identifier))
    row = c.fetchone()
    conn.close()
    return float(row[0]) if row else 0.0

def adjust_wallet(user_type, identifier, delta):
    conn = db()
    c = conn.cursor()
    get_or_create_wallet(user_type, identifier)
    c.execute("UPDATE wallets SET balance = balance + ? WHERE user_type=? AND identifier=?", (delta, user_type, identifier))
    conn.commit()
    conn.close()

def init_payment(email, amount, reference, callback_url="/payment/callback"):
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}", "Content-Type": "application/json"}
    data = {
        "email": email,
        "amount": int(round(amount * 100)),
        "reference": reference,
        "callback_url": request.host_url.strip("/") + callback_url
    }
    r = requests.post(PAYSTACK_INIT_URL, json=data, headers=headers, timeout=20)
    res = r.json()
    return res["data"]["authorization_url"] if res.get("status") and res.get("data") else None

def verify_payment(reference):
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
    r = requests.get(PAYSTACK_VERIFY_URL + reference, headers=headers, timeout=20)
    try:
        res = r.json()
        return res.get("status") and res.get("data", {}).get("status") == "success"
    except Exception:
        return False

# ------------------ TEMPLATE ------------------
BASE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Data Store</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="container py-4">
  {% with messages = get_flashed_messages() %}
    {% if messages %}
      <div class="alert alert-info">{{ messages|join(', ') }}</div>
    {% endif %}
  {% endwith %}
  {{ content|safe }}

  <!-- WhatsApp Manager -->
  <a href="https://wa.me/{{ MANAGER_WHATSAPP }}?text={{ manager_msg|urlencode }}"
     target="_blank"
     style="position: fixed; bottom: 20px; right: 80px; background-color: #25D366; color: white; border-radius: 50%; padding: 15px; text-align: center; font-size: 22px; box-shadow: 0 4px 6px rgba(0,0,0,0.2);">
      📱
  </a>

  <!-- WhatsApp Admin -->
  <a href="https://wa.me/{{ ADMIN_WHATSAPP }}?text={{ admin_msg|urlencode }}"
     target="_blank"
     style="position: fixed; bottom: 20px; right: 20px; background-color: #007bff; color: white; border-radius: 50%; padding: 15px; text-align: center; font-size: 22px; box-shadow: 0 4px 6px rgba(0,0,0,0.2);">
      💬
  </a>
</body>
</html>
"""

def page(content_html, manager_msg="Hello Manager, I need help.", admin_msg="Hello Admin, I need help."):
    return render_template_string(BASE, content=content_html, MANAGER_WHATSAPP=MANAGER_WHATSAPP,
                                  ADMIN_WHATSAPP=ADMIN_WHATSAPP, manager_msg=manager_msg, admin_msg=admin_msg)

# ------------------ PUBLIC / CUSTOMER ------------------
@app.route("/")
def index():
    bundles = [(gb, gb * 5) for gb in range(1, 31)]
    networks = ["MTN", "Telecel", "Tigo Big-Time", "Tigo IShare"]
    manager_msg = "Hello Manager, I need help with my data purchase."
    admin_msg = "Hello Admin, I need help with my data purchase."
    html = "<h1 class='mb-3'>📶 Data Bundles Store</h1><p>Use forms below to buy bundles or register AFA.</p>"
    return page(html, manager_msg=manager_msg, admin_msg=admin_msg)

# ------------------ RUN ------------------
if _name_ == "_main_":
    app.run(debug=True)
