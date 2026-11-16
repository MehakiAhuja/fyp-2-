import sqlite3
from datetime import datetime

DB_PATH = "digitronix_product.db"


def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def now():
    return datetime.now().isoformat(timespec="seconds")


def init_db():
    con = connect()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS readings(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        reading REAL NOT NULL,
        units_consumed REAL,
        confidence INTEGER,
        image_file TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_readings_user ON readings(user_id, id);
    """)
    con.commit()
    con.close()


def create_user(name, email, password_hash):
    con = connect()
    try:
        con.execute("INSERT INTO users(name,email,password_hash,created_at) VALUES(?,?,?,?)",
                    (name, email, password_hash, now()))
        con.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        con.close()


def get_user_by_email(email):
    con = connect()
    row = con.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    con.close()
    return row


def last_reading(user_id):
    con = connect()
    row = con.execute("SELECT * FROM readings WHERE user_id=? ORDER BY id DESC LIMIT 1",
                      (user_id,)).fetchone()
    con.close()
    return row


def add_reading(user_id, reading, units, confidence, image_file):
    con = connect()
    con.execute("INSERT INTO readings(user_id,reading,units_consumed,confidence,image_file,created_at) "
                "VALUES(?,?,?,?,?,?)", (user_id, reading, units, confidence, image_file, now()))
    con.commit()
    con.close()


def list_readings(user_id, limit=50):
    con = connect()
    rows = con.execute("SELECT reading, units_consumed, confidence, created_at FROM readings "
                       "WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, limit)).fetchall()
    con.close()
    return [dict(r) for r in rows]

def init_reset_table():
    con = connect()
    con.execute("""CREATE TABLE IF NOT EXISTS password_resets(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        token_hash TEXT NOT NULL UNIQUE,
        expires_at REAL NOT NULL,
        used INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE)""")
    con.commit()
    con.close()


def create_reset(user_id, token_hash, expires_at):
    con = connect()
    con.execute("INSERT INTO password_resets(user_id,token_hash,expires_at) VALUES(?,?,?)",
                (user_id, token_hash, expires_at))
    con.commit()
    con.close()


def get_reset(token_hash):
    con = connect()
    row = con.execute("SELECT * FROM password_resets WHERE token_hash=?", (token_hash,)).fetchone()
    con.close()
    return row


def finish_reset(reset_id, user_id, password_hash):
    con = connect()
    con.execute("UPDATE users SET password_hash=? WHERE id=?", (password_hash, user_id))
    con.execute("UPDATE password_resets SET used=1 WHERE user_id=?", (user_id,))
    con.commit()
    con.close()