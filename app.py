"""
Handoff — healthcare workflow & care-coordination prototype.

Core idea: responsibility during patient transitions should be visible,
transferable, time-stamped, and accountable. One person owns the baton at
any moment (baton actions: status change, transfer, completion), while any
member of the care team can contribute to the record (notes, orders,
updates) without taking the baton.

Patient-centered layer (Clinical Feedback Assessment #002): the patient is
a first-class record derived from the case reference; care-team membership,
task ownership (the baton), and personal following are three separate
axes. Membership governs the patient workspace; the baton governs one
task; following governs only your own landing page.

Run:  flask --app app run   (or: python app.py)
Demo logins are listed in DEMO.md. DEMO ONLY — not for real PHI.
"""
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import hashlib
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
    "8": _make_user("8", "epriddy", "Erin Priddy", "3"),
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

# -----------------------------
# Patient-centered layer (Assessment #002)
# -----------------------------
# Handoffs stay in DATA_FILE as the same bare list every existing tool and
# test relies on — histories are never rewritten. The patient-centered
# additions (explicit team changes, personal follows, read state) live in
# a sidecar file in the same folder, so repointing DATA_FILE (as the
# tests do) isolates both stores together. Patient identity itself is
# derived from the case reference: patient_id == case_id.

def care_file():
    return os.path.join(os.path.dirname(DATA_FILE), "care_store.json")

def load_care():
    try:
        with open(care_file(), "r") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
    except (OSError, json.JSONDecodeError):
        data = {}
    data.setdefault("members_added", {})
    data.setdefault("members_removed", {})
    data.setdefault("follows", [])
    data.setdefault("read_state", {})
    return data

def save_care(care):
    os.makedirs(os.path.dirname(care_file()), exist_ok=True)
    with open(care_file(), "w") as f:
        json.dump(care, f, indent=2)

# Charge nurses and care coordinators coordinate across the whole unit:
# they hold organization-wide workspace access by role. Everyone else's
# access is their care-team membership on that patient.
ORG_WIDE_ROLES = {"4", "6"}

SECTIONS = ["LABS", "DIAGNOSTICS", "CONSULTS", "TASKS"]
SECTION_LABELS = {
    "LABS": "Labs",
    "DIAGNOSTICS": "Diagnostics / Imaging",
    "CONSULTS": "Consultations",
    "TASKS": "Care Tasks",
}
RECORD_CATEGORY_SECTION = {"LAB": "LABS", "DIAGNOSTIC": "DIAGNOSTICS", "CONSULT": "CONSULTS"}
RECORD_CATEGORIES = {"GENERAL", "LAB", "DIAGNOSTIC", "CONSULT"}
OPEN_STATUSES = {"NEW", "IN_PROGRESS", "ESCALATED"}

def infer_section(event_text):
    t = (event_text or "").lower()
    if any(k in t for k in ("mri", "ct ", "ct-", "x-ray", "xray", "ultrasound", "echo", "imaging", "scan", "mammogram")):
        return "DIAGNOSTICS"
    if any(k in t for k in ("lab", "troponin", "cbc", "culture", "blood", "insulin")):
        return "LABS"
    if "consult" in t:
        return "CONSULTS"
    return "TASKS"

def task_section(h):
    return h.get("section") or infer_section(h.get("event"))

def all_patients(handoffs):
    """Group handoff records into patient records keyed by case reference."""
    patients = {}
    for h in handoffs:
        cid = str(h.get("case_id"))
        p = patients.get(cid)
        if p is None:
            p = {
                "case_id": cid,
                "patient_name": h.get("patient_name", ""),
                "age": h.get("age"),
                "sex": h.get("sex"),
                "context": "",
                "tasks": [],
            }
            patients[cid] = p
        if not p["context"] and h.get("patient_context"):
            p["context"] = h["patient_context"]
        p["tasks"].append(h)
    return patients

def derived_member_ids(handoffs, case_id):
    """Team membership derived from the record itself: whoever initiated,
    owns, owned, or has contributed to any of the patient's tasks is on
    the care team. This is how existing history becomes membership at
    migration time — nobody loses a patient they already work on."""
    ids = set()
    for h in handoffs:
        if str(h.get("case_id")) != str(case_id):
            continue
        ids.add(str(h.get("initiator")))
        ids.add(str(h.get("owner")))
        for e in h.get("history", []):
            by = e.get("by")
            if isinstance(by, int) or (isinstance(by, str) and by.isdigit()):
                ids.add(str(by))
            elif isinstance(by, str) and "→" in by:
                for part in by.split("→"):
                    part = part.strip()
                    if part.isdigit():
                        ids.add(part)
    ids.discard("None")
    return ids

def owns_open_task(handoffs, case_id, user_id):
    return any(
        str(h.get("case_id")) == str(case_id)
        and str(h.get("owner")) == str(user_id)
        and h.get("status") in OPEN_STATUSES
        for h in handoffs
    )

def effective_member_ids(handoffs, care, case_id):
    ids = derived_member_ids(handoffs, case_id)
    ids |= {str(u) for u in care["members_added"].get(str(case_id), [])}
    removed = {str(u) for u in care["members_removed"].get(str(case_id), [])}
    for uid in removed:
        # The clinician holding an open baton cannot be removed from the
        # team out from under their own accountability.
        if not owns_open_task(handoffs, case_id, uid):
            ids.discard(uid)
    return ids

def unit_wide_access(user):
    """Charge nurses (role 4) and care coordinators (role 6) hold
    unit-wide access — the single rule every scope decision uses."""
    return str(getattr(user, "role_id", "")) in ORG_WIDE_ROLES

def can_view_patient(user, handoffs, care, case_id):
    """Server-side workspace access: org-wide coordination roles, or
    care-team membership. Default is deny."""
    if str(user.role_id) in ORG_WIDE_ROLES:
        return True
    return str(user.id) in effective_member_ids(handoffs, care, case_id)

def followed_case_ids(care, user_id):
    return {str(f["case_id"]) for f in care["follows"] if str(f["user_id"]) == str(user_id)}

def ensure_follow(care, user_id, case_id):
    if str(case_id) not in followed_case_ids(care, user_id):
        care["follows"].append({"user_id": str(user_id), "case_id": str(case_id), "followed_at": now_iso()})

def event_actor(e):
    """The user id who caused a history event, as a string, or None."""
    by = e.get("by")
    if isinstance(by, int) or (isinstance(by, str) and by.isdigit()):
        return str(by)
    if isinstance(by, str) and "→" in by:
        part = by.split("→")[-1].strip()
        return part if part.isdigit() else None
    return None

def _name_of(meta, uid):
    m = meta.get(str(uid)) if uid is not None else None
    return m["name"] if m else "Unknown"

def event_line(e, task, meta):
    """One concise line for a history event — the worklist summary line."""
    ev = e.get("event")
    if ev == "RECORD_ADDED":
        text = (e.get("text") or "").strip()
        return (text[:107] + "…") if len(text) > 110 else text
    if ev == "CREATED":
        return f"New: {task.get('event', '')}"
    if ev == "OWNERSHIP_TRANSFERRED":
        return f"Baton passed to {_name_of(meta, event_actor(e))} — {task.get('event', '')}"
    if ev == "ASSIGNMENT_ACKNOWLEDGED":
        return f"{_name_of(meta, event_actor(e))} acknowledged — {task.get('event', '')}"
    if ev == "HANDOFF_CANCELED":
        return f"Canceled: {e.get('reason', '')} — {task.get('event', '')}"
    if isinstance(ev, str) and ev.startswith("STATUS_CHANGED_TO_"):
        return f"{task.get('event', '')} — now {ev.replace('STATUS_CHANGED_TO_', '').replace('_', ' ').title()}"
    return task.get("event", "")

def event_section(e, task):
    if e.get("event") == "RECORD_ADDED":
        return RECORD_CATEGORY_SECTION.get(e.get("category", "GENERAL"), task_section(task))
    return task_section(task)

def patient_latest(tasks, meta):
    """The patient's most recent activity: {at, line, section, actor}."""
    best = None
    for h in tasks:
        for e in h.get("history", []):
            if best is None or e.get("at", "") > best["at"]:
                best = {
                    "at": e.get("at", ""),
                    "line": event_line(e, h, meta),
                    "section": event_section(e, h),
                    "actor": event_actor(e),
                }
    return best

def patient_section_statuses(tasks, meta):
    """Latest recorded status line per clinical section, for the strip."""
    out = {}
    for sec in ("LABS", "DIAGNOSTICS", "CONSULTS"):
        best = None
        for h in tasks:
            for e in h.get("history", []):
                if event_section(e, h) == sec and (best is None or e.get("at", "") > best["at"]):
                    best = {"at": e.get("at", ""), "line": event_line(e, h, meta)}
            if task_section(h) == sec:
                cand = {"at": h.get("updated_at", ""), "line": f"{h.get('event', '')} — {h.get('status', '').replace('_', ' ').title()}"}
                if best is None or cand["at"] > best["at"]:
                    best = cand
        out[sec] = best["line"] if best else None
    return out

def is_unread(care, user_id, case_id, tasks, meta):
    latest = patient_latest(tasks, meta)
    if not latest or not latest["at"]:
        return False
    if latest["actor"] is not None and str(latest["actor"]) == str(user_id):
        return False
    seen = care["read_state"].get(str(user_id), {}).get(str(case_id), "")
    return latest["at"] > seen

def mark_read(care, user_id, case_id, tasks, meta):
    latest = patient_latest(tasks, meta)
    if latest and latest["at"]:
        care["read_state"].setdefault(str(user_id), {})[str(case_id)] = latest["at"]

def state_version(handoffs, case_ids, meta):
    """A cheap change stamp for the polling refresh: any new activity on
    any watched patient changes the version."""
    parts = []
    patients = all_patients(handoffs)
    for cid in sorted(str(c) for c in case_ids):
        p = patients.get(cid)
        if p:
            latest = patient_latest(p["tasks"], meta)
            parts.append(f"{cid}:{(latest or {}).get('at', '')}")
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]

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
# Dashboard helpers
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

def display_roles():
    roles = dict(ROLE_MAP)
    for uid, u in USERS.items():
        roles[uid] = u.role_name
    return roles

def patient_summaries(handoffs, care, user, meta):
    """Enriched patient records for the worklist, newest activity first."""
    patients = all_patients(handoffs)
    followed = followed_case_ids(care, user.id)
    out = []
    for cid, p in patients.items():
        tasks = [enrich(h) for h in p["tasks"]]
        latest = patient_latest(tasks, meta)
        mine = cid in followed or any(
            str(h.get("owner")) == str(user.id) and h.get("status") in OPEN_STATUSES for h in tasks
        )
        out.append({
            **p,
            "tasks": tasks,
            "open_tasks": [h for h in tasks if h.get("status") in OPEN_STATUSES],
            "latest": latest,
            "unread": is_unread(care, user.id, cid, tasks, meta),
            "mine": mine,
            "can_view": can_view_patient(user, handoffs, care, cid),
            "strip": patient_section_statuses(tasks, meta),
            "member_ids": effective_member_ids(handoffs, care, cid),
        })
    out.sort(key=lambda p: (p["latest"] or {}).get("at", ""), reverse=True)
    return out

STATUS_FILTERS = {"NEW", "IN_PROGRESS", "ESCALATED", "COMPLETED", "STALE", "COMPLETIONS"}
FILTER_LABELS = {
    "NEW": "New",
    "IN_PROGRESS": "In Progress",
    "ESCALATED": "Escalated",
    "COMPLETED": "Completed",
    "STALE": "Waiting Too Long",
    "COMPLETIONS": "Completion Times",
}

@app.template_filter("fmt_minutes")
def fmt_minutes(m):
    if m is None:
        return "—"
    m = int(round(m))
    if m < 60:
        return f"{m} min"
    return f"{m // 60} h {m % 60:02d} min" if m % 60 else f"{m // 60} h"

def completion_stats(tasks):
    """Completion-time breakdown for completed tasks that carry both a
    creation and a completion timestamp."""
    rows = []
    for h in tasks:
        if h.get("status") != "COMPLETED":
            continue
        created = parse_ts(h.get("created_at"))
        done_at = None
        for e in h.get("history", []):
            if e["event"] == "STATUS_CHANGED_TO_COMPLETED":
                done_at = parse_ts(e["at"])
        if created and done_at:
            rows.append({"task": h, "minutes": (done_at - created).total_seconds() / 60,
                         "done_at": done_at.isoformat()})
    durations = sorted(r["minutes"] for r in rows)
    stats = {"count": len(rows), "rows": rows, "avg": None, "median": None, "min": None, "max": None}
    if durations:
        stats["avg"] = round(sum(durations) / len(durations))
        mid = len(durations) // 2
        stats["median"] = round(durations[mid] if len(durations) % 2 else (durations[mid - 1] + durations[mid]) / 2)
        stats["min"] = round(durations[0])
        stats["max"] = round(durations[-1])
    return stats

def build_worklist(handoffs, care, user, meta, q="", active_filter=None, unit_scope=False):
    """Shared view-model for Screen 1 and its refresh fragment.

    The home-page metric cards describe the signed-in clinician's own
    authorized universe — so the number on a card always matches what
    selecting it can show that clinician. (The Operations Board keeps
    unit-wide numbers.)"""
    summaries = patient_summaries(handoffs, care, user, meta)
    if unit_scope:
        # Operations Board drill-down scope: the whole unit. The board
        # route only honors a filter for unit-wide roles, and the patient
        # workspace behind every link still enforces membership itself.
        authorized_all = list(summaries)
    else:
        authorized_all = [p for p in summaries if p["can_view"]]
    scoped_tasks = [h for p in authorized_all for h in p["tasks"]]
    metrics = compute_metrics(scoped_tasks)
    if q:
        needle = q.lower()
        def matches(p):
            fields = [p.get("patient_name", ""), p.get("case_id", ""), p.get("context", "")]
            fields += [h.get("event", "") for h in p["tasks"]]
            for h in p["tasks"]:
                for key in ("owner", "initiator"):
                    m = meta.get(str(h.get(key)))
                    if m:
                        fields += [m["name"], m["role"]]
            return any(needle in str(f).lower() for f in fields)
        summaries = [p for p in summaries if matches(p)]
    authorized = [p for p in summaries if p["can_view"]]
    ctx = {
        "my_patients": [p for p in summaries if p["mine"]],
        "authorized": authorized,
        "authorized_all": authorized_all,
        "metrics": metrics,
        "active_filter": active_filter if active_filter in STATUS_FILTERS else None,
        "filter_kind": None,
        "filter_groups": [],
        "filter_task_count": 0,
        "filter_patient_count": 0,
        "completion": None,
        "completion_groups": [],
    }
    if active_filter == "COMPLETIONS":
        stats = completion_stats(scoped_tasks)
        by_patient = {}
        for row in stats["rows"]:
            by_patient.setdefault(str(row["task"]["case_id"]), []).append(row)
        ctx["filter_kind"] = "completions"
        ctx["completion"] = stats
        ctx["completion_groups"] = [
            {"patient": p, "rows": by_patient[p["case_id"]]}
            for p in authorized_all if p["case_id"] in by_patient
        ]
    elif active_filter in STATUS_FILTERS:
        def task_matches(h):
            if active_filter == "STALE":
                return bool(h.get("stale_level"))
            return h.get("status") == active_filter
        total = 0
        for p in authorized_all:
            ms = [h for h in p["tasks"] if task_matches(h)]
            if ms:
                ctx["filter_groups"].append(
                    {"patient": p, "tasks": ms, "section": task_section(ms[0])})
                total += len(ms)
        ctx["filter_kind"] = "status"
        ctx["filter_task_count"] = total
        ctx["filter_patient_count"] = len(ctx["filter_groups"])
    return ctx

# -----------------------------
# Screen 1 — My Patients (patient-centered home)
# -----------------------------

@app.route("/")
@login_required
def index():
    handoffs = load_handoffs()
    care = load_care()
    meta = user_meta()
    q = (request.args.get("q") or "").strip()
    active_filter = (request.args.get("filter") or "").upper() or None
    ctx = build_worklist(handoffs, care, current_user, meta, q=q, active_filter=active_filter)
    version = state_version(handoffs, [p["case_id"] for p in ctx["authorized_all"]], meta)
    return render_template(
        "index.html",
        **ctx,
        roles=display_roles(),
        users=USERS,
        user_meta=meta,
        q=q,
        total_count=len(all_patients(handoffs)),
        state_version=version,
        section_labels=SECTION_LABELS,
        filter_labels=FILTER_LABELS,
    )

@app.route("/fragments/worklist")
@login_required
def fragment_worklist():
    handoffs = load_handoffs()
    care = load_care()
    meta = user_meta()
    active_filter = (request.args.get("filter") or "").upper() or None
    ctx = build_worklist(handoffs, care, current_user, meta, q="", active_filter=active_filter)
    return render_template(
        "worklist_blocks.html",
        **ctx,
        roles=display_roles(),
        users=USERS,
        user_meta=meta,
        q="",
        section_labels=SECTION_LABELS,
        filter_labels=FILTER_LABELS,
    )

# -----------------------------
# Operations board (the original status view, preserved)
# -----------------------------

@app.route("/board")
@login_required
def board():
    all_handoffs = [enrich(h) for h in load_handoffs()]
    metrics = compute_metrics(all_handoffs)
    meta = user_meta()
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
    can_drill = unit_wide_access(current_user)
    board_filter = (request.args.get("filter") or "").upper() or None
    if not can_drill or q:
        board_filter = None
    ctx = {}
    if board_filter in STATUS_FILTERS or board_filter == "COMPLETIONS":
        ctx = build_worklist(load_handoffs(), load_care(), current_user, meta,
                             active_filter=board_filter, unit_scope=True)
    else:
        board_filter = None
    kwargs = dict(handoffs=handoffs, roles=display_roles(), users=USERS,
                  metrics=metrics, user_meta=meta, q=q, total_count=len(all_handoffs),
                  user=str(current_user.id), can_drill=can_drill,
                  board_filter=board_filter, section_labels=SECTION_LABELS,
                  filter_labels=FILTER_LABELS)
    kwargs.update(ctx)  # unit-scope ctx metrics are the board's own numbers
    return render_template("board.html", **kwargs)

# -----------------------------
# Screen 2 — Individual patient workspace
# -----------------------------

def build_patient_view(handoffs, care, user, case_id, meta):
    patients = all_patients(handoffs)
    p = patients.get(str(case_id))
    if p is None:
        return None
    tasks = [enrich(h) for h in p["tasks"]]
    # Consolidated timeline: every event from every task, chronological.
    timeline = []
    for h in tasks:
        for e in h.get("history", []):
            timeline.append({**e, "task": h, "section": event_section(e, h),
                             "line": event_line(e, h, meta), "actor": event_actor(e)})
    timeline.sort(key=lambda e: e.get("at", ""))
    sections = {sec: {"tasks": [], "records": []} for sec in SECTIONS}
    for h in tasks:
        sections[task_section(h)]["tasks"].append(h)
    for item in timeline:
        if item["event"] == "RECORD_ADDED":
            sections[item["section"]]["records"].append(item)
    accountability = [i for i in timeline if i["event"] != "RECORD_ADDED"]
    members = []
    for uid in sorted(effective_member_ids(handoffs, care, case_id), key=lambda x: int(x)):
        m = meta.get(uid)
        if m:
            members.append({"id": uid, **m})
    return {
        **p,
        "tasks": tasks,
        "open_tasks": [h for h in tasks if h.get("status") in OPEN_STATUSES],
        "timeline": timeline,
        "sections_data": sections,
        "accountability": accountability,
        "strip": patient_section_statuses(tasks, meta),
        "members": members,
        "latest": patient_latest(tasks, meta),
        "is_following": str(case_id) in followed_case_ids(care, user.id),
        "can_manage_team": str(user.role_id) in ORG_WIDE_ROLES,
    }

@app.route("/patient/<case_id>")
@login_required
def patient_page(case_id):
    handoffs = load_handoffs()
    care = load_care()
    meta = user_meta()
    if str(case_id) not in all_patients(handoffs):
        return "Patient not found", 404
    if not can_view_patient(current_user, handoffs, care, case_id):
        return "Unauthorized: you are not on this patient's care team", 403
    view = build_patient_view(handoffs, care, current_user, case_id, meta)
    # Opening the workspace marks the patient's activity as seen.
    mark_read(care, current_user.id, case_id, view["tasks"], meta)
    save_care(care)
    section = (request.args.get("section") or "").upper()
    if section not in SECTIONS and section != "HISTORY":
        section = "TASKS"
        latest = view["latest"]
        if latest and latest["section"] in ("LABS", "DIAGNOSTICS", "CONSULTS"):
            section = latest["section"]
    version = state_version(handoffs, [str(case_id)], meta)
    return render_template(
        "patient.html",
        p=view,
        roles=display_roles(),
        users=USERS,
        user_meta=meta,
        active_section=section,
        section_labels=SECTION_LABELS,
        sections=SECTIONS,
        state_version=version,
    )

@app.route("/fragments/patient/<case_id>")
@login_required
def fragment_patient(case_id):
    handoffs = load_handoffs()
    care = load_care()
    meta = user_meta()
    if str(case_id) not in all_patients(handoffs):
        return "Patient not found", 404
    if not can_view_patient(current_user, handoffs, care, case_id):
        return "Unauthorized", 403
    view = build_patient_view(handoffs, care, current_user, case_id, meta)
    section = (request.args.get("section") or "TASKS").upper()
    if section not in SECTIONS and section != "HISTORY":
        section = "TASKS"
    return render_template(
        "patient_sections.html",
        p=view,
        roles=display_roles(),
        users=USERS,
        user_meta=meta,
        active_section=section,
        section_labels=SECTION_LABELS,
        sections=SECTIONS,
    )

@app.route("/api/state")
@login_required
def api_state():
    """Change stamp + unread map for the polling refresh. The client only
    swaps content when this version moves — and never over a dirty form."""
    handoffs = load_handoffs()
    care = load_care()
    meta = user_meta()
    summaries = patient_summaries(handoffs, care, current_user, meta)
    authorized = [p for p in summaries if p["can_view"]]
    return {
        "version": state_version(handoffs, [p["case_id"] for p in authorized], meta),
        "unread": {p["case_id"]: p["unread"] for p in authorized},
        "patients": len(authorized),
    }

# -----------------------------
# Follow / care-team management
# -----------------------------

@app.route("/follow", methods=["POST"])
@login_required
def follow_patient():
    case_id = str(request.form.get("case_id") or "")
    handoffs = load_handoffs()
    care = load_care()
    if case_id not in all_patients(handoffs):
        return "Patient not found", 404
    if not can_view_patient(current_user, handoffs, care, case_id):
        return "Unauthorized: following requires care-team access", 403
    ensure_follow(care, current_user.id, case_id)
    save_care(care)
    return redirect(request.form.get("next") or url_for("index"))

@app.route("/unfollow", methods=["POST"])
@login_required
def unfollow_patient():
    case_id = str(request.form.get("case_id") or "")
    handoffs = load_handoffs()
    care = load_care()
    # Stop Following is a personal-list change only — but it must never
    # silently abandon an open task you still own on this patient.
    if owns_open_task(handoffs, case_id, current_user.id):
        flash("You still own an open task for this patient. Transfer or complete it before removing the patient from your list.")
        return redirect(request.form.get("next") or url_for("patient_page", case_id=case_id))
    care["follows"] = [
        f for f in care["follows"]
        if not (str(f["user_id"]) == str(current_user.id) and str(f["case_id"]) == case_id)
    ]
    save_care(care)
    return redirect(request.form.get("next") or url_for("index"))

@app.route("/team/add", methods=["POST"])
@login_required
def team_add():
    case_id = str(request.form.get("case_id") or "")
    new_member = str(request.form.get("user_id") or "")
    handoffs = load_handoffs()
    care = load_care()
    if case_id not in all_patients(handoffs):
        return "Patient not found", 404
    if not can_view_patient(current_user, handoffs, care, case_id):
        return "Unauthorized: only the care team can add members", 403
    if new_member not in USERS:
        return "Unknown user", 400
    added = care["members_added"].setdefault(case_id, [])
    if new_member not in [str(u) for u in added]:
        added.append(new_member)
    removed = care["members_removed"].setdefault(case_id, [])
    if new_member in [str(u) for u in removed]:
        removed.remove(new_member)
    ensure_follow(care, new_member, case_id)
    save_care(care)
    return redirect(url_for("patient_page", case_id=case_id))

@app.route("/team/remove", methods=["POST"])
@login_required
def team_remove():
    case_id = str(request.form.get("case_id") or "")
    target = str(request.form.get("user_id") or "")
    handoffs = load_handoffs()
    care = load_care()
    if case_id not in all_patients(handoffs):
        return "Patient not found", 404
    is_self = target == str(current_user.id)
    if not is_self and str(current_user.role_id) not in ORG_WIDE_ROLES:
        return "Unauthorized: only charge nurses and care coordinators can remove others", 403
    if owns_open_task(handoffs, case_id, target):
        flash("That clinician owns an open task for this patient and cannot be removed until it is transferred or completed.")
        return redirect(url_for("patient_page", case_id=case_id))
    removed = care["members_removed"].setdefault(case_id, [])
    if target not in [str(u) for u in removed]:
        removed.append(target)
    added = care["members_added"].setdefault(case_id, [])
    if target in [str(u) for u in added]:
        added.remove(target)
    save_care(care)
    if is_self:
        return redirect(url_for("index"))
    return redirect(url_for("patient_page", case_id=case_id))

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
    section = (request.form.get("section") or "").upper()
    if section not in SECTIONS:
        section = infer_section(event)
    context = (request.form.get("patient_context") or "").strip()

    # Assignment vs. acknowledgment: the owner holds the baton from the
    # moment of assignment, but the assignment counts as acknowledged
    # only when the owner confirms receipt. Self-assignment is
    # acknowledged by definition; anyone else must acknowledge.
    self_assigned = str(owner) == str(current_user.id)

    new_handoff = {
        "handoff_id": new_handoff_id(),
        "patient_name": patient_name,
        "case_id": case_id,
        "event": event,
        "section": section,
        "patient_context": context if context else None,
        "age": age if age else None,
        "sex": sex if sex in ("M", "F") else None,
        # The initiator is whoever is signed in and creates the handoff —
        # accountability starts with a real identity, not a dropdown.
        "initiator": int(current_user.id),
        "owner": int(owner),
        "status": "NEW",
        "acknowledged_at": ts if self_assigned else None,
        "acknowledged_by": int(current_user.id) if self_assigned else None,
        "created_at": ts,
        "updated_at": ts,
        "history": [
            {"at": ts, "event": "CREATED", "by": int(current_user.id)}
        ],
    }

    handoffs.append(new_handoff)
    save_handoffs(handoffs)

    care = load_care()
    ensure_follow(care, current_user.id, case_id)
    ensure_follow(care, int(owner), case_id)
    save_care(care)
    return redirect(url_for("index"))

# ===== WORKFLOW POLICY (single source of truth) =====

STATUSES = ["NEW", "IN_PROGRESS", "ESCALATED", "COMPLETED", "CANCELED"]

ALLOWED_STATUS_TRANSITIONS = {
    "NEW": {"IN_PROGRESS"},
    "IN_PROGRESS": {"ESCALATED", "COMPLETED"},
    "ESCALATED": {"IN_PROGRESS", "COMPLETED"},
    "COMPLETED": set(),
    "CANCELED": set(),
}

# Transfer rules
TRANSFER_ALLOWED_STATUSES = {"NEW", "IN_PROGRESS", "ESCALATED"}  # NOT COMPLETED / CANCELED
ALLOW_SELF_TRANSFER = False

# Enforcement rules
ONLY_OWNER_CAN_CHANGE_STATUS = True
ONLY_OWNER_CAN_TRANSFER = True  # strong default

# Cancellation: the owner, or a charge nurse / care coordinator, with a
# recorded reason. Handled by its own route — never a status dropdown.
CANCEL_ROLES = ORG_WIDE_ROLES

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

def can_cancel(user, handoff) -> bool:
    if handoff.get("status") not in TRANSFER_ALLOWED_STATUSES:
        return False
    return str(user.id) == str(handoff.get("owner")) or str(user.role_id) in CANCEL_ROLES

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
    # A transferred assignment is a NEW assignment for the receiver: the
    # baton moved, but acknowledgment has not happened yet.
    target["acknowledged_at"] = None
    target["acknowledged_by"] = None
    target["updated_at"] = now_iso()
    target["history"].append({
        "at": target["updated_at"],
        "event": "OWNERSHIP_TRANSFERRED",
        "by": f"{old_owner} → {new_owner}",
    })

    save_handoffs(handoffs)

    # Receiving the baton joins you to the patient's team and list.
    care = load_care()
    ensure_follow(care, int(new_owner), target["case_id"])
    save_care(care)
    return redirect(url_for("index"))

@app.route("/acknowledge", methods=["POST"])
@login_required
def acknowledge():
    """The owner confirms receipt of an assignment. Distinct from
    ownership itself: you can hold the baton before you've acknowledged,
    and the record shows both facts separately."""
    handoff_id = request.form.get("handoff_id")
    handoffs = load_handoffs()
    target = find_handoff(handoffs, handoff_id)
    if target is None:
        return "Handoff not found", 404
    if str(current_user.id) != str(target["owner"]):
        return "Unauthorized: Only the assigned owner can acknowledge", 403
    if target.get("acknowledged_at"):
        return redirect(request.form.get("next") or url_for("index"))
    ts = now_iso()
    target["acknowledged_at"] = ts
    target["acknowledged_by"] = int(current_user.id)
    target["updated_at"] = ts
    target["history"].append({"at": ts, "event": "ASSIGNMENT_ACKNOWLEDGED", "by": int(current_user.id)})
    save_handoffs(handoffs)
    return redirect(request.form.get("next") or url_for("index"))

@app.route("/cancel-handoff", methods=["POST"])
@login_required
def cancel_handoff():
    handoff_id = request.form.get("handoff_id")
    reason = (request.form.get("reason") or "").strip()
    handoffs = load_handoffs()
    target = find_handoff(handoffs, handoff_id)
    if target is None:
        return "Handoff not found", 404
    if not can_cancel(current_user, target):
        return "Unauthorized: Only the owner, a charge nurse, or a care coordinator can cancel", 403
    if not reason:
        return "A reason is required to cancel a handoff", 400
    if len(reason) > 300:
        return "Reason too long (300 characters max)", 400
    ts = now_iso()
    target["status"] = "CANCELED"
    target["updated_at"] = ts
    target["history"].append({
        "at": ts,
        "event": "HANDOFF_CANCELED",
        "by": int(current_user.id),
        "reason": reason,
    })
    save_handoffs(handoffs)
    return redirect(request.form.get("next") or url_for("index"))

# -----------------------------
# Record actions (any signed-in care team member)
# -----------------------------
# Real units chart collaboratively: several clinicians add orders and
# notes to the same patient. Those contributions belong ON the record —
# time-stamped and attributed — without moving the baton. Only the owner
# can change status or transfer ownership (above). Entries may carry a
# clinical category so the patient workspace can file them under Labs,
# Diagnostics, or Consultations; the entry always shows its author —
# clinical content here is manually recorded by a named clinician, and
# nothing in this application arrives from an EMR feed.

RECORD_TYPES = {"NOTE", "ORDER", "UPDATE"}

@app.route("/add-note", methods=["POST"])
@login_required
def add_note():
    handoff_id = request.form.get("handoff_id")
    note_type = (request.form.get("note_type") or "NOTE").upper()
    category = (request.form.get("category") or "GENERAL").upper()
    text = (request.form.get("text") or "").strip()

    if note_type not in RECORD_TYPES:
        return "Invalid record type", 400
    if category not in RECORD_CATEGORIES:
        return "Invalid record category", 400
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
        "category": category,
        "text": text,
        "by": int(current_user.id),
    })
    target["updated_at"] = ts

    save_handoffs(handoffs)
    return redirect(request.form.get("next") or url_for("index"))

if __name__ == "__main__":
    app.run(debug=os.environ.get("HANDOFF_DEBUG", "1") == "1")
