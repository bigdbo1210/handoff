"""
Navigation at scale (Requirement: 15-20 fictional patients).

With 18 patients on the board, the two-screen navigation must stay
efficient: the worklist renders fast, search narrows to one patient,
deep links land on the right sections, and every authorized patient
workspace opens. Also covers the automatic-update plumbing: the state
endpoint's version moves when another clinician records activity, the
unread flag follows read state, and refresh fragments enforce the same
permissions as the pages.

Run:  python tests/test_navigation_load.py
"""
import os
import sys
import tempfile
import time

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
    handoffs = build_seed_handoffs()
    handoff_app.save_handoffs(handoffs)
    case_ids = sorted({h["case_id"] for h in handoffs})
    check("board carries 18 fictional patients", len(case_ids) == 18)

    nina = login("njohnson")
    thompson = login("nthompson")

    print("== Worklist at scale ==")
    start = time.time()
    r = nina.get("/")
    elapsed = time.time() - start
    html = r.get_data(as_text=True)
    check("worklist renders 200", r.status_code == 200)
    check(f"worklist renders fast ({elapsed:.2f}s < 2s)", elapsed < 2.0)
    check("her patients are listed as compact roster rows under My Patients",
          "My Patients" in html and html.count('class="auth-row"') >= 2)
    check("the four status categories lead as navigation chips (no metric band)",
          all(s in html for s in ["New", "In Progress", "Escalated", "Completed"])
          and "cat-chip" in html and "Avg Completion" not in html)

    print("== Search narrows the list (inside your authorized universe) ==")
    r = thompson.get("/?q=NGUYEN")
    html = r.get_data(as_text=True)
    check("search finds NGUYEN (charge nurse, org-wide)", "NGUYEN, T" in html)
    check("search excludes PATEL's block", 'data-case="H51092"' not in html)
    r = nina.get("/?q=NGUYEN")
    html = r.get_data(as_text=True)
    check("search never leaks a patient Nina isn't authorized for", 'data-case="G20817"' not in html)

    print("== Every authorized workspace opens (charge nurse, org-wide) ==")
    start = time.time()
    bad = []
    for cid in case_ids:
        rr = thompson.get(f"/patient/{cid}")
        if rr.status_code != 200:
            bad.append((cid, rr.status_code))
    elapsed = time.time() - start
    check("all 18 patient pages return 200", not bad)
    check(f"18 pages render in {elapsed:.2f}s total (< 10s)", elapsed < 10.0)

    print("== Patient page content: strip + sections ==")
    r = nina.get("/patient/A44219")
    html = r.get_data(as_text=True)
    check("status strip shows the MRI line", "MRI in progress" in html)
    check("care team strip lists the team", "Nina Johnson" in html and "Dr. Carter" in html)
    r = nina.get("/patient/A44219?section=LABS")
    html = r.get_data(as_text=True)
    check("labs section opens directly", 'class="tab active" href="/patient/A44219?section=LABS"' in html or "section=LABS" in html)
    check("labs empty state is honest", "No labs updates recorded" in html)
    r = nina.get("/patient/A44219?section=DIAGNOSTICS")
    html = r.get_data(as_text=True)
    check("diagnostics entry is labeled with its recorder", "Recorded by Nina Johnson" in html)
    check("entries are labeled manually entered (no implied EMR feed)", "Entered manually" in html)

    print("== Automatic-update plumbing ==")
    state1 = nina.get("/api/state").get_json()
    check("state endpoint returns a version + unread map",
          bool(state1.get("version")) and isinstance(state1.get("unread"), dict))
    check("JOHNSON starts read for Nina (her own note is latest)", state1["unread"].get("A44219") is False)
    williams = login("dwilliams")
    hid = [h["handoff_id"] for h in handoff_app.load_handoffs() if h["case_id"] == "A44219"][0]
    williams.post("/add-note", data={"handoff_id": hid, "note_type": "UPDATE", "category": "LAB",
                                     "text": "Troponin resulted: 0.04 — within normal limits.", "id_confirm_name": "on", "id_confirm_dob": "on"})
    state2 = nina.get("/api/state").get_json()
    check("version changes when a teammate records activity", state2["version"] != state1["version"])
    check("JOHNSON becomes unread for Nina", state2["unread"].get("A44219") is True)
    r = nina.get("/fragments/patient/A44219")
    check("patient fragment serves members", r.status_code == 200)
    check("fragment shows the new lab entry", "Troponin resulted" in r.get_data(as_text=True))
    r = nina.get("/patient/A44219")
    state3 = nina.get("/api/state").get_json()
    check("opening the workspace clears the unread flag", state3["unread"].get("A44219") is False)
    r = nina.get("/fragments/worklist")
    check("worklist fragment renders", r.status_code == 200 and "auth-row" in r.get_data(as_text=True))
    erin = login("epriddy")
    r = erin.get("/fragments/patient/A44219")
    check("fragment enforces membership (non-member -> 403)", r.status_code == 403)
    r = erin.get("/fragments/patient/F31407")
    check("fragment serves her own patient's workspace", r.status_code == 200)
    anon = handoff_app.app.test_client()
    check("state endpoint requires login", anon.get("/api/state").status_code == 302)

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
