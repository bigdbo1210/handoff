"""
End-to-end workflow tests for Handoff (build v3).

Covers the original prototype rules plus the new build:
  - real login (required, wrong password rejected)
  - baton actions enforced against the signed-in user (owner only)
  - contributor model: any signed-in team member can add record entries
    (notes/orders/updates) without owning the baton

POLICY UPDATE (2026-10-22, approved by Derrick D. Dennis): contribution
now requires verified care-team membership (or unit-wide organizational
access) BEFORE the contribution is accepted. A clinician joins a team
through the approved team-add mechanism — never by submitting a note.
Three checks below were updated to this policy: the Resident is first
denied, then added to the team by a member, then contributes as before.

Run:  python tests/test_workflow.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import app as handoff_app

# Point the app at a throwaway data file for the tests
_tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
_tmp.write("[]")
_tmp.close()
handoff_app.DATA_FILE = _tmp.name

results = []

def check(name, cond, extra=""):
    results.append((name, "PASS" if cond else "FAIL", extra))

def load():
    return json.load(open(_tmp.name))

def login(client, username, password="handoff123"):
    if username == "njohnson" and password == "handoff123":
        password = "NinaUAT2026!"  # reviewer holds an individual UAT credential on this branch
    return client.post("/login", data={"username": username, "password": password})

# ---------- Auth ----------
anon = handoff_app.app.test_client()
r = anon.get("/")
check("Dashboard requires login (redirect)", r.status_code == 302 and "/login" in r.headers.get("Location", ""), f"status={r.status_code}")

r = login(anon, "njohnson", "wrong-password")
r2 = anon.get("/")
check("Wrong password does not log in", r2.status_code == 302, f"status={r2.status_code}")

rn = handoff_app.app.test_client()
login(rn, "njohnson", "NinaUAT2026!")
r = rn.get("/")
check("RN logs in and sees dashboard", r.status_code == 200, f"status={r.status_code}")
check("Dashboard shows 4 status columns", all(s in r.get_data(as_text=True) for s in ["NEW", "IN PROGRESS", "ESCALATED", "COMPLETED"]))
check("Dashboard shows metrics strip", "Avg Completion" in r.get_data(as_text=True))

# ---------- Create (initiator = signed-in user) ----------
dr = handoff_app.app.test_client()
login(dr, "dcarter")
r = dr.post("/create-handoff", data={"patient_name": "SMITH, J", "case_id": "A44219", "event": "MRI", "owner": "3"})
check("Create handoff redirects", r.status_code == 302, f"status={r.status_code}")
h = load()[-1]
hid = h["handoff_id"]
check("Handoff stored with status NEW", h["status"] == "NEW")
check("Initiator is the signed-in creator (Dr. Carter = 1)", h["initiator"] == 1)
check("created_at is stored", bool(h.get("created_at")))
check("History records CREATED event", h["history"][0]["event"] == "CREATED")

r = dr.post("/create-handoff", data={"patient_name": "", "case_id": "X", "event": "Lab", "owner": "3"})
check("Create with missing field -> 400", r.status_code == 400, f"status={r.status_code}")

# ---------- Baton rules against the signed-in user ----------
# Dr. Carter created it but Nurse Johnson (3) owns it: Carter cannot move it.
r = dr.post("/update-status", data={"handoff_id": hid, "status": "IN_PROGRESS"})
check("Non-owner status change -> 403", r.status_code == 403, f"status={r.status_code}")

# Owner cannot skip NEW -> COMPLETED
r = rn.post("/update-status", data={"handoff_id": hid, "status": "COMPLETED"})
check("NEW -> COMPLETED jump -> 400", r.status_code == 400, f"status={r.status_code}")

r = rn.post("/update-status", data={"handoff_id": hid, "status": "IN_PROGRESS"})
check("Owner NEW -> IN_PROGRESS", r.status_code == 302, f"status={r.status_code}")

r = rn.post("/transfer-owner", data={"handoff_id": hid, "new_owner": "3"})
check("Self-transfer -> 400", r.status_code == 400, f"status={r.status_code}")

r = rn.post("/transfer-owner", data={"handoff_id": hid, "new_owner": "6"})
check("Transfer RN(3) -> Care Coordinator(6)", r.status_code == 302, f"status={r.status_code}")
h = [x for x in load() if x["handoff_id"] == hid][0]
check("Owner is now 6", h["owner"] == 6)
check("History shows transfer 3 -> 6", any(e["event"] == "OWNERSHIP_TRANSFERRED" and "3" in e["by"] and "6" in e["by"] for e in h["history"]))

# ---------- Nina's contributor model ----------
# The Resident (2) does NOT own the baton. Under the 2026-10-22 policy he
# must be on the care team before he can contribute to the record.
resident = handoff_app.app.test_client()
login(resident, "dwilliams")
r = resident.post("/add-note", data={"handoff_id": hid, "note_type": "ORDER", "text": "Repeat troponin in 3 hours.", "id_confirm_name": "on", "id_confirm_dob": "on"})
check("Contribution before team membership -> 403", r.status_code == 403, f"status={r.status_code}")
r = rn.post("/team/add", data={"case_id": "A44219", "user_id": "2"})
check("A team member adds the Resident to the care team", r.status_code == 302, f"status={r.status_code}")
r = resident.post("/add-note", data={"handoff_id": hid, "note_type": "ORDER", "text": "Repeat troponin in 3 hours.", "id_confirm_name": "on", "id_confirm_dob": "on"})
check("Non-owner team member can add an ORDER to the record", r.status_code == 302, f"status={r.status_code}")
h = [x for x in load() if x["handoff_id"] == hid][0]
rec = [e for e in h["history"] if e["event"] == "RECORD_ADDED"]
check("Record entry is in history with text + author", len(rec) == 1 and rec[0]["text"] == "Repeat troponin in 3 hours." and rec[0]["by"] == 2)
check("Adding a record entry does NOT move the baton", h["owner"] == 6 and h["status"] == "IN_PROGRESS")

r = resident.post("/add-note", data={"handoff_id": hid, "note_type": "NOTE", "text": "   "})
check("Empty record entry -> 400", r.status_code == 400, f"status={r.status_code}")

# Contributor still cannot perform baton actions
r = resident.post("/update-status", data={"handoff_id": hid, "status": "ESCALATED"})
check("Contributor status change still -> 403", r.status_code == 403, f"status={r.status_code}")

# Anonymous users cannot add records
r = anon.post("/add-note", data={"handoff_id": hid, "note_type": "NOTE", "text": "sneaky"})
check("Anonymous record add -> login redirect", r.status_code == 302 and "/login" in r.headers.get("Location", ""), f"status={r.status_code}")

# ---------- Completion is terminal ----------
coord = handoff_app.app.test_client()
login(coord, "jlee")
r = coord.post("/update-status", data={"handoff_id": hid, "status": "ESCALATED"})
check("Owner IN_PROGRESS -> ESCALATED", r.status_code == 302, f"status={r.status_code}")
r = coord.post("/update-status", data={"handoff_id": hid, "status": "COMPLETED", "outcome": "Care coordination complete \u2014 receiving team confirmed."})
check("Owner ESCALATED -> COMPLETED", r.status_code == 302, f"status={r.status_code}")
r = coord.post("/transfer-owner", data={"handoff_id": hid, "new_owner": "2"})
check("Transfer of COMPLETED -> 400", r.status_code == 400, f"status={r.status_code}")

# A late record entry can still be added to a completed handoff (late charting is real)
r = resident.post("/add-note", data={"handoff_id": hid, "note_type": "NOTE", "text": "Late entry: family notified of result.", "id_confirm_name": "on", "id_confirm_dob": "on"})
check("Record can be added to COMPLETED handoff", r.status_code == 302, f"status={r.status_code}")

# ---------- Logout ----------
coord.get("/logout")
r = coord.get("/")
check("After logout, dashboard redirects to login", r.status_code == 302, f"status={r.status_code}")

h = [x for x in load() if x["handoff_id"] == hid][0]
print(f"Final: status={h['status']} owner={h['owner']} history={[e['event'] for e in h['history']]}\n")
for name, res, extra in results:
    print(f"{res}  {name}  {extra}")
print(f"\n{sum(1 for _, r, _ in results if r == 'PASS')}/{len(results)} passed")
os.unlink(_tmp.name)
