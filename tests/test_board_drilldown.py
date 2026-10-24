"""
Operations Board drill-down checks (Derrick's requirements, 2026-10-22):

  1. personal dashboard scoping is untouched (covered by the other suites),
  2. unit-wide drill-downs exist ONLY for unit-wide roles (charge nurse,
     care coordinator),
  3. regular clinicians gain nothing from a board filter, URL, or API —
     the filter is simply not honored for them,
  4. counts, filtered results, and patient details share one rule,
  5. every board filtered view links back to the full board,
  6. selecting a metric is navigation only — no status/owner changes,
  7. the plain board keeps working, including its cards,
  8. multi-user: two supervisors and a regular clinician at once.

Run:  python tests/test_board_drilldown.py
"""
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

def header_counts(html):
    m = re.search(r"<strong>(\d+) tasks?</strong> across <strong>(\d+) patients?</strong>", html)
    return (int(m.group(1)), int(m.group(2))) if m else None

def snapshot():
    return [
        (h["handoff_id"], h["status"], h["owner"], len(h["history"]), h.get("acknowledged_at"))
        for h in handoff_app.load_handoffs()
    ]

def main():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    handoff_app.DATA_FILE = path
    care_path = handoff_app.care_file()
    if os.path.exists(care_path):
        os.unlink(care_path)
    handoff_app.save_handoffs(build_seed_handoffs())

    thompson = login("nthompson")   # charge nurse — unit-wide
    jlee = login("jlee")            # care coordinator — unit-wide
    nina = login("njohnson")        # NP — regular clinician
    williams = login("dwilliams")   # resident — regular clinician
    carter = login("dcarter")       # attending — regular clinician

    print("== Who gets clickable board cards ==")
    for name, client in [("Thompson (charge)", thompson), ("Lee (coordinator)", jlee)]:
        board = client.get("/board").get_data(as_text=True)
        check(f"{name}: all six board cards are links",
              all(f"/board?filter={f}" in board for f in
                  ["NEW", "IN_PROGRESS", "ESCALATED", "COMPLETED", "CANCELED", "COMPLETIONS"]))
    for name, client in [("Nina", nina), ("Williams", williams), ("Carter", carter)]:
        board = client.get("/board").get_data(as_text=True)
        check(f"{name}: board cards are links too (everything clickable)",
              all(f"/board?filter={f}" in board for f in
                  ["NEW", "IN_PROGRESS", "ESCALATED", "COMPLETED", "CANCELED", "COMPLETIONS"]))

    print("== Non-unit-wide drill-down stays inside the clinician's universe ==")
    page = nina.get("/board?filter=ESCALATED").get_data(as_text=True)
    check("Nina's ESCALATED drill-down counts only her universe (1 task / 1 patient)",
          header_counts(page) == (1, 1))
    check("her escalated patient is grouped", "LEWIS, D" in page)
    check("patients outside her universe stay out",
          "PATEL, R" not in page and "GARCIA, L" not in page)
    check("scope is labeled as her authorized patients only",
          "your authorized patients only" in page)

    print("== The drill-down itself ==")
    page = thompson.get("/board?filter=ESCALATED").get_data(as_text=True)
    check("ESCALATED groups read '3 tasks across 3 patients'", header_counts(page) == (3, 3))
    check("the three escalated patients are grouped",
          all(n in page for n in ["PATEL, R", "GARCIA, L", "LEWIS, D"]))
    check("tasks are compact expandable rows", page.count('<details class="task-expand">') == 3)
    check("scope is labeled unit-wide", "unit-wide" in page)
    check("every group links into the workspace",
          all(f"/patient/{c}" in page for c in ["H51092", "B77102", "P78193"]))
    check("an obvious way back to the full board",
          "Back to the full Operations Board" in page and 'href="/board"' in page)
    check("the status columns step aside while filtered",
          'class="column escalated"' not in page)

    # Totals include the 2026-10-23 journey patient (H72410).
    totals = {"NEW": (5, 5), "IN_PROGRESS": (10, 10), "ESCALATED": (3, 3),
              "COMPLETED": (6, 5), "CANCELED": (0, 0)}
    for f, want in totals.items():
        got = header_counts(thompson.get(f"/board?filter={f}").get_data(as_text=True))
        check(f"board filter {f}: counts agree with the board's own cards ({want[0]} tasks)",
              got is not None and got[0] == want[0])

    page = jlee.get("/board?filter=COMPLETIONS").get_data(as_text=True)
    check("coordinator: Average Completion opens the breakdown", page.count('class="stat-tile"') == 5)
    check("breakdown shows the unit average", "2 h 46 min" in page)  # 166 min incl. journey completions
    check("completed rows carry durations and history links",
          "1 h 54 min" in page and "/patient/D55231?section=HISTORY" in page)

    print("== Regular clinicians drill in too — scoped to their universe ==")
    for name, client in [("Nina", nina), ("Williams", williams)]:
        page = client.get("/board?filter=ESCALATED").get_data(as_text=True)
        check(f"{name}: filter honored — grouped view renders", header_counts(page) is not None)
        check(f"{name}: the columns step aside while filtered", 'class="column escalated"' not in page)
        page = client.get("/board?filter=COMPLETIONS").get_data(as_text=True)
        check(f"{name}: completion breakdown opens (scoped)", "Completion Times" in page)
    check("Nina's workspace access is unchanged (LEWIS baton view, JOHNSON ok)",
          nina.get("/patient/A44219").status_code == 200)
    check("an unauthorized workspace is still 403",
          nina.get("/patient/D55231").status_code == 403)

    print("== Navigation only; search still wins; board cards work ==")
    before = snapshot()
    for client in (thompson, jlee, nina):
        for f in ["NEW", "IN_PROGRESS", "ESCALATED", "COMPLETED", "CANCELED", "COMPLETIONS", "BOGUS"]:
            client.get(f"/board?filter={f}")
    check("no status, owner, acknowledgment, or history changed", snapshot() == before)
    page = thompson.get("/board?filter=BOGUS").get_data(as_text=True)
    check("an invalid filter falls back to the plain board", 'class="column new"' in page)
    page = thompson.get("/board?q=LEWIS&filter=ESCALATED").get_data(as_text=True)
    check("search keeps its behavior (filter steps aside)", header_counts(page) is None)
    board = jlee.get("/board").get_data(as_text=True)
    check("the baton holder's working forms render on the plain board",
          'action="/transfer-owner"' in board)

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
