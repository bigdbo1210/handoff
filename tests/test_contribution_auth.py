"""
Contribution authorization (policy approved 2026-10-22, Derrick D. Dennis):

  - A clinician must ALREADY hold care-team membership or unit-wide
    organizational access before any note, order, or update is accepted.
  - Submitting a note never confers membership.
  - Authorized team members can contribute regardless of who holds the
    baton; baton actions themselves stay owner-only.
  - The approved way onto a team is the team-add mechanism (a member, a
    charge nurse, or a care coordinator adds the clinician).
  - Denials change nothing: no membership, no history, no patient data.

Run:  python tests/test_contribution_auth.py
"""
import json
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

def task(case_id, event_part=None):
    for h in handoff_app.load_handoffs():
        if h["case_id"] == case_id and (event_part is None or event_part in h["event"]):
            return h
    raise KeyError(case_id)

def main():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    handoff_app.DATA_FILE = path
    care_path = handoff_app.care_file()
    if os.path.exists(care_path):
        os.unlink(care_path)
    handoff_app.save_handoffs(build_seed_handoffs())

    nina = login("njohnson")       # initiator/member of LEWIS; baton is Erin's
    erin = login("epriddy")         # owner of LEWIS's baton
    williams = login("dwilliams")   # outsider to LEWIS and JOHNSON
    thompson = login("nthompson")   # charge nurse — unit-wide
    morgan = login("amorgan")       # unit clerk — outsider to LEE

    lewis = task("P78193", "Wound Care")
    johnson = task("A44219", "MRI")
    lee = task("E90214", "Cardiology")

    print("== Unauthorized contributions are denied, and change nothing ==")
    before_h = json.dumps(handoff_app.load_handoffs(), sort_keys=True)
    before_care = open(care_path).read() if os.path.exists(care_path) else ""
    r = williams.post("/add-note", data={"handoff_id": lewis["handoff_id"],
                                         "note_type": "NOTE", "text": "drive-by note"})
    check("outsider's note to LEWIS -> 403", r.status_code == 403)
    r = morgan.post("/add-note", data={"handoff_id": johnson["handoff_id"],
                                       "note_type": "ORDER", "text": "drive-by order"})
    check("outsider's order to JOHNSON -> 403", r.status_code == 403)
    check("no handoff data changed", json.dumps(handoff_app.load_handoffs(), sort_keys=True) == before_h)
    after_care = open(care_path).read() if os.path.exists(care_path) else ""
    check("no care-team data changed", after_care == before_care)
    check("the outsider gained no access", williams.get("/patient/P78193").status_code == 403)

    print("== Authorized clinicians contribute, baton or not ==")
    r = nina.post("/add-note", data={"handoff_id": lewis["handoff_id"],
                                     "note_type": "NOTE", "text": "Wound edges improving."})
    check("team member without the baton can contribute", r.status_code == 302)
    r = erin.post("/add-note", data={"handoff_id": lewis["handoff_id"],
                                     "note_type": "NOTE", "text": "Dressing changed."})
    check("the baton holder can contribute", r.status_code == 302)
    h = task("P78193", "Wound Care")
    entries = [e for e in h["history"] if e["event"] == "RECORD_ADDED"]
    seed_entries = [e for e in lewis["history"] if e["event"] == "RECORD_ADDED"]
    check("both entries landed in the audit history",
          len(entries) == len(seed_entries) + 2)
    check("authorship is recorded (Nina=3, Erin=8)",
          {e.get("by") for e in entries[-2:]} == {3, 8})
    check("contributing never moved the baton", h["owner"] == lewis["owner"])

    r = thompson.post("/add-note", data={"handoff_id": task("D55231")["handoff_id"],
                                         "note_type": "NOTE", "text": "Charge review."})
    check("unit-wide organizational access can contribute anywhere", r.status_code == 302)

    print("== The approved way onto a team ==")
    check("Morgan cannot see LEE yet", morgan.get("/patient/E90214").status_code == 403)
    r = thompson.post("/team/add", data={"case_id": "E90214", "user_id": "5"})
    check("charge nurse adds Morgan to LEE's team", r.status_code == 302)
    check("Morgan can now open the workspace", morgan.get("/patient/E90214").status_code == 200)
    r = morgan.post("/add-note", data={"handoff_id": lee["handoff_id"],
                                       "note_type": "NOTE", "text": "Family updated."})
    check("the newly added member can contribute", r.status_code == 302)

    r = nina.post("/team/add", data={"case_id": "P78193", "user_id": "2"})
    check("a team member adds Williams to LEWIS's team", r.status_code == 302)
    r = williams.post("/add-note", data={"handoff_id": lewis["handoff_id"],
                                         "note_type": "NOTE", "text": "Now on the team."})
    check("Williams contributes after being added", r.status_code == 302)
    r = williams.post("/update-status", data={"handoff_id": lewis["handoff_id"], "status": "COMPLETED"})
    check("membership never grants baton actions (still 403)", r.status_code == 403)

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
