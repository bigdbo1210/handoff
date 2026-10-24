"""
Access-scope security verification (Derrick's pre-deployment requirement).

Every surface must enforce the signed-in clinician's authorized scope:
the Operations Board (records, metrics, and its search), the home page
and its search, the refresh fragment, the state API, patient workspaces,
and task actions. Unit-wide roles (charge nurse, care coordinator) are
authorized for the whole unit, so their surfaces are unchanged.

Run:  python tests/test_board_scope.py
"""
import json
import os
import re
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

def board_num(html, label):
    m = re.search(r'<div class="num">([^<]+)</div><div class="lbl">' + label + r'</div>', html)
    return m.group(1) if m else None

def main():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    handoff_app.DATA_FILE = path
    care_path = handoff_app.care_file()
    if os.path.exists(care_path):
        os.unlink(care_path)
    seed = build_seed_handoffs()
    handoff_app.save_handoffs(seed)

    # H72410 (PATTERSON, R) joined Nina's authorized set 2026-10-23: she is
    # on the demonstration journey patient's care team by design.
    nina_cases = {"A44219", "E90214", "K90271", "P78193", "S60429", "H72410"}
    name_by_case = {}
    for h in seed:
        name_by_case.setdefault(str(h["case_id"]), h["patient_name"])
    unauthorized_names = [n for c, n in name_by_case.items() if c not in nina_cases]
    authorized_names = [n for c, n in name_by_case.items() if c in nina_cases]

    nina = login("njohnson")
    williams = login("dwilliams")
    thompson = login("nthompson")

    print("== The board itself is scoped ==")
    board = nina.get("/board").get_data(as_text=True)
    leaks = [n for n in unauthorized_names if n in board]
    check("no unauthorized patient appears anywhere on Nina's board", leaks == [])
    check("her authorized patients do appear",
          all(n in board for n in ["JOHNSON, M", "LEWIS, D", "WILSON, J"]))
    check("her board metrics are scoped too (Escalated 1, Completed 3 — journey tasks)",
          board_num(board, "Escalated") == "1" and board_num(board, "Completed") == "3")
    check("her board average reflects her authorized completions (journey: 207 min)",
          board_num(board, "Avg Completion") == "207 min")

    board_w = williams.get("/board").get_data(as_text=True)
    check("Williams's board hides patients he has no access to",
          "LEWIS, D" not in board_w and "BROWN, D" not in board_w)
    check("Williams's board shows his own patients", "SMITH, J" in board_w and "PATEL, R" in board_w)

    board_t = thompson.get("/board").get_data(as_text=True)
    check("the charge nurse's board is the full unit (all 19 patients)",
          all(n in board_t for n in name_by_case.values()))
    check("her board metrics stay unit-wide (5 new / 3 escalated / 166 min)",
          board_num(board_t, "New") == "5" and board_num(board_t, "Escalated") == "3"
          and board_num(board_t, "Avg Completion") == "166 min")

    print("== Search respects the same scope ==")
    page = nina.get("/board?q=BROWN").get_data(as_text=True)
    check("board search cannot surface an unauthorized patient",
          "BROWN, D" not in page and "Showing 0 of" in page)
    page = nina.get("/board?q=JOHNSON").get_data(as_text=True)
    check("board search still finds her own patient", "JOHNSON, M" in page)
    page = thompson.get("/board?q=BROWN").get_data(as_text=True)
    check("unit-wide search still works for the charge nurse", "BROWN, D" in page)
    page = nina.get("/?q=BROWN").get_data(as_text=True)
    check("home search cannot surface an unauthorized patient", "BROWN, D" not in page)

    print("== Fragments, API, workspaces, actions ==")
    frag = nina.get("/fragments/worklist").get_data(as_text=True)
    check("the refresh fragment carries no unauthorized patient",
          all(n not in frag for n in unauthorized_names))
    state = json.loads(nina.get("/api/state").get_data(as_text=True))
    check("the state API covers exactly her authorized cases",
          set(state["unread"].keys()) == nina_cases and state["patients"] == 6)
    check("workspace direct access still 403 for unauthorized patients",
          nina.get("/patient/D55231").status_code == 403
          and nina.get("/patient/B77102").status_code == 403)
    brown = [h for h in seed if h["case_id"] == "D55231"][0]
    r = nina.post("/update-status", data={"handoff_id": brown["handoff_id"], "status": "COMPLETED"})
    check("task actions on unauthorized patients stay forbidden", r.status_code == 403)
    # Contribution requires prior authorization (policy, 2026-10-22):
    # a clinician who is not on the care team cannot write into the
    # record, and the attempt changes nothing — no membership is granted.
    surfaces = board + nina.get("/").get_data(as_text=True) + frag
    check("an unauthorized handoff's ID appears on none of her surfaces",
          brown["handoff_id"] not in surfaces)
    state_before = json.loads(nina.get("/api/state").get_data(as_text=True))
    r = nina.post("/add-note", data={"handoff_id": brown["handoff_id"],
                                     "note_type": "NOTE", "text": "Cross-cover note"})
    check("an unauthorized contribution is denied (403)", r.status_code == 403)
    stored = [h for h in handoff_app.load_handoffs() if h["case_id"] == "D55231"][0]
    check("the denied attempt changed no patient data",
          stored["status"] == "COMPLETED" and len(stored["history"]) == len(brown["history"]))
    check("the denied attempt granted no membership",
          nina.get("/patient/D55231").status_code == 403
          and json.loads(nina.get("/api/state").get_data(as_text=True))["unread"].keys()
              == state_before["unread"].keys())

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
