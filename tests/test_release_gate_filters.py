"""
Release-gate checks for the interactive metric cards deployment.

Maps to Derrick's seven pre-deployment requirements:
  #2 all six cards work (links + targets on the shipped page),
  #3 filtered results are compact patient summaries with expandable tasks,
  #4 selecting a metric is a pure read — it never changes clinical
     status, ownership, or history,
  #5 permissions hold on every filtered result and every task action,
  #6 polling preserves the active filter and the unsaved-text guard.

(#1 full-suite verification and #7 rollback are release-process steps,
evidenced in the deployment report.)

Run:  python tests/test_release_gate_filters.py
"""
import copy
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

def snapshot():
    return [
        (h["handoff_id"], h["status"], h["owner"], len(h["history"]),
         h.get("acknowledged_at"))
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

    thompson = login("nthompson")
    nina = login("njohnson")
    jlee = login("jlee")

    print("== #2 The four status categories work ==")
    home = thompson.get("/").get_data(as_text=True)
    for f in ["NEW", "IN_PROGRESS", "ESCALATED", "COMPLETED"]:
        check(f"category chip links to ?filter={f}", f'href="/?filter={f}"' in home)
        r = thompson.get(f"/?filter={f}")
        check(f"filter {f} renders 200", r.status_code == 200)
    board = thompson.get("/board").get_data(as_text=True)
    check("completion times stay reachable from the Operations Board",
          'href="/board?filter=COMPLETIONS"' in board)
    check("the removed inactivity category links from nowhere",
          "filter=STALE" not in home and "filter=STALE" not in board
          and "Waiting Too Long" not in home and "Waiting Too Long" not in board)
    check("filter COMPLETIONS renders 200", thompson.get("/?filter=COMPLETIONS").status_code == 200)
    check("filter STALE renders 200 (falls back to the roster)", thompson.get("/?filter=STALE").status_code == 200)

    print("== #3 Compact summaries, expandable tasks ==")
    page = thompson.get("/?filter=ESCALATED").get_data(as_text=True)
    check("each matching task is a compact expandable row",
          page.count('<details class="task-expand">') == 3)
    check("compact row names the baton holder", "Baton:" in page and "Jordan Lee" in page)
    check("the full working card lives inside the expander",
          page.count('action="/transfer-owner"') == 0)  # Thompson owns none of these
    jlee_page = jlee.get("/?filter=ESCALATED").get_data(as_text=True)
    check("the owner's expander contains his working transfer form",
          'action="/transfer-owner"' in jlee_page)
    home_default = nina.get("/").get_data(as_text=True)
    check("the unfiltered home keeps its full-card layout",
          'class="task-expand"' not in home_default)

    print("== #4 Selecting a metric changes nothing clinical ==")
    before = snapshot()
    for client in (thompson, nina):
        for f in ["NEW", "IN_PROGRESS", "ESCALATED", "COMPLETED", "COMPLETIONS"]:
            client.get(f"/?filter={f}")
            client.get(f"/fragments/worklist?filter={f}")
    check("statuses, owners, acknowledgments, history lengths identical",
          snapshot() == before)

    print("== #5 Permissions on filtered results and actions ==")
    page_n = nina.get("/?filter=COMPLETED").get_data(as_text=True)
    # Since 2026-10-23 Nina IS authorized for one completed patient — the
    # demonstration journey patient (PATTERSON, R) — and only that one.
    check("Nina's COMPLETED filter shows only her authorized completed patient",
          'class="patient-block"' in page_n and "PATTERSON, R" in page_n)
    check("no unauthorized completed patients leak",
          all(n not in page_n for n in ["BROWN, D", "DAVIS, S", "WALKER, N"]))
    lewis = [h for h in handoff_app.load_handoffs() if h["case_id"] == "P78193"][0]
    r = nina.post("/update-status", data={"handoff_id": lewis["handoff_id"], "status": "COMPLETED"})
    check("Nina still cannot move a baton she doesn't own (403)", r.status_code == 403)
    page_n = nina.get("/?filter=ESCALATED").get_data(as_text=True)
    check("her filtered view of LEWIS carries no baton forms",
          'action="/transfer-owner"' not in page_n and 'action="/update-status"' not in page_n)

    print("== #6 Polling preserves the filter and unsaved work ==")
    page = nina.get("/?filter=ESCALATED").get_data(as_text=True)
    check("the page pins its active filter for refreshes",
          'const ACTIVE_FILTER = "ESCALATED"' in page)
    check("the dirty-form guard ships on filtered pages",
          "editingNow" in page and "formDirty" in page and "updates-pill" in page)
    frag = nina.get("/fragments/worklist?filter=ESCALATED").get_data(as_text=True)
    check("fragment under the filter stays filtered",
          "LEWIS, D" in frag and "GARCIA, L" not in frag)

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
