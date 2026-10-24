"""
Interactive metric cards (Screen 1 filters).

Covers Derrick's specification:
  - Selecting NEW / IN PROGRESS / ESCALATED / COMPLETED / WAITING TOO
    LONG shows the matching handoffs, grouped by patient, on the home
    page itself — no Operations Board trip, no manual search.
  - AVERAGE COMPLETION opens a completion-time breakdown, not a filter.
  - Filters respect the signed-in user's permissions: a team member's
    card counts and filtered lists cover only their authorized
    patients, and the number on the card equals the number of tasks
    the filter shows them.
  - Counts are labeled as tasks across patients — never conflated.

Run:  python tests/test_metric_filters.py
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

# Directive 3.0 experience: the four status categories are navigation
# chips on the roster; their counts are the same roster-task counts the
# metric cards used to show.
CHIP_LABELS = {"NEW": "New", "IN_PROGRESS": "In Progress", "ESCALATED": "Escalated", "COMPLETED": "Completed"}

def metric_num(html, label):
    m = re.search(CHIP_LABELS[label] + r' <span class="cat-count">(\d+)</span>', html)
    return int(m.group(1)) if m else None

def blocks(html):
    return html.count('class="patient-block"')

def task_cards(html):
    # Card containers only: class="card" or class="card stale-..." —
    # not the inner card-head / card-chips / card-case divs.
    return len(re.findall(r'<div class="card[" ]', html))

def main():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    handoff_app.DATA_FILE = path
    care_path = handoff_app.care_file()
    if os.path.exists(care_path):
        os.unlink(care_path)
    handoff_app.save_handoffs(build_seed_handoffs())

    thompson = login("nthompson")  # Charge Nurse — org-wide, sees all 19 patients
    nina = login("njohnson")        # NP — authorized for 6 patients (journey added 2026-10-23)

    print("== Cards are present and scoped (org-wide view) ==")
    home = thompson.get("/").get_data(as_text=True)
    check("ESCALATED card counts 3", metric_num(home, "ESCALATED") == 3)
    check("NEW card counts 5", metric_num(home, "NEW") == 5)
    check("COMPLETED card counts 6", metric_num(home, "COMPLETED") == 6)  # incl. 3 journey completions
    check("cards are links to filters", 'href="/?filter=ESCALATED"' in home)

    print("== ESCALATED filter: the 3 tasks, grouped by patient ==")
    page = thompson.get("/?filter=ESCALATED").get_data(as_text=True)
    check("header counts tasks AND patients", "3 task" in page and "3 patient" in page)
    check("three patient groups", blocks(page) == 3)
    check("three task cards", task_cards(page) == 3)
    check("the right patients are grouped",
          all(n in page for n in ["GARCIA, L", "PATEL, R", "LEWIS, D"]))
    check("each group deep-links to its patient workspace",
          'href="/patient/B77102?section=TASKS"' in page)
    check("the selected card is highlighted", 'metric alert active' in page or 'active' in page)

    print("== Other status filters ==")
    page = thompson.get("/?filter=NEW").get_data(as_text=True)
    check("NEW shows 5 groups / 5 tasks", blocks(page) == 5 and task_cards(page) == 5)
    page = thompson.get("/?filter=COMPLETED").get_data(as_text=True)
    check("COMPLETED shows the 4 finished patients",
          blocks(page) == 4 and all(n in page for n in ["BROWN, D", "DAVIS, S", "WALKER, N", "PATTERSON, R"]))
    page = thompson.get("/?filter=STALE").get_data(as_text=True)
    check("the removed inactivity filter falls back to the plain roster",
          "My Patients" in page)
    check("the removed inactivity label appears nowhere (home, board, workspace)",
          all("Waiting Too Long" not in c.get(p).get_data(as_text=True)
              for c, p in [(thompson, "/"), (thompson, "/board"), (nina, "/patient/A44219")]))

    print("== AVERAGE COMPLETION opens a breakdown, not a filter ==")
    page = thompson.get("/?filter=COMPLETIONS").get_data(as_text=True)
    check("breakdown tiles render (average/median/fastest/slowest)",
          all(s in page for s in ["Average", "Median", "Fastest", "Slowest"]))
    check("per-task durations are shown (BROWN took 1 h 54 min)", "1 h 54 min" in page)
    check("completed tasks grouped under their patients",
          all(n in page for n in ["BROWN, D", "DAVIS, S", "WALKER, N"]))
    check("breakdown links into the patient's history",
          'href="/patient/D55231?section=HISTORY"' in page)

    print("== Permissions: Nina's cards and lists cover only her patients ==")
    home_n = nina.get("/").get_data(as_text=True)
    check("Nina's ESCALATED card counts only her universe (1)", metric_num(home_n, "ESCALATED") == 1)
    page_n = nina.get("/?filter=ESCALATED").get_data(as_text=True)
    check("Nina's filter shows LEWIS only", blocks(page_n) == 1 and "LEWIS, D" in page_n)
    check("unauthorized patients never leak into her filter",
          "GARCIA, L" not in page_n and "PATEL, R" not in page_n)
    check("card number equals the tasks her filter shows",
          metric_num(home_n, "ESCALATED") == task_cards(page_n))
    check("header labels the count honestly (1 task, 1 patient)",
          "1 task" in page_n and "1 patient" in page_n)

    print("== Refresh fragment + fallbacks ==")
    frag = nina.get("/fragments/worklist?filter=ESCALATED").get_data(as_text=True)
    check("fragment honors the active filter", "LEWIS, D" in frag and "GARCIA, L" not in frag)
    page = nina.get("/?filter=BOGUS")
    check("unknown filter falls back to the normal home (200)", page.status_code == 200)
    check("fallback shows My Patients", "My Patients" in page.get_data(as_text=True))
    home_n = nina.get("/").get_data(as_text=True)
    check("mobile compaction rules ship in the page",
          "@media (max-width: 520px)" in home_n and "a.metric" in home_n)

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
