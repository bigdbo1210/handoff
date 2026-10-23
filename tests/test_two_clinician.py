"""
Two-clinician collaboration + refresh-safety release checks.

Simulates two different signed-in clinicians working the same patient at
the same time (two independent sessions):
  - Nina (NP, baton owner) and Dr. Williams (resident, contributor).
  - Dr. Williams records a categorized lab update on Nina's patient.
  - Nina's update channel must show: a changed version stamp, an unread
    flag on that patient, and the new entry in her refresh fragment.
  - The baton must NOT move and Dr. Williams must NOT gain baton powers.
  - Visibility rule: a third clinician who is not on the team (Erin)
    sees none of it — her state endpoint doesn't list the patient.

Refresh safety (release check): the shipped pages must contain the
dirty-form guard — automatic swaps are blocked while any form holds
unsaved input, and the patient page offers a tap-to-refresh notice
instead of ever reloading itself.

Run:  python tests/test_two_clinician.py
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
    resp = client.post("/login", data={"username": username, "password": "NinaUAT2026!" if username == "njohnson" else "handoff123"})
    assert resp.status_code == 302, username
    return client

def main():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    handoff_app.DATA_FILE = path
    care_path = handoff_app.care_file()
    if os.path.exists(care_path):
        os.unlink(care_path)
    handoff_app.save_handoffs(build_seed_handoffs())

    nina = login("njohnson")
    williams = login("dwilliams")
    erin = login("epriddy")
    hid = [h["handoff_id"] for h in handoff_app.load_handoffs() if h["case_id"] == "A44219"][0]

    print("== Two clinicians, one patient, same moment ==")
    nina.get("/patient/A44219")  # Nina opens the chart (marks it read)
    state_a = nina.get("/api/state").get_json()
    check("Nina's baseline: JOHNSON read, version stamped",
          state_a["unread"].get("A44219") is False and bool(state_a["version"]))

    r = williams.post("/add-note", data={
        "handoff_id": hid, "note_type": "UPDATE", "category": "LAB",
        "text": "Troponin resulted: 0.04 — within normal limits.", "id_confirm_name": "on", "id_confirm_dob": "on"})
    check("teammate's contribution is accepted (302)", r.status_code == 302)
    h = handoff_app.find_handoff(handoff_app.load_handoffs(), hid)
    check("the baton did not move", h["owner"] == 3 and h["status"] == "IN_PROGRESS")

    state_b = nina.get("/api/state").get_json()
    check("Nina's version stamp changed", state_b["version"] != state_a["version"])
    check("Nina is notified: JOHNSON unread again", state_b["unread"].get("A44219") is True)
    frag = nina.get("/fragments/patient/A44219?section=LABS").get_data(as_text=True)
    check("Nina's refresh fragment carries the new lab entry", "Troponin resulted" in frag)
    check("the entry is attributed to its author", "Dr. Williams" in frag)

    r = williams.post("/update-status", data={"handoff_id": hid, "status": "COMPLETED"})
    check("contributor still cannot move the baton (403)", r.status_code == 403)
    r = williams.post("/transfer-owner", data={"handoff_id": hid, "new_owner": "2"})
    check("contributor still cannot transfer (403)", r.status_code == 403)

    print("== A clinician outside the team sees none of it ==")
    erin_state = erin.get("/api/state").get_json()
    check("JOHNSON absent from Erin's unread map", "A44219" not in erin_state["unread"])
    check("Erin's workspace request is refused (403)", erin.get("/patient/A44219").status_code == 403)

    print("== Unsaved-text protection ships in the pages ==")
    home = nina.get("/").get_data(as_text=True)
    check("worklist polls a version stamp", "/api/state" in home)
    check("worklist blocks the swap while a form is dirty", "editingNow" in home and "formDirty" in home)
    check("worklist offers tap-to-refresh instead", "updates-pill" in home)
    page = nina.get("/patient/A44219").get_data(as_text=True)
    check("patient page polls but never auto-reloads", "/api/state" in page and "updates-pill" in page)
    check("patient page carries the refresh-safety checklist note",
          "never reload over unsaved writing" in page)

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
