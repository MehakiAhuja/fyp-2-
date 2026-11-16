from functools import wraps
from datetime import datetime

from flask import Blueprint, jsonify, request, render_template, session, redirect, url_for

import db
import bill
from catalog import CATALOG, TIPS, GENERAL_TIP

advisor_bp = Blueprint("advisor", __name__)


def init_tables():
    con = db.connect()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS budgets(
        user_id INTEGER PRIMARY KEY,
        monthly_budget REAL NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS user_appliances(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        type TEXT NOT NULL,
        variant TEXT NOT NULL,
        brand TEXT NOT NULL,
        watts REAL NOT NULL,
        qty INTEGER NOT NULL,
        hours REAL NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
    """)
    con.commit()
    con.close()


init_tables()


def api_login(f):
    @wraps(f)
    def wrapper(*a, **k):
        if "user_id" not in session:
            return jsonify(ok=False, message="Please sign in."), 401
        return f(*a, **k)
    return wrapper


def get_budget(uid):
    con = db.connect()
    row = con.execute("SELECT monthly_budget FROM budgets WHERE user_id=?", (uid,)).fetchone()
    con.close()
    return row["monthly_budget"] if row else None


def get_appliances(uid):
    con = db.connect()
    rows = con.execute("SELECT * FROM user_appliances WHERE user_id=? ORDER BY id", (uid,)).fetchall()
    con.close()
    return [dict(r) for r in rows]


def latest_period(uid):
    rows = db.list_readings(uid, 6)
    for i, r in enumerate(rows):
        if r["units_consumed"] is not None:
            prev = [x["units_consumed"] for x in rows[i + 1:i + 6]]
            return r, bill.estimate(r["units_consumed"], prev), prev
    return None, None, []


def units_for_budget(budget, previous):
    best = 0
    for u in range(0, 3001):
        est = bill.estimate(u, previous)
        if est and est["amount"] <= budget:
            best = u
    return best


def budget_status(uid):
    budget = get_budget(uid)
    out = {"budget": budget, "bill": None, "units": None, "state": "none"}
    r, est, prev = latest_period(uid)
    if r and est:
        out["units"] = r["units_consumed"]
        out["bill"] = est["amount"]
    if budget:
        out["units_allowed"] = units_for_budget(budget, prev)
        if est:
            out["diff"] = round(est["amount"] - budget, 2)
            out["state"] = "over" if out["diff"] > 0 else "within"
        else:
            out["state"] = "no_reading"
    return out


def appliance_rows(items):
    rows = []
    for a in items:
        kwh = a["watts"] * a["qty"] * a["hours"] * 30 / 1000
        rows.append({"id": a["id"], "type": a["type"], "variant": a["variant"], "brand": a["brand"],
                     "watts": a["watts"], "qty": a["qty"], "hours": a["hours"], "kwh_month": round(kwh, 1)})
    total = sum(r["kwh_month"] for r in rows)
    est = bill.estimate(round(total, 2), ()) if total > 0 else None
    for r in rows:
        r["cost"] = round(est["amount"] * r["kwh_month"] / total) if est and total else 0
    return rows, total, est


def make_tips(rows, total, est):
    tips = []
    if not rows or not est:
        return tips
    for r in sorted(rows, key=lambda x: x["kwh_month"], reverse=True)[:3]:
        saved = r["watts"] * r["qty"] * 30 / 1000 if r["hours"] >= 1 else 0
        saving = 0
        if saved:
            new = bill.estimate(round(max(total - saved, 0), 2), ())
            saving = round(est["amount"] - (new["amount"] if new else 0))
        tips.append({"title": f'{r["type"]} ({r["variant"]}) uses about {r["kwh_month"]:g} units per month',
                     "text": TIPS.get(r["type"], GENERAL_TIP),
                     "saving_units": round(saved, 1), "saving_rs": saving})
    return tips


@advisor_bp.route("/advisor")
def advisor_page():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("advisor.html", name=session["user_name"])


@advisor_bp.route("/advisor/api/catalog")
@api_login
def catalog():
    return jsonify({t: {"hours": c["hours"], "brands": c["brands"],
                        "variants": [{"name": n, "watts": w} for n, w in c["variants"]]}
                    for t, c in CATALOG.items()})


@advisor_bp.route("/advisor/api/state")
@api_login
def state():
    uid = session["user_id"]
    rows, total, est = appliance_rows(get_appliances(uid))
    return jsonify(ok=True, budget=get_budget(uid), appliances=rows, total_kwh=round(total, 1),
                   estimate=est, status=budget_status(uid), tips=make_tips(rows, total, est))


@advisor_bp.route("/advisor/api/status")
@api_login
def status():
    return jsonify(budget_status(session["user_id"]))


@advisor_bp.route("/advisor/api/budget", methods=["POST"])
@api_login
def set_budget():
    d = request.get_json(force=True, silent=True) or {}
    try:
        value = float(d.get("budget"))
    except (TypeError, ValueError):
        return jsonify(ok=False, message="Please enter a valid amount."), 400
    if not 100 <= value <= 1000000:
        return jsonify(ok=False, message="Budget must be between Rs 100 and Rs 1,000,000."), 400
    con = db.connect()
    con.execute("INSERT OR REPLACE INTO budgets(user_id, monthly_budget) VALUES(?,?)",
                (session["user_id"], value))
    con.commit()
    con.close()
    return jsonify(ok=True)


@advisor_bp.route("/advisor/api/appliance", methods=["POST"])
@api_login
def add_appliance():
    d = request.get_json(force=True, silent=True) or {}
    t, v, b = d.get("type"), d.get("variant"), d.get("brand")
    cat = CATALOG.get(t)
    if not cat or v not in [x[0] for x in cat["variants"]] or b not in cat["brands"]:
        return jsonify(ok=False, message="Please choose a valid appliance."), 400
    try:
        watts, qty, hours = float(d.get("watts")), int(d.get("qty")), float(d.get("hours"))
    except (TypeError, ValueError):
        return jsonify(ok=False, message="Please enter valid numbers."), 400
    if not (1 <= watts <= 10000 and 1 <= qty <= 50 and 0 <= hours <= 24):
        return jsonify(ok=False, message="Watts must be 1 to 10000, quantity 1 to 50 and hours 0 to 24."), 400
    uid = session["user_id"]
    if len(get_appliances(uid)) >= 50:
        return jsonify(ok=False, message="You can add up to 50 appliances."), 400
    con = db.connect()
    con.execute("INSERT INTO user_appliances(user_id,type,variant,brand,watts,qty,hours,created_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (uid, t, v, b, watts, qty, hours, datetime.now().isoformat(timespec="seconds")))
    con.commit()
    con.close()
    return jsonify(ok=True)


@advisor_bp.route("/advisor/api/appliance/delete", methods=["POST"])
@api_login
def delete_appliance():
    d = request.get_json(force=True, silent=True) or {}
    con = db.connect()
    con.execute("DELETE FROM user_appliances WHERE id=? AND user_id=?", (d.get("id"), session["user_id"]))
    con.commit()
    con.close()
    return jsonify(ok=True)