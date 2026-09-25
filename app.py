from flask import Flask, render_template, request, redirect, url_for
import json
import os
from datetime import datetime, timezone
app = Flask(__name__)
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
    "7": "Case Manager"
}

def role_label(role_id):
    return ROLE_MAP.get(str(role_id), f"Role {role_id}")

DATA_FILE = os.path.join(
    os.path.dirname(__file__),
    "handoff",
    "prototype",
    "handoffs.json"
)

def load_handoffs():
    with open(DATA_FILE, "r") as f:
        return json.load(f)
    
def save_handoffs(handoffs):
    with open(DATA_FILE, "w") as f:
        json.dump(handoffs, f, indent=2)

@app.route("/")
def index():
    handoffs = load_handoffs()
    return render_template("index.html", handoffs=handoffs, roles=ROLE_MAP)

   
@app.route('/create-handoff', methods=['POST'])
def create_handoff():
    patient_name = request.form.get("patient_name")
    case_id = request.form.get("case_id")
    event = request.form.get("event")
    initiator = request.form.get("initiator")
    owner = request.form.get("owner")

    print("CREATE HANDOFF:", patient_name, case_id, event, initiator, owner)

    if not patient_name or not case_id or not event or not initiator or not owner:
        print("FORM ERROR:", patient_name, case_id, event, initiator, owner)
        return "Missing required fields — check all inputs", 400
    handoffs = load_handoffs()

    handoff_id = datetime.utcnow().strftime("%Y%m%d%H%M%S")

    new_handoff = {
        "handoff_id": handoff_id,
        "patient_name": patient_name,
        "case_id": case_id,
        "event": event,
        "initiator": int(initiator) if initiator else None,
        "owner": int(owner) if owner else None,
        "status": "NEW",
        "updated_at": datetime.utcnow().isoformat(),
        "history": [
            {
                "at": datetime.utcnow().isoformat(),
                "event": "CREATED",
                "by": int(initiator)
            }
        ]
    }

    handoffs.append(new_handoff)
    save_handoffs(handoffs)

    return redirect(url_for("index"))
    

   
    # ===== WORKFLOW POLICY (single source of truth) =====

STATUSES = ["NEW", "IN_PROGRESS", "ESCALATED", "COMPLETED"]

ALLOWED_STATUS_TRANSITIONS = {
    "NEW": {"IN_PROGRESS"},
    "IN_PROGRESS": {"ESCALATED", "COMPLETED"},
    "ESCALATED": {"IN_PROGRESS"},
    "COMPLETED": set(),
}

# Transfer rules
TRANSFER_ALLOWED_STATUSES = {"CREATED", "IN_PROGRESS", "BLOCKED"}  # NOT COMPLETED
ALLOW_SELF_TRANSFER = False

# Enforcement rules
ONLY_OWNER_CAN_CHANGE_STATUS = True
ONLY_OWNER_CAN_TRANSFER = True  # strong default
# Role permissions for status changes
ROLE_STATUS_PERMISSIONS = {
    "1": {"CREATED", "IN_PROGRESS"},      # Registered Nurse
    "4": {"IN_PROGRESS", "BLOCKED"},      # Charge Nurse
    "5": {"COMPLETED"}                    # Physician
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
@app.route("/update-status", methods=["POST"])
def update_status():
    handoff_id = request.form.get("handoff_id")
    new_status = request.form.get("status")
    acting_user = request.form.get("acting_user")

    handoffs = load_handoffs()

    target = None
    for h in handoffs:
        if h["handoff_id"] == handoff_id:
            target = h
            break

    # If no matching handoff found
    if target is None:
        return "Handoff not found", 404

    old_status = target["status"]
    current_owner = target["owner"]

    # 🔒 Owner-only enforcement
    if acting_user != current_owner:
        return "Unauthorized: Only current owner can change status", 403
    # Role permission enforcement
    allowed_statuses = ROLE_STATUS_PERMISSIONS.get(acting_user, set())

    if new_status not in allowed_statuses:
        return "Role not allowed to set this status", 403

    # Validate workflow
    if not can_change_status(old_status, new_status):
        return f"Invalid status transition: {old_status} -> {new_status}", 400

    # Apply change
    target["status"] = new_status
    target["updated_at"] = datetime.utcnow().isoformat()
    target["history"].append({
        "at": target["updated_at"],
        "event": f"STATUS_CHANGED_TO_{new_status}",
        "by": acting_user
    })

    save_handoffs(handoffs)
    return redirect(url_for("index"))

@app.route("/transfer-owner", methods=["POST"])
def transfer_owner():
    handoff_id = request.form["handoff_id"]
    new_owner = request.form["new_owner"]

    handoffs = load_handoffs()
    now = datetime.now(timezone.utc) .isoformat()

    for h in handoffs:
        if h["handoff_id"] == handoff_id:
            old_owner = h["owner"]
            h["owner"] = new_owner
            h["updated_at"] = now
            h["history"].append({
                "at": now,
                "event": "OWNERSHIP_TRANSFERRED",
                "by": f"{old_owner} → {new_owner}"
            })
            break

    save_handoffs(handoffs)
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True)
