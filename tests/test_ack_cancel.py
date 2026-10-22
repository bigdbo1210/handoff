"""
Assignment acknowledgment + cancellation (Assessment #002).

Ownership and acknowledgment are different facts:
  - the owner holds the baton from the moment of assignment;
  - the assignment is acknowledged only when the owner confirms receipt.
Self-assignment is acknowledged at creation; assigning or transferring
to someone else starts unacknowledged, and transferring RESETS the
acknowledgment — the new owner has not confirmed anything yet.

Cancellation is its own action (never a status-dropdown value): the
owner, a charge nurse, or a care coordinator may cancel an open handoff,
and a reason is always recorded in the audit history.

Run:  python tests/test_ack_cancel.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as handoff_app
from seed_demo import build_seed_handoffs

passed = failed = 0

def check(label, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        print(f"  FAIL  {label}")

def login(username):
    client = handoff_app.app.test_client()
    resp = client.post("/login", data={"username": username, "password": "handoff123"})
    assert resp.status_code == 302, username
    return client

def get(hid):
    return handoff_app.find_handoff(handoff_app.load_handoffs(), hid)

def main():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    handoff_app.DATA_FILE = path
    care_path = handoff_app.care_file()
    if os.path.exists(care_path):
        os.unlink(care_path)
    handoff_app.save_handoffs(build_seed_handoffs())

    carter = login("dcarter")
    nina = login("njohnson")

    print("== Acknowledgment lifecycle ==")
    r = carter.post("/create-handoff", data={
        "patient_name": "TEST, A", "case_id": "Z10001", "event": "Lab — CBC",
        "owner": "3", "patient_age": "40", "patient_sex": "F"})
    check("create for another owner -> 302", r.status_code == 302)
    h = handoff_app.load_handoffs()[-1]
    hid = h["handoff_id"]
    check("owner holds the baton immediately", h["owner"] == 3)
    check("assignment to another starts UNACKNOWLEDGED", h["acknowledged_at"] is None)

    r = carter.post("/acknowledge", data={"handoff_id": hid})
    check("non-owner cannot acknowledge -> 403", r.status_code == 403)
    r = nina.post("/acknowledge", data={"handoff_id": hid})
    check("owner acknowledges -> 302", r.status_code == 302)
    h = get(hid)
    check("acknowledgment is stamped", h["acknowledged_at"] is not None and h["acknowledged_by"] == 3)
    check("acknowledgment enters the audit history",
          any(e["event"] == "ASSIGNMENT_ACKNOWLEDGED" and e["by"] == 3 for e in h["history"]))

    r = carter.post("/create-handoff", data={
        "patient_name": "TEST, B", "case_id": "Z10002", "event": "MRI — Brain", "owner": "1"})
    check("self-assignment create -> 302", r.status_code == 302)
    h2 = handoff_app.load_handoffs()[-1]
    check("self-assignment is acknowledged at creation", h2["acknowledged_at"] is not None)

    print("== Transfer resets acknowledgment ==")
    nina.post("/update-status", data={"handoff_id": hid, "status": "IN_PROGRESS"})
    r = nina.post("/transfer-owner", data={"handoff_id": hid, "new_owner": "7"})
    check("transfer -> 302", r.status_code == 302)
    h = get(hid)
    check("baton moved to the case manager", h["owner"] == 7)
    check("acknowledgment reset for the new owner", h["acknowledged_at"] is None)
    brooks = login("tbrooks")
    r = brooks.post("/acknowledge", data={"handoff_id": hid})
    check("new owner can acknowledge", r.status_code == 302 and get(hid)["acknowledged_at"] is not None)

    print("== Cancellation ==")
    williams = login("dwilliams")
    jlee = login("jlee")
    r = williams.post("/cancel-handoff", data={"handoff_id": hid, "reason": "Duplicate order"})
    check("uninvolved clinician cannot cancel -> 403", r.status_code == 403)
    r = brooks.post("/cancel-handoff", data={"handoff_id": hid, "reason": "   "})
    check("cancel without a reason -> 400", r.status_code == 400)
    r = jlee.post("/cancel-handoff", data={"handoff_id": hid, "reason": "Service no longer required — resolved by phone"})
    check("care coordinator can cancel with a reason -> 302", r.status_code == 302)
    h = get(hid)
    check("status is CANCELED", h["status"] == "CANCELED")
    check("cancellation + reason in audit history",
          any(e["event"] == "HANDOFF_CANCELED" and "resolved by phone" in e.get("reason", "") for e in h["history"]))
    r = brooks.post("/update-status", data={"handoff_id": hid, "status": "IN_PROGRESS"})
    check("canceled handoff accepts no status change -> 400", r.status_code == 400)
    r = brooks.post("/transfer-owner", data={"handoff_id": hid, "new_owner": "2"})
    check("canceled handoff cannot be transferred -> 400", r.status_code == 400)
    r = brooks.post("/add-note", data={"handoff_id": hid, "note_type": "NOTE",
                                       "text": "Late note: family informed of the change."})
    check("record entries can still be added after cancellation", r.status_code == 302)

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
