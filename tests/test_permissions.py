"""
Server-side patient permissions (Assessment #002, Stage 3).

The patient workspace is membership-scoped and enforced in the routes,
not the templates: non-members get 403, unknown patients 404, anonymous
users a login redirect. Charge nurses and care coordinators hold
organization-wide access by role. Following requires membership; team
membership can be granted by the team and revoked under the rules
(self-removal always; removing others is a coordinator/charge action;
nobody can be removed or stop following out from under an open baton).

Run:  python tests/test_permissions.py
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

def main():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    handoff_app.DATA_FILE = path
    care_path = handoff_app.care_file()
    if os.path.exists(care_path):
        os.unlink(care_path)
    handoff_app.save_handoffs(build_seed_handoffs())

    print("== Workspace access ==")
    anon = handoff_app.app.test_client()
    r = anon.get("/patient/A44219")
    check("anonymous -> login redirect", r.status_code == 302 and "/login" in r.headers.get("Location", ""))

    erin = login("epriddy")  # RN; on MOORE's and LEWIS's teams, not JOHNSON's
    r = erin.get("/patient/A44219")
    check("non-member clinician -> 403", r.status_code == 403)
    r = erin.get("/patient/F31407")
    check("own patient (MOORE) -> 200", r.status_code == 200)
    r = erin.get("/patient/ZZ9999")
    check("unknown patient -> 404", r.status_code == 404)

    nina = login("njohnson")
    r = nina.get("/patient/A44219")
    check("care-team member (Nina, JOHNSON) -> 200", r.status_code == 200)
    r = nina.get("/patient/C30981")
    check("Nina is not on SMITH's team -> 403", r.status_code == 403)

    thompson = login("nthompson")  # Charge Nurse — org-wide role
    r = thompson.get("/patient/R91537")
    check("charge nurse opens any patient (org-wide) -> 200", r.status_code == 200)
    jlee = login("jlee")  # Care Coordinator — org-wide role
    r = jlee.get("/patient/T34960")
    check("care coordinator opens any patient (org-wide) -> 200", r.status_code == 200)

    print("== Following requires membership ==")
    r = erin.post("/follow", data={"case_id": "A44219"})
    check("non-member follow -> 403", r.status_code == 403)
    r = erin.post("/follow", data={"case_id": "F31407"})
    check("member follow -> 302", r.status_code == 302)
    care = handoff_app.load_care()
    check("follow recorded", "F31407" in handoff_app.followed_case_ids(care, "8"))

    print("== Team management ==")
    r = nina.post("/team/add", data={"case_id": "A44219", "user_id": "8"})
    check("team member can add a clinician", r.status_code == 302)
    r = erin.get("/patient/A44219")
    check("added clinician can now open the workspace", r.status_code == 200)
    r = nina.post("/team/remove", data={"case_id": "A44219", "user_id": "2"})
    check("non-manager removing someone else -> 403", r.status_code == 403)
    r = thompson.post("/team/remove", data={"case_id": "A44219", "user_id": "2"})
    check("charge nurse can remove a member", r.status_code == 302)
    williams = login("dwilliams")
    r = williams.get("/patient/A44219")
    check("removed clinician loses workspace access", r.status_code == 403)
    r = erin.post("/team/remove", data={"case_id": "A44219", "user_id": "8"})
    check("self-removal (leave team) allowed", r.status_code == 302)
    r = erin.get("/patient/A44219")
    check("after leaving, access is gone", r.status_code == 403)

    print("== Stop-following guardrail ==")
    nina.post("/follow", data={"case_id": "A44219"})
    r = nina.post("/unfollow", data={"case_id": "A44219"})
    check("unfollow while owning an open task is refused (redirect w/ flash)", r.status_code == 302)
    care = handoff_app.load_care()
    check("Nina still follows JOHNSON", "A44219" in handoff_app.followed_case_ids(care, "3"))
    r = erin.post("/unfollow", data={"case_id": "F31407"})
    check("Erin's unfollow of MOORE is also blocked (she owns its open task)", r.status_code == 302)
    care = handoff_app.load_care()
    check("Erin still follows MOORE after the blocked attempt",
          "F31407" in handoff_app.followed_case_ids(care, "8"))
    thompson.post("/follow", data={"case_id": "T34960"})
    r = thompson.post("/unfollow", data={"case_id": "T34960"})
    check("unfollow with no open baton succeeds", r.status_code == 302)
    care = handoff_app.load_care()
    check("follow actually removed", "T34960" not in handoff_app.followed_case_ids(care, "4"))

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
