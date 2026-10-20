"""
Handoff — healthcare workflow & care-coordination prototype.

Core idea: responsibility during patient transitions should be visible,
transferable, time-stamped, and accountable. One person owns the baton at
any moment (baton actions: status change, transfer, completion), while any
member of the care team can contribute to the record (notes, orders,
updates) without taking the baton.

Run:  flask --app app run   (or: python app.py)
Demo logins are listed in DEMO.md. DEMO ONLY — not for real PHI.
"""
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import json
import os
import secrets
from datetime import datetime, timezone

app = Flask(__name__)

# Secret key comes from the environment in any real deployment;
# the fallback exists only so the demo runs locally with zero setup.
app.secret_key = os.environ.get("HANDOFF_SECRET_KEY", "handoff-dev-secret-key")

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# -----------------------------
# Role Map (Human-Readable Roles)
# -----------------------------

ROLE_MAP = {
    "1": "ED Attending Physician",
    "2": "Resident Physician",
    "3": "Registered Nurse (RN)",
    "4": "Charge Nurse",
    "5": "Unit Clerk",
    "6": "Care Coordinator",
    "7": "Case Manager",
    "8": "Nurse Practitioner (NP)",
}

def role_label(role_id):
    return ROLE_MAP.get(str(role_id), f"Role {role_id}")

# -----------------------------
# Users (demo accounts)
# -----------------------------
# DEMO ONLY: every demo account shares the demo password "handoff123".
# Passwords are stored hashed, never in plain text. Production use requires
# real per-user credentials managed outside the codebase.

DEMO_PASSWORD = "handoff123"

class User(UserMixin):
    def __init__(self, user_id, username, name, role_id, password_hash):
        self.id = str(user_id)
        self.username = username
        self.name = name
        self.role_id = str(role_id)
        self.role_name = role_label(role_id)
        self.password_hash = password_hash

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

def _make_user(user_id, username, name, role_id):
    return User(user_id, username, name, role_id, generate_password_hash(DEMO_PASSWORD))

USERS = {
    "1": _make_user("1", "dcarter", "Dr. Carter", "1"),
    "2": _make_user("2", "dwilliams", "Dr. Williams", "2"),
    "3": _make_user("3", "njohnson", "Nina Johnson", "8"),
    "4": _make_user("4", "nthompson", "Nurse Thompson", "4"),
    "5": _make_user("5", "amorgan", "Alex Morgan", "5"),
    "6": _make_user("6", "jlee", "Jordan Lee", "6"),
    "7": _make_user("7", "tbrooks", "Taylor Brooks", "7"),
}

USERS_BY_USERNAME = {u.username: u for u in USERS.values()}

_AVATAR_COLORS = ["#1a73e8", "#7b1fa2", "#188038", "#e8710a", "#0097a7", "#c2185b", "#5f6368"]

def initials_of(name):
    parts = [p for p in name.replace(".", "").split() if p.lower() not in ("dr", "nurse")]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()

def user_meta():
    """Display metadata per user id: name, role, avatar initials + color."""
    return {
        uid: {
            "name": u.name,
            "role": u.role_name,
            "initials": initials_of(u.name),
            "color": _AVATAR_COLORS[(int(uid) - 1) % len(_AVATAR_COLORS)],
        }
        for uid, u in USERS.items()
    }

@login_manager.user_loader
def load_user(user_id):
    return USERS.get(str(user_id))

# -----------------------------
# Data storage (development JSON)
# -----------------------------
# The data file lives in a normal project folder and is created
# automatically on first run, so a fresh clone works immediately.
# JSON is development persistence only — production uses a database.

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "handoffs.json")

def load_handoffs():
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

def save_handoffs(handoffs):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(handoffs, f, indent=2)

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def new_handoff_id():
    # Timestamp keeps IDs human-sortable; the random suffix prevents
    # collisions when two handoffs are created in the same second.
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + secrets.token_hex(2)

def find_handoff(handoffs, handoff_id):
    for h in handoffs:
        if h["handoff_id"] == handoff_id:
            return h
    return None

# Hosted-demo mode: on hosts with an ephemeral filesystem the data file
# disappears whenever the service restarts, which would greet visitors
# with an empty board. When HANDOFF_SEED_DEMO=1, (re)seed the fictional
# demo board on startup whenever no data exists yet.
if os.environ.get("HANDOFF_SEED_DEMO") == "1" and not load_handoffs():
    from seed_demo import build_seed_handoffs
    save_handoffs(build_seed_handoffs())

# -----------------------------
# Auth routes
# -----------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    if request.method == "POST":
        username = (request.form.get("username") or "").strip().lower()
        password = request.form.get("password") or ""
        user = USERS_BY_USERNAME.get(username)
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("index"))
        flash("Invalid username or password.")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# -----------------------------
# Dashboard
# -----------------------------

def parse_ts(value):
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None

def enrich(handoff):
    """Add display fields: age of the handoff's current state, staleness."""
    updated = parse_ts(handoff.get("updated_at"))
    age_min = None
    if updated:
        age_min = max(0, int((datetime.now(timezone.utc) - updated).total_seconds() // 60))
    handoff["age_minutes"] = age_min
    status = handoff.get("status")
    # A handoff that sits untouched is the invisible-work problem made
    # visible: flag it amber, then red, the longer it waits.
    if status == "ESCALATED":
        handoff["stale_level"] = "red" if (age_min or 0) >= 60 else "amber" if (age_min or 0) >= 30 else ""
    elif status in ("NEW", "IN_PROGRESS"):
        handoff["stale_level"] = "red" if (age_min or 0) >= 240 else "amber" if (age_min or 0) >= 120 else ""
    else:
        handoff["stale_level"] = ""
    return handoff

def compute_metrics(handoffs):
    metrics = {"NEW": 0, "IN_PROGRESS": 0, "ESCALATED": 0, "COMPLETED": 0, "stale": 0}
    completion_minutes = []
    for h in handoffs:
        metrics[h["status"]] = metrics.get(h["status"], 0) + 1
        if h.get("stale_level"):
            metrics["stale"] += 1
        if h["status"] == "COMPLETED":
            created = parse_ts(h.get("created_at")) or parse_ts(h["history"][0]["at"]) if h.get("history") else None
            done_at = None
            for e in h.get("history", []):
                if e["event"] == "STATUS_CHANGED_TO_COMPLETED":
                    done_at = parse_ts(e["at"])
            if created and done_at:
                completion_minutes.append((done_at - created).total_seconds() / 60)
    metrics["avg_completion"] = (
        round(sum(completion_minutes) / len(completion_minutes)) if completion_minutes else None
    )
    return metrics

@app.route("/")
@login_required
def index():
    all_handoffs = [enrich(h) for h in load_handoffs()]
    metrics = compute_metrics(all_handoffs)
    # Display labels: history and ownership fields store user ids, so
    # resolve them to each user's actual role (people and roles are not
    # always 1:1 — e.g., Nina Johnson is a Nurse Practitioner).
    display_roles = dict(ROLE_MAP)
    for uid, u in USERS.items():
        display_roles[uid] = u.role_name
    meta = user_meta()
    # Board search: match patient, case, event, or a team member's name/role.
    q = (request.args.get("q") or "").strip()
    handoffs = all_handoffs
    if q:
        needle = q.lower()
        def matches(h):
            fields = [h.get("patient_name", ""), h.get("case_id", ""), h.get("event", "")]
            for key in ("owner", "initiator"):
                m = meta.get(str(h.get(key)))
                if m:
                    fields += [m["name"], m["role"]]
            return any(needle in str(f).lower() for f in fields)
        handoffs = [h for h in all_handoffs if matches(h)]
    return render_template("index.html", handoffs=handoffs, roles=display_roles, users=USERS,
                           metrics=metrics, user_meta=meta, q=q, total_count=len(all_handoffs))

# -----------------------------
# Create a handoff
# -----------------------------

@app.route("/create-handoff", methods=["POST"])
@login_required
def create_handoff():
    patient_name = request.form.get("patient_name")
    case_id = request.form.get("case_id")
    event = request.form.get("event")
    owner = request.form.get("owner")

    if not patient_name or not case_id or not event or not owner:
        return "Missing required fields — check all inputs", 400

    handoffs = load_handoffs()
    ts = now_iso()

    age = (request.form.get("patient_age") or "").strip()
    sex = (request.form.get("patient_sex") or "").strip().upper()

    new_handoff = {
        "handoff_id": new_handoff_id(),
        "patient_name": patient_name,
        "case_id": case_id,
        "event": event,
        "age": age if age else None,
        "sex": sex if sex in ("M", "F") else None,
        # The initiator is whoever is signed in and creates the handoff —
        # accountability starts with a real identity, not a dropdown.
        "initiator": int(current_user.id),
        "owner": int(owner),
        "status": "NEW",
        "created_at": ts,
        "updated_at": ts,
        "history": [
            {"at": ts, "event": "CREATED", "by": int(current_user.id)}
        ],
    }

    handoffs.append(new_handoff)
    save_handoffs(handoffs)
    return redirect(url_for("index"))

# ===== WORKFLOW POLICY (single source of truth) =====

STATUSES = ["NEW", "IN_PROGRESS", "ESCALATED", "COMPLETED"]

ALLOWED_STATUS_TRANSITIONS = {
    "NEW": {"IN_PROGRESS"},
    "IN_PROGRESS": {"ESCALATED", "COMPLETED"},
    "ESCALATED": {"IN_PROGRESS", "COMPLETED"},
    "COMPLETED": set(),
}

# Transfer rules
TRANSFER_ALLOWED_STATUSES = {"NEW", "IN_PROGRESS", "ESCALATED"}  # NOT COMPLETED
ALLOW_SELF_TRANSFER = False

# Enforcement rules
ONLY_OWNER_CAN_CHANGE_STATUS = True
ONLY_OWNER_CAN_TRANSFER = True  # strong default

# Role permissions for status changes
ROLE_STATUS_PERMISSIONS = {
    "1": {"NEW", "IN_PROGRESS", "ESCALATED", "COMPLETED"},
    "2": {"NEW", "IN_PROGRESS", "ESCALATED", "COMPLETED"},
    "3": {"NEW", "IN_PROGRESS", "ESCALATED", "COMPLETED"},
    "4": {"NEW", "IN_PROGRESS", "ESCALATED", "COMPLETED"},
    "5": {"NEW", "IN_PROGRESS", "ESCALATED", "COMPLETED"},
    "6": {"NEW", "IN_PROGRESS", "ESCALATED", "COMPLETED"},
    "7": {"NEW", "IN_PROGRESS", "ESCALATED", "COMPLETED"},
    "8": {"NEW", "IN_PROGRESS", "ESCALATED", "COMPLETED"},
}

def is_valid_status(status: str) -> bool:
    return status in STATUSES

def can_change_status(current_status: str, new_status: str) -> bool:
    if not is_valid_status(current_status) or not is_valid_status(new_status):
        return False
    return new_status in ALLOWED_STATUS_TRANSITIONS.get(current_status, set())

def can_transfer(current_status: str, old_owner: str, new_owner: str) -> bool:
    if current_status not in TRANSFER_ALLOWED_STATUSES:
        return False
    if not ALLOW_SELF_TRANSFER and new_owner == old_owner:
        return False
    return True

# -----------------------------
# Baton actions (current owner only)
# -----------------------------

@app.route("/update-status", methods=["POST"])
@login_required
def update_status():
    handoff_id = request.form.get("handoff_id")
    new_status = request.form.get("status")

    handoffs = load_handoffs()
    target = find_handoff(handoffs, handoff_id)
    if target is None:
        return "Handoff not found", 404

    old_status = target["status"]
    current_owner = target["owner"]

    # Owner-only enforcement — against the signed-in user, not a form field.
    if ONLY_OWNER_CAN_CHANGE_STATUS and str(current_user.id) != str(current_owner):
        return "Unauthorized: Only current owner can change status", 403

    allowed_statuses = ROLE_STATUS_PERMISSIONS.get(current_user.role_id, set())
    if new_status not in allowed_statuses:
        return "Role not allowed to set this status", 403

    if not can_change_status(old_status, new_status):
        return f"Invalid status transition: {old_status} -> {new_status}", 400

    target["status"] = new_status
    target["updated_at"] = now_iso()
    target["history"].append({
        "at": target["updated_at"],
        "event": f"STATUS_CHANGED_TO_{new_status}",
        "by": int(current_user.id),
    })

    save_handoffs(handoffs)
    return redirect(url_for("index"))

@app.route("/transfer-owner", methods=["POST"])
@login_required
def transfer_owner():
    handoff_id = request.form["handoff_id"]
    new_owner = request.form["new_owner"]

    handoffs = load_handoffs()
    target = find_handoff(handoffs, handoff_id)
    if target is None:
        return "Handoff not found", 404

    old_owner = target["owner"]
    if ONLY_OWNER_CAN_TRANSFER and str(current_user.id) != str(old_owner):
        return "Unauthorized: Only current owner can transfer ownership", 403

    if not can_transfer(target["status"], str(old_owner), str(new_owner)):
        return "Transfer not allowed for this handoff", 400

    target["owner"] = int(new_owner)
    target["updated_at"] = now_iso()
    target["history"].append({
        "at": target["updated_at"],
        "event": "OWNERSHIP_TRANSFERRED",
        "by": f"{old_owner} → {new_owner}",
    })

    save_handoffs(handoffs)
    return redirect(url_for("index"))

# -----------------------------
# Record actions (any signed-in care team member)
# -----------------------------
# Real units chart collaboratively: several clinicians add orders and
# notes to the same patient. Those contributions belong ON the record —
# time-stamped and attributed — without moving the baton. Only the owner
# can change status or transfer ownership (above).

RECORD_TYPES = {"NOTE", "ORDER", "UPDATE"}

@app.route("/add-note", methods=["POST"])
@login_required
def add_note():
    handoff_id = request.form.get("handoff_id")
    note_type = (request.form.get("note_type") or "NOTE").upper()
    text = (request.form.get("text") or "").strip()

    if note_type not in RECORD_TYPES:
        return "Invalid record type", 400
    if not text:
        return "Record entry cannot be empty", 400
    if len(text) > 1000:
        return "Record entry too long (1000 characters max)", 400

    handoffs = load_handoffs()
    target = find_handoff(handoffs, handoff_id)
    if target is None:
        return "Handoff not found", 404

    ts = now_iso()
    target["history"].append({
        "at": ts,
        "event": "RECORD_ADDED",
        "type": note_type,
        "text": text,
        "by": int(current_user.id),
    })
    target["updated_at"] = ts

    save_handoffs(handoffs)
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=os.environ.get("HANDOFF_DEBUG", "1") == "1")
