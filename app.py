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
from zoneinfo import ZoneInfo

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
# DEMO ONLY: demo accounts share the demo password "handoff123", except
# the clinical reviewer's individual UAT credential on this branch.
# Passwords are stored hashed, never in plain text. Production use requires
# real per-user credentials managed outside the codebase.

DEMO_PASSWORD = "handoff123"
UAT_REVIEWER_PASSWORD = "NinaUAT2026!"

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

def _make_user(user_id, username, name, role_id, password=DEMO_PASSWORD):
    return User(user_id, username, name, role_id, generate_password_hash(password))

USERS = {
    "1": _make_user("1", "dcarter", "Dr. Carter", "1"),
    "2": _make_user("2", "dwilliams", "Dr. Williams", "2"),
    "3": _make_user("3", "njohnson", "Nina Johnson", "8", password=UAT_REVIEWER_PASSWORD),
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

# Fictional demo badge numbers. Only the masked form (last two digits)
# is ever displayed, as the Directive 3.0 attribution standard requires.
STAFF_BADGES = {"1": "4417", "2": "2290", "3": "4821", "4": "3355",
                "5": "5108", "6": "6742", "7": "7819", "8": "9024"}

def user_meta():
    """Display metadata per user id: name, role, avatar initials + color."""
    return {
        uid: {
            "name": u.name,
            "role": u.role_name,
            "initials": initials_of(u.name),
            "color": _AVATAR_COLORS[(int(uid) - 1) % len(_AVATAR_COLORS)],
            "staff_id_masked": "\u2022\u2022" + STAFF_BADGES.get(str(uid), "00")[-2:],
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
    data.setdefault("dispositions", {})
    data.setdefault("snapshots", {})
    data.setdefault("notifications", [])
    data.setdefault("notif_state", {})
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
# The approved Directive 3.0 workspace: ten sections, one patient at a time.
WORKSPACE_SECTIONS = ["OVERVIEW", "HPI", "MEDICAL_HISTORY", "VITALS", "LABS",
                      "DIAGNOSTICS", "CONSULTS", "UPDATES", "TASKS", "HISTORY"]
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
                "dob": None,
                "mrn": None,
                "fin": None,
                "context": "",
                "tasks": [],
            }
            patients[cid] = p
        if not p["context"] and h.get("patient_context"):
            p["context"] = h["patient_context"]
        for _k in ("dob", "mrn", "fin"):
            if not p[_k] and h.get(_k):
                p[_k] = h[_k]
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

if os.environ.get("HANDOFF_SEED_DEMO") == "1" and not os.path.exists(care_file()):
    from seed_demo import build_seed_care
    save_care(build_seed_care())

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
    # No automatic inactivity flags in this build (removal decision,
    # 2026-10-23). The key stays for template compatibility, always "".
    handoff["stale_level"] = ""
    return handoff

def compute_metrics(handoffs):
    metrics = {"NEW": 0, "IN_PROGRESS": 0, "ESCALATED": 0, "COMPLETED": 0, "CANCELED": 0, "stale": 0}
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

# The approved Directive 3.0 experience has exactly four status
# categories. The inactivity / Tasks Overdue category was removed entirely by
# Derrick + Nina's decision (2026-10-23): no stale filter, no inactivity
# flags — elapsed time alone never marks a task.
STATUS_FILTERS = {"NEW", "IN_PROGRESS", "ESCALATED", "COMPLETED", "CANCELED", "COMPLETIONS"}
FILTER_LABELS = {
    "NEW": "New",
    "IN_PROGRESS": "In Progress",
    "ESCALATED": "Escalated",
    "COMPLETED": "Completed",
    "CANCELED": "Canceled",
    "COMPLETIONS": "Completion Times",
}

def fmt_ts_str(iso):
    """Exact display timestamp: 'Oct 23, 2026 \u00b7 4:57 PM EDT'.
    Relative time is supplementary only (added client-side); when the
    source time is missing the honest display is 'Not documented'."""
    dt = parse_ts(iso)
    if not dt:
        return "Not documented"
    local = dt.astimezone(ZoneInfo("America/New_York"))
    return local.strftime("%b %d, %Y \u00b7 %I:%M %p ") + (local.tzname() or "")

@app.template_filter("fmt_ts")
def fmt_ts(iso):
    return fmt_ts_str(iso)

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

def identifier_match(ident, needle):
    """Match a search string against DOB / MRN / FIN: full-string for the
    DOB as typed (MM/DD/YYYY), digit-substring for MRN/FIN and for the
    DOB's digits in either MMDDYYYY or YYYYMMDD order."""
    digits = "".join(ch for ch in (needle or "") if ch.isdigit())
    if len(digits) < 4:
        return False
    dob_digits = "".join(ch for ch in (ident.get("dob") or "") if ch.isdigit())
    iso = dob_digits[4:] + dob_digits[:4] if len(dob_digits) == 8 else ""
    return (digits in (ident.get("mrn") or "")
            or digits in (ident.get("fin") or "")
            or digits in dob_digits or digits in iso)

def build_worklist(handoffs, care, user, meta, q="", active_filter=None, unit_scope=False):
    """Shared view-model for Screen 1 and its refresh fragment.

    The home-page metric cards describe the signed-in clinician's own
    authorized universe — so the number on a card always matches what
    selecting it can show that clinician. (The Operations Board keeps
    unit-wide numbers.)"""
    summaries = patient_summaries(handoffs, care, user, meta)
    if unit_scope:
        # Operations Board drill-down scope for unit-wide roles: the
        # whole unit. Other clinicians drill into their authorized
        # patients only (unit_scope=False), and the patient workspace
        # behind every link still enforces membership itself.
        authorized_all = list(summaries)
    else:
        authorized_all = [p for p in summaries if p["can_view"]]
    scoped_tasks = [h for p in authorized_all for h in p["tasks"]]
    metrics = compute_metrics(scoped_tasks)
    if q:
        needle = q.lower()
        def matches(p):
            fields = [p.get("patient_name", ""), p.get("case_id", ""), p.get("context", ""),
                      p.get("dob", "") or "", p.get("mrn", "") or "", p.get("fin", "") or ""]
            fields += [h.get("event", "") for h in p["tasks"]]
            for h in p["tasks"]:
                for key in ("owner", "initiator"):
                    m = meta.get(str(h.get(key)))
                    if m:
                        fields += [m["name"], m["role"]]
            return identifier_match(p, needle) or any(needle in str(f).lower() for f in fields)
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
        notif_unread=notif_unread_count(current_user, handoffs, care, meta),
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
    raw = load_handoffs()
    care = load_care()
    # The board enforces the same access scope as every other surface:
    # a clinician sees the tasks of the patients they are authorized for.
    # Unit-wide roles (charge nurse, care coordinator) are authorized
    # for the whole unit, so their board is unchanged.
    visible = [h for h in raw
               if can_view_patient(current_user, raw, care, h.get("case_id"))]
    all_handoffs = [enrich(h) for h in visible]
    metrics = compute_metrics(all_handoffs)
    meta = user_meta()
    q = (request.args.get("q") or "").strip()
    handoffs = all_handoffs
    if q:
        needle = q.lower()
        def matches(h):
            fields = [h.get("patient_name", ""), h.get("case_id", ""), h.get("event", ""),
                      h.get("dob", "") or "", h.get("mrn", "") or "", h.get("fin", "") or ""]
            for key in ("owner", "initiator"):
                m = meta.get(str(h.get(key)))
                if m:
                    fields += [m["name"], m["role"]]
            return identifier_match(h, needle) or any(needle in str(f).lower() for f in fields)
        handoffs = [h for h in all_handoffs if matches(h)]
    # Every board card is clickable for every clinician (Derrick's
    # directive, 2026-10-23: "we made everything clickable"). What a
    # clinician drills INTO stays scoped: unit-wide roles see the whole
    # board; everyone else drills into their authorized patients only -
    # the same universe their board already shows.
    unit_wide = unit_wide_access(current_user)
    can_drill = True
    board_filter = (request.args.get("filter") or "").upper() or None
    if q:
        board_filter = None
    ctx = {}
    if board_filter in STATUS_FILTERS or board_filter == "COMPLETIONS":
        ctx = build_worklist(raw, care, current_user, meta,
                             active_filter=board_filter, unit_scope=unit_wide)
    else:
        board_filter = None
    kwargs = dict(handoffs=handoffs, roles=display_roles(), users=USERS,
                  metrics=metrics, user_meta=meta, q=q, total_count=len(all_handoffs),
                  user=str(current_user.id), can_drill=can_drill, unit_wide=unit_wide,
                  notif_unread=notif_unread_count(current_user, raw, care, meta),
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
        "disposition": enrich_disposition(care, case_id, meta),
        "snapshot": care["snapshots"].get(str(case_id)) or {},
        "updates": [i for i in timeline if i["event"] == "RECORD_ADDED"],
        "composer_task_id": (max(tasks, key=lambda h: h.get("updated_at", "")) or {}).get("handoff_id") if tasks else None,
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
    if section not in WORKSPACE_SECTIONS:
        section = "OVERVIEW"
    version = state_version(handoffs, [str(case_id)], meta)
    return render_template(
        "patient.html",
        p=view,
        roles=display_roles(),
        users=USERS,
        user_meta=meta,
        active_section=section,
        section_labels=SECTION_LABELS,
        sections=WORKSPACE_SECTIONS,
        hl=request.args.get("hl") or "",
        notif_unread=notif_unread_count(current_user, handoffs, care, meta),
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
    if section not in WORKSPACE_SECTIONS:
        section = "TASKS"
    return render_template(
        "patient_sections.html",
        p=view,
        roles=display_roles(),
        users=USERS,
        user_meta=meta,
        active_section=section,
        section_labels=SECTION_LABELS,
        sections=WORKSPACE_SECTIONS,
        hl=request.args.get("hl") or "",
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
# Disposition & responsibility transfer (Directive 3.0)
# -----------------------------
# A patient's disposition is staged, never a single label: intent,
# order placement, acceptance, and completed disposition are separate
# facts with their own attribution. The current responsible clinician is
# a distinct record — a bed request or an acceptance NEVER moves it.
# Responsibility transfers only at sign-off, and sign-off requires a
# recorded acceptance (the institution-approved transfer criteria this
# build can enforce; the criteria themselves remain hospital policy).

def add_notification(care, case_id, kind, text, by_user, ack_required=False):
    care["notifications"].append({
        "id": new_handoff_id(),
        "case_id": str(case_id),
        "kind": kind,
        "text": text,
        "by": str(by_user),
        "at": now_iso(),
        "ack_required": bool(ack_required),
    })

def _who(meta, uid):
    m = meta.get(str(uid)) if uid is not None else None
    return f"{m['name']} · {m['role']}" if m else None

def enrich_disposition(care, case_id, meta):
    d = care["dispositions"].get(str(case_id))
    if not d:
        return None
    ir = d.get("intent_recorded")
    stages = [{
        "label": "Intent recorded \u2014 " + ("Intent to admit" if d.get("intent") == "ADMIT" else "Intent to discharge"),
        "state": "done" if ir else "current",
        "detail": (f"Intended service: {d.get('service', '')}" + (f" \u00b7 By {_who(meta, ir['by'])} \u00b7 {fmt_ts_str(ir['at'])}" if ir else "")),
    }]
    if d.get("intent") == "ADMIT":
        op = d.get("order_placed")
        stages.append({
            "label": "Order placement \u2014 admission order / bed request recorded",
            "state": "done" if op else ("current" if ir else "pending"),
            "detail": (f"By {_who(meta, op['by'])}" + (f" \u00b7 Entered by {_who(meta, op.get('entered_by'))}" if op.get("entered_by") else "") + f" \u00b7 {fmt_ts_str(op['at'])}") if op else "Not yet recorded",
        })
        ac = d.get("acceptance")
        stages.append({
            "label": "Receiving service acceptance",
            "state": "done" if ac else ("current" if op else "pending"),
            "detail": (f"Accepted by {ac.get('acceptor_label', '')}" + (f" \u00b7 Recorded by {_who(meta, ac.get('recorded_by'))}" if ac.get("recorded_by") else "") + f" \u00b7 {fmt_ts_str(ac['at'])}") if ac else "Pending",
        })
    co = d.get("completed")
    stages.append({
        "label": "Completed disposition \u2014 responsibility transferred at sign-off" if d.get("intent") == "ADMIT" else "Completed disposition \u2014 discharge completed",
        "state": "done" if co else "pending",
        "detail": (f"Signed off by {_who(meta, co.get('signed_off_by'))}" + (f" \u00b7 Responsibility accepted by {_who(meta, co.get('accepted_by'))}" if co.get("accepted_by") else "") + f" \u00b7 {fmt_ts_str(co['at'])}") if co else "Not completed",
    })
    return {"record": d, "stages": stages,
            "responsible_label": _who(meta, d.get("responsible")),
            "receiving": d.get("service")}

# -----------------------------
# Notifications Center (Directive 3.0)
# -----------------------------
# One feed per clinician: stored disposition/transfer notifications plus
# the meaningful events on their authorized patients' histories. States
# are kept separate: unread \u2260 read \u2260 acknowledged. Viewing never
# counts as acknowledgment.

DERIVED_NOTIF_KINDS = {
    "STATUS_CHANGED_TO_ESCALATED": ("Task escalated", True),
    "RECORD_ADDED": ("New record", False),
    "STATUS_CHANGED_TO_COMPLETED": ("Task completed", False),
    "HANDOFF_CANCELED": ("Handoff canceled", False),
}
STORED_NOTIF_LABELS = {
    "BED_REQUEST": "Admission order \u2014 bed request",
    "DISPOSITION_INTENT": "Disposition intent recorded",
    "ACCEPTANCE": "Receiving acceptance recorded",
    "TRANSFER_COMPLETE": "Responsibility transferred \u2014 sign-off complete",
    "DISCHARGE_COMPLETE": "Discharge completed",
    "SIMULATION": "Simulated incoming alert",
}

def notification_feed(user, handoffs, care, meta):
    items = []
    patients = all_patients(handoffs)
    for n in care["notifications"]:
        cid = str(n.get("case_id"))
        if str(n.get("by")) == str(user.id):
            continue
        if cid in patients and can_view_patient(user, handoffs, care, cid):
            items.append({
                "key": "n:" + n["id"], "kind": n.get("kind"),
                "label": STORED_NOTIF_LABELS.get(n.get("kind"), n.get("kind", "Notification")),
                "case_id": cid, "patient_name": patients[cid]["patient_name"],
                "text": n.get("text", ""), "by": n.get("by"), "at": n.get("at", ""),
                "ack_required": bool(n.get("ack_required")),
                "section": n.get("section") or "OVERVIEW", "hl": n.get("hl") or "",
            })
    for cid, p in patients.items():
        if not can_view_patient(user, handoffs, care, cid):
            continue
        for h in p["tasks"]:
            for e in h.get("history", []):
                actor = event_actor(e)
                if actor is not None and str(actor) == str(user.id):
                    continue
                ev = e.get("event")
                kind = label = None
                ack = False
                if ev in DERIVED_NOTIF_KINDS:
                    kind, label, ack = ev, DERIVED_NOTIF_KINDS[ev][0], DERIVED_NOTIF_KINDS[ev][1]
                elif ev == "OWNERSHIP_TRANSFERRED" and actor is not None:
                    if str(actor) == str(user.id):
                        kind, label, ack = ev, "Baton received", True
                    else:
                        kind, label = ev, "Baton moved"
                elif ev == "CREATED" and str(h.get("owner")) == str(user.id):
                    kind, label, ack = ev, "New assignment", True
                if not kind:
                    continue
                if ev == "RECORD_ADDED":
                    deep_section = event_section(e, h)
                elif ev == "HANDOFF_CANCELED":
                    deep_section = "HISTORY"
                else:
                    deep_section = "TASKS"
                items.append({
                    "key": f"h:{h['handoff_id']}:{ev}:{e.get('at', '')}",
                    "kind": kind, "label": label,
                    "case_id": cid, "patient_name": p["patient_name"],
                    "text": event_line(e, h, meta), "by": actor, "at": e.get("at", ""),
                    "ack_required": ack,
                    "section": deep_section, "hl": e.get("at", ""),
                })
    state = care["notif_state"].get(str(user.id), {"read": [], "ack": []})
    for it in items:
        it["read"] = it["key"] in state.get("read", [])
        it["acked"] = it["key"] in state.get("ack", [])
    items.sort(key=lambda x: x.get("at", ""), reverse=True)
    return items[:40]

def notif_unread_count(user, handoffs, care, meta):
    return sum(1 for it in notification_feed(user, handoffs, care, meta) if not it["read"])

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
# Disposition actions (Directive 3.0)
# -----------------------------

def _disposition_guard(case_id):
    """Shared checks for disposition actions. Returns (handoffs, care,
    record) or an error response tuple via _DispError."""
    handoffs = load_handoffs()
    care = load_care()
    if str(case_id) not in all_patients(handoffs):
        return None, None, ("Patient not found", 404)
    if not can_view_patient(current_user, handoffs, care, case_id):
        return None, None, ("Unauthorized: you are not on this patient's care team", 403)
    return handoffs, care, care["dispositions"].get(str(case_id))

@app.route("/disposition/intent", methods=["POST"])
@login_required
def disposition_intent():
    case_id = str(request.form.get("case_id") or "")
    intent = (request.form.get("intent") or "").upper()
    service = (request.form.get("service") or "").strip()
    handoffs, care, record = _disposition_guard(case_id)
    if handoffs is None:
        return record
    if intent not in ("ADMIT", "DISCHARGE"):
        return "Invalid disposition intent", 400
    if not service:
        return "The intended service or destination is required", 400
    if record and record.get("completed"):
        return "This disposition is already completed", 400
    ts = now_iso()
    if record is None:
        record = {"intent": intent, "service": service,
                  "intent_recorded": {"by": str(current_user.id), "at": ts},
                  "order_placed": None, "acceptance": None, "completed": None,
                  "responsible": str(current_user.id)}
        care["dispositions"][case_id] = record
    else:
        record["intent"] = intent
        record["service"] = service
        record["intent_recorded"] = {"by": str(current_user.id), "at": ts}
        if not record.get("responsible"):
            record["responsible"] = str(current_user.id)
    add_notification(care, case_id, "DISPOSITION_INTENT",
                     f"{'Intent to admit' if intent == 'ADMIT' else 'Intent to discharge'} recorded \u2014 {service}.",
                     current_user.id)
    save_care(care)
    flash("Disposition intent recorded.")
    return redirect(url_for("patient_page", case_id=case_id))

@app.route("/disposition/bed-request", methods=["POST"])
@login_required
def disposition_bed_request():
    case_id = str(request.form.get("case_id") or "")
    handoffs, care, record = _disposition_guard(case_id)
    if handoffs is None:
        return record
    if not record or record.get("intent") != "ADMIT":
        return "A bed request requires a recorded Intent to admit", 400
    if record.get("order_placed"):
        return "A bed request is already recorded for this patient", 400
    record["order_placed"] = {"by": str(current_user.id), "entered_by": None, "at": now_iso()}
    # The rule, enforced: recording a bed request does NOT change who is
    # responsible for this patient.
    add_notification(care, case_id, "BED_REQUEST",
                     f"Admission order recorded \u2014 bed request (bed-slip) for {record.get('service', '')}. A bed request does not transfer responsibility.",
                     current_user.id, ack_required=True)
    save_care(care)
    flash("Bed request recorded. Responsibility remains with the current responsible clinician.")
    return redirect(url_for("patient_page", case_id=case_id))

@app.route("/disposition/acceptance", methods=["POST"])
@login_required
def disposition_acceptance():
    case_id = str(request.form.get("case_id") or "")
    acceptor = (request.form.get("acceptor_label") or "").strip()
    service = (request.form.get("service") or "").strip()
    handoffs, care, record = _disposition_guard(case_id)
    if handoffs is None:
        return record
    if not record or record.get("intent") != "ADMIT" or not record.get("order_placed"):
        return "Acceptance requires a recorded bed request first", 400
    if record.get("acceptance"):
        return "Acceptance is already recorded for this patient", 400
    if not acceptor:
        return "Name who accepted (clinician or service admissions)", 400
    record["acceptance"] = {"recorded_by": str(current_user.id), "acceptor_label": acceptor,
                            "service": service or record.get("service", ""), "at": now_iso()}
    add_notification(care, case_id, "ACCEPTANCE",
                     f"Receiving acceptance recorded \u2014 {acceptor} ({service or record.get('service', '')}). Sign-off still pending; responsibility has not transferred.",
                     current_user.id)
    save_care(care)
    flash("Acceptance recorded. Responsibility still has not transferred \u2014 sign-off is the transfer point.")
    return redirect(url_for("patient_page", case_id=case_id))

@app.route("/disposition/sign-off", methods=["POST"])
@login_required
def disposition_sign_off():
    case_id = str(request.form.get("case_id") or "")
    new_responsible = str(request.form.get("new_responsible") or "")
    handoffs, care, record = _disposition_guard(case_id)
    if handoffs is None:
        return record
    if not record or record.get("intent") != "ADMIT":
        return "Sign-off applies to an Intent to admit disposition", 400
    if not record.get("acceptance"):
        return "Sign-off requires a recorded receiving acceptance \u2014 responsibility cannot transfer before acceptance", 400
    if record.get("completed"):
        return "This disposition is already completed", 400
    if str(current_user.id) != str(record.get("responsible")) and str(current_user.role_id) not in ORG_WIDE_ROLES:
        return "Only the current responsible clinician (or a charge nurse / care coordinator) can sign off", 403
    if new_responsible not in USERS:
        return "Choose the clinician accepting responsibility", 400
    record["completed"] = {"signed_off_by": str(current_user.id), "accepted_by": new_responsible, "at": now_iso()}
    record["responsible"] = new_responsible
    add_notification(care, case_id, "TRANSFER_COMPLETE",
                     "Responsibility transferred at sign-off under institution-approved transfer criteria.",
                     current_user.id, ack_required=True)
    save_care(care)
    flash("Sign-off complete \u2014 responsibility has transferred and the transfer is on the record.")
    return redirect(url_for("patient_page", case_id=case_id))

@app.route("/disposition/complete", methods=["POST"])
@login_required
def disposition_complete():
    case_id = str(request.form.get("case_id") or "")
    handoffs, care, record = _disposition_guard(case_id)
    if handoffs is None:
        return record
    if not record or record.get("intent") != "DISCHARGE":
        return "This completion applies to an Intent to discharge disposition", 400
    if record.get("completed"):
        return "This disposition is already completed", 400
    if str(current_user.id) != str(record.get("responsible")) and str(current_user.role_id) not in ORG_WIDE_ROLES:
        return "Only the current responsible clinician (or a charge nurse / care coordinator) can complete the discharge", 403
    record["completed"] = {"signed_off_by": str(current_user.id), "accepted_by": None, "at": now_iso()}
    add_notification(care, case_id, "DISCHARGE_COMPLETE",
                     "Discharge completed and recorded by the responsible clinician.",
                     current_user.id)
    save_care(care)
    flash("Discharge completed and recorded.")
    return redirect(url_for("patient_page", case_id=case_id))

# -----------------------------
# Notifications Center routes
# -----------------------------

@app.route("/notifications")
@login_required
def notifications_page():
    handoffs = load_handoffs()
    care = load_care()
    meta = user_meta()
    items = notification_feed(current_user, handoffs, care, meta)
    # Opening the center marks items read \u2014 read is not acknowledgment;
    # ack-required items keep their Acknowledge button until acked.
    state = care["notif_state"].setdefault(str(current_user.id), {"read": [], "ack": []})
    read_set = set(state.get("read", []))
    for it in items:
        read_set.add(it["key"])
    state["read"] = sorted(read_set)
    save_care(care)
    return render_template("notifications.html", items=items, user_meta=meta,
                           roles=display_roles(), users=USERS)

@app.route("/notifications/simulate", methods=["POST"])
@login_required
def notifications_simulate():
    """Inject one clearly-labeled simulated incoming alert for the
    signed-in clinician (Directive 3.0 reviewer feature): it lands in the
    Notifications Center like a real alert, deep-links to the patient's
    latest record, and is marked SIMULATION everywhere it appears."""
    handoffs = load_handoffs()
    care = load_care()
    meta = user_meta()
    authorized = [p for p in patient_summaries(handoffs, care, current_user, meta) if p["can_view"]]
    if not authorized:
        flash("No authorized patients to simulate an update for.")
        return redirect(url_for("notifications_page"))
    p = authorized[0]
    latest = p["latest"] or {}
    add_notification(care, p["case_id"], "SIMULATION",
                     f"SIMULATION \u2014 incoming update for {p['patient_name']}: {latest.get('line', 'new activity recorded')}",
                     "0")
    care["notifications"][-1]["section"] = latest.get("section", "TASKS")
    care["notifications"][-1]["hl"] = latest.get("at", "")
    save_care(care)
    flash("Simulated incoming alert added to your Notifications Center.")
    return redirect(url_for("notifications_page"))

@app.route("/notifications/ack", methods=["POST"])
@login_required
def notifications_ack():
    key = (request.form.get("key") or "").strip()
    care = load_care()
    state = care["notif_state"].setdefault(str(current_user.id), {"read": [], "ack": []})
    ack_set = set(state.get("ack", []))
    if key:
        ack_set.add(key)
    state["ack"] = sorted(ack_set)
    save_care(care)
    return redirect(url_for("notifications_page"))

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

    # Itemized completion (Directive 3.0): a task is never just "Completed".
    # Completing requires a documented outcome, and the record keeps what
    # was completed, who completed it (with role), when, and the outcome.
    # Completing a task never changes the patient's disposition.
    outcome = None
    if new_status == "COMPLETED":
        outcome = (request.form.get("outcome") or "").strip()
        if not outcome:
            return "A documented outcome is required to complete a handoff", 400
        if len(outcome) > 500:
            return "Outcome too long (500 characters max)", 400

    target["status"] = new_status
    target["updated_at"] = now_iso()
    event = {
        "at": target["updated_at"],
        "event": f"STATUS_CHANGED_TO_{new_status}",
        "by": int(current_user.id),
    }
    if outcome is not None:
        event["outcome"] = outcome
        target["completion"] = {
            "by": int(current_user.id),
            "role": current_user.role_name,
            "at": target["updated_at"],
            "outcome": outcome,
        }
    target["history"].append(event)

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
    # Contribution requires authorization (policy, 2026-10-22): verified
    # care-team membership or unit-wide organizational access. Submitting
    # a note never confers membership.
    if not can_view_patient(current_user, handoffs, load_care(), target.get("case_id")):
        return "You are not on this patient's care team", 403

    # Two-identifier rule (Directive 3.0): documenting care requires the
    # clinician to confirm two patient identifiers — name plus DOB/MRN —
    # for THIS patient. Enforced here, server-side, on every record entry.
    if request.form.get("id_confirm_name") != "on" or request.form.get("id_confirm_dob") != "on":
        return "Two patient identifiers must be confirmed before documenting care", 400

    ts = now_iso()
    entry = {
        "at": ts,
        "event": "RECORD_ADDED",
        "type": note_type,
        "category": category,
        "text": text,
        "by": int(current_user.id),
        "id_confirmed": True,
    }
    performed_by = (request.form.get("performed_by") or "").strip()
    if performed_by.isdigit() and performed_by in USERS:
        # The recorder explicitly identified who performed the activity;
        # it is stored as its own fact, never merged with the recorder.
        entry["performed_by"] = performed_by
        entry["performed_at"] = ts
    target["history"].append(entry)
    target["updated_at"] = ts

    save_handoffs(handoffs)
    return redirect(request.form.get("next") or url_for("index"))


# -----------------------------
# Vital signs: entry + correction (Directive 3.0, Derrick 2026-10-23)
# -----------------------------
# The Vitals pane is a working documentation surface, not a display.
# "Measured by" and "Recorded by" are independent fields: the recorder
# is always the authenticated user; the measurer is documented only
# when actually known — never assumed from team membership. For an
# existing entry whose measurer was never established, an authorized
# clinician may document it later as an attributed, timestamped
# amendment; the original entry is preserved untouched.

def _parse_local_dt(raw):
    """A datetime-local form value, interpreted as Eastern local time."""
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return "INVALID"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("America/New_York"))
    return dt.astimezone(timezone.utc).isoformat()


def _vitals_guard(case_id):
    handoffs = load_handoffs()
    care = load_care()
    if case_id not in all_patients(handoffs):
        return None, None, ("Patient not found", 404)
    if not can_view_patient(current_user, handoffs, care, case_id):
        return None, None, ("You are not on this patient's care team", 403)
    if request.form.get("id_confirm_name") != "on" or request.form.get("id_confirm_dob") != "on":
        return None, None, ("Two patient identifiers must be confirmed before documenting care", 400)
    return handoffs, care, None


def _file_record(handoffs, case_id, text, performed_by=None):
    tasks = [h for h in handoffs if str(h.get("case_id")) == str(case_id)]
    if not tasks:
        return
    target = max(tasks, key=lambda h: h.get("updated_at", ""))
    entry = {"at": now_iso(), "event": "RECORD_ADDED", "type": "UPDATE",
             "category": "GENERAL", "text": text, "by": int(current_user.id),
             "id_confirmed": True}
    if performed_by:
        entry["performed_by"] = performed_by
        entry["performed_at"] = entry["at"]
    target["history"].append(entry)
    target["updated_at"] = entry["at"]


@app.route("/vitals/add", methods=["POST"])
@login_required
def vitals_add():
    case_id = str(request.form.get("case_id") or "")
    handoffs, care, err = _vitals_guard(case_id)
    if err:
        return err
    def _f(name):
        return (request.form.get(name) or "").strip()
    bp, hr, rr, spo2, temp = _f("bp"), _f("hr"), _f("rr"), _f("spo2"), _f("temp")
    if not (bp and hr and rr and spo2 and temp):
        return "All vital-sign values are required", 400
    measured_by = _f("measured_by")
    if measured_by and not (measured_by.isdigit() and measured_by in USERS):
        return "Invalid measurer", 400
    measured_at = _parse_local_dt(_f("measured_at"))
    if measured_at == "INVALID":
        return "Invalid measurement time", 400
    ts = now_iso()
    entry = {"bp": bp, "hr": hr, "rr": rr, "spo2": spo2, "temp": temp,
             "by": str(current_user.id), "at": ts, "source": "Manually entered"}
    if measured_by:
        entry["performed_by"] = measured_by
        entry["performed_at"] = measured_at or ts
    snap = care["snapshots"].setdefault(case_id, {})
    snap.setdefault("vitals", []).append(entry)
    meta = user_meta()
    measurer = meta.get(measured_by, {}).get("name") if measured_by else "Not documented"
    _file_record(handoffs, case_id,
                 f"Vital signs recorded — BP {bp} · HR {hr} · RR {rr} · SpO₂ {spo2} · Temp {temp}. "
                 f"Measured by: {measurer}.")
    save_handoffs(handoffs)
    save_care(care)
    flash("Vital signs recorded — measurer and recorder are documented separately.")
    return redirect(url_for("patient_page", case_id=case_id, section="VITALS"))


@app.route("/vitals/amend", methods=["POST"])
@login_required
def vitals_amend():
    case_id = str(request.form.get("case_id") or "")
    entry_at = (request.form.get("entry_at") or "").strip()
    handoffs, care, err = _vitals_guard(case_id)
    if err:
        return err
    performed_by = (request.form.get("performed_by") or "").strip()
    if not (performed_by.isdigit() and performed_by in USERS):
        return "Choose the clinician who actually measured these vital signs", 400
    performed_at = _parse_local_dt((request.form.get("performed_at") or "").strip())
    if performed_at == "INVALID":
        return "Invalid measurement time", 400
    reason = (request.form.get("reason") or "").strip()
    if not reason:
        return "A reason is required to amend a clinical entry", 400
    if len(reason) > 300:
        return "Reason too long (300 characters max)", 400
    snap = care["snapshots"].get(case_id) or {}
    target = next((v for v in snap.get("vitals", []) if v.get("at") == entry_at), None)
    if target is None:
        return "Vital-sign entry not found", 404
    ts = now_iso()
    target.setdefault("amendments", []).append({
        "kind": "MEASURER_DOCUMENTED",
        "performed_by": performed_by,
        "performed_at": performed_at,
        "by": str(current_user.id), "at": ts, "reason": reason,
    })
    meta = user_meta()
    measurer = meta.get(performed_by, {}).get("name", "Unknown")
    _file_record(handoffs, case_id,
                 f"Correction — measurer documented for the vital-sign set recorded "
                 f"{fmt_ts_str(target.get('at'))}: {measurer}. Reason: {reason} "
                 f"Original entry preserved.")
    save_handoffs(handoffs)
    save_care(care)
    flash("Measurer documented as an amendment — the original entry is preserved.")
    return redirect(url_for("patient_page", case_id=case_id, section="VITALS"))


if __name__ == "__main__":
    app.run(debug=os.environ.get("HANDOFF_DEBUG", "1") == "1")
