"""Directive 3.0 EXPERIENCE checks (UAT presentation correction, 2026-10-23).

Nina's UAT screenshots showed the legacy task-centered interface. These
checks pin the approved experience in the application itself:

  * Home = My Patients first: compact clickable roster, the four status
    categories as navigation chips, no metric band above the roster.
  * The removed inactivity category appears NOWHERE (label or filter).
  * The workspace has the ten approved sections; Overview is the
    default and carries Disposition & Responsibility.
  * Snapshot sections (HPI / Medical History / Vitals) render the
    seeded fictional entries with provenance labels and attribution.
  * Care-Team Updates carries the two-identifier composer.
  * Notifications deep-link to the exact record (section + highlight)
    and Simulate injects a clearly-labeled simulated alert.

Run: python tests/test_directive3_experience.py
"""
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import app as handoff_app
from seed_demo import build_seed_care, build_seed_handoffs

passed = failed = 0


def check(name, cond):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}")


def login(username):
    client = handoff_app.app.test_client()
    pw = "NinaUAT2026!" if username == "njohnson" else "handoff123"
    resp = client.post("/login", data={"username": username, "password": pw})
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
    handoff_app.save_care(build_seed_care())

    nina = login("njohnson")
    thompson = login("nthompson")

    print("== Home: My Patients first ==")
    home = nina.get("/").get_data(as_text=True)
    check("My Patients heading is on the home page", "My Patients" in home)
    check("roster rows render (compact, clickable)", 'class="auth-row"' in home)
    check("no metric band above the roster", 'class="metric' not in home and 'class="metrics"' not in home)
    check("the four status categories are navigation chips",
          all(f'href="/?filter={f}"' in home for f in ["NEW", "IN_PROGRESS", "ESCALATED", "COMPLETED"]))
    check("chip counts are computed (Escalated shows her universe)",
          'Escalated <span class="cat-count">1</span>' in home)
    check("create form is collapsed below the roster", '<details class="create-wrap">' in home)
    check("Operations Board is a link, not the home", 'href="/board"' in home)

    print("== The removed inactivity category is nowhere ==")
    for client, url in [(nina, "/"), (thompson, "/"), (thompson, "/board"),
                        (nina, "/patient/A44219"), (nina, "/notifications")]:
        html = client.get(url).get_data(as_text=True)
        check(f"no removed label at {url}", "Waiting Too Long" not in html and "filter=STALE" not in html)

    print("== Workspace: the ten approved sections ==")
    page = nina.get("/patient/A44219").get_data(as_text=True)
    for label in ["Overview", "HPI", "Medical History", "Vitals", "Labs",
                  "Diagnostics / Imaging", "Consultations", "Care-Team Updates",
                  "Pending Tasks", "Activity &amp; Accountability"]:
        check(f"tab present: {label}", label in page)
    check("Overview is the default section (disposition lives there)",
          "Disposition &amp; Responsibility" in page and "Intent to admit" in page)
    check("identifiers ride the header (DOB + MRN)", "07/02/1955" in page and "7712045" in page)

    print("== Snapshot sections carry provenance-labeled fictional data ==")
    hpi = nina.get("/patient/A44219?section=HPI").get_data(as_text=True)
    check("HPI renders the seeded entry", "NIHSS 14" in hpi)
    check("HPI entry is attributed with a source label",
          "Dr. Carter" in hpi and "Manually entered" in hpi)
    hist = nina.get("/patient/A44219?section=MEDICAL_HISTORY").get_data(as_text=True)
    check("Medical History renders entries", "Hypertension" in hist and "Prior TIA" in hist)
    vit = nina.get("/patient/A44219?section=VITALS").get_data(as_text=True)
    check("Vitals render recorded sets with performer", "BP 158/92" in vit and "Erin Priddy" in vit)
    empty = thompson.get("/patient/H51092?section=HPI").get_data(as_text=True)
    check("a patient without snapshot data gets an honest empty state",
          "No history of present illness has been recorded" in empty)

    print("== Care-Team Updates: feed + gated composer ==")
    upd = nina.get("/patient/A44219?section=UPDATES").get_data(as_text=True)
    check("seeded updates are listed", "MRI in progress" in upd)
    check("the two-identifier gate rides the composer",
          'name="id_confirm_name"' in upd and 'name="id_confirm_dob"' in upd)
    hid = None
    for h in handoff_app.load_handoffs():
        if h["case_id"] == "A44219":
            hid = h["handoff_id"]
    r = nina.post("/add-note", data={"handoff_id": hid, "text": "Ungated update attempt",
                                     "note_type": "UPDATE", "category": "GENERAL"})
    check("posting without the gate is refused (400)", r.status_code == 400)
    r = nina.post("/add-note", data={"handoff_id": hid, "text": "Family updated at bedside",
                                     "note_type": "UPDATE", "category": "GENERAL",
                                     "id_confirm_name": "on", "id_confirm_dob": "on"})
    check("posting with the gate succeeds (302)", r.status_code == 302)
    upd = nina.get("/patient/A44219?section=UPDATES").get_data(as_text=True)
    check("the gated update lands in Care-Team Updates", "Family updated at bedside" in upd)

    print("== Board cards lead with name + DOB/MRN; case is secondary ==")
    tasks_page = nina.get("/patient/A44219?section=TASKS").get_data(as_text=True)
    check("the task card names the patient first", "JOHNSON, M" in tasks_page)
    check("DOB and MRN ride the card", "DOB 07/02/1955" in tasks_page and "MRN 7712045" in tasks_page)
    check("the case id is demoted to an internal reference",
          "Case A44219 \u00b7 internal reference" in tasks_page)
    board = nina.get("/board").get_data(as_text=True)
    check("every board box is clickable for Nina, Canceled included",
          all(f"/board?filter={f}" in board for f in
              ["NEW", "IN_PROGRESS", "ESCALATED", "COMPLETED", "CANCELED", "COMPLETIONS"]))
    canceled = nina.get("/board?filter=CANCELED").get_data(as_text=True)
    check("the Canceled box filters (0 canceled in her universe, honestly)",
          "0 tasks" in canceled or "0 task" in canceled)
    esc = nina.get("/board?filter=ESCALATED").get_data(as_text=True)
    check("selecting the active category again returns the full board (Master Directive §3)",
          'metric alert active" href="/board"' in esc)

    print("== Attribution: performer and recorder are never merged ==")
    meta = handoff_app.user_meta()
    lee_vitals = nina.get("/patient/E90214?section=VITALS").get_data(as_text=True)
    check("Lee vitals separate Measured by from Recorded by",
          "Measured by:" in lee_vitals and "Recorded by" in lee_vitals)
    check("existing records never carry an assumed performer (Derrick, 2026-10-23)",
          "Measured by: Not documented" in lee_vitals
          and ("Measured by: " + meta["4"]["name"]) not in lee_vitals
          and ("Recorded by " + meta["7"]["name"]) in lee_vitals)
    check("Lee vitals carry masked staff IDs", "Staff ID" in lee_vitals)
    johnson_vitals = nina.get("/patient/A44219?section=VITALS").get_data(as_text=True)
    check("Johnson's existing sets also show the measurer as Not documented",
          johnson_vitals.count("Measured by: Not documented") >= 2)
    check("the split-attribution example is a labeled demonstration entry",
          "Demonstration entry" in johnson_vitals
          and ("Measured by: " + meta["8"]["name"]) in johnson_vitals
          and ("Recorded by " + meta["3"]["name"]) in johnson_vitals)
    check("clinical times render as exact date + clock time + timezone",
          re.search(r"[A-Z][a-z]{2} \d{1,2}, \d{4} · \d{1,2}:\d{2} (AM|PM) E[DS]T",
                    johnson_vitals) is not None
          and "just now</span>" not in johnson_vitals)
    lee_hist = nina.get("/patient/E90214?section=MEDICAL_HISTORY").get_data(as_text=True)
    check("Lee history credits Nina as recorder", ("Recorded by " + meta["3"]["name"]) in lee_hist)
    check("Lee history honestly shows the obtainer as Not documented",
          "Obtained by: Not documented" in lee_hist)
    check("Lee history honestly shows the information source as Not documented",
          "Information source: Not documented" in lee_hist)
    moore_hist = thompson.get("/patient/F31407?section=MEDICAL_HISTORY").get_data(as_text=True)
    check("Moore history carries its documented origin (caregiver-reported)",
          "Information source: Caregiver-reported" in moore_hist)
    labs = thompson.get("/patient/G20817?section=LABS").get_data(as_text=True)
    diag = nina.get("/patient/A44219?section=DIAGNOSTICS").get_data(as_text=True)
    check("record entries render through the shared attribution component",
          "attr-block" in labs and "attr-block" in diag and "attr-block" in lee_vitals)
    check("seeded lab records show performer Not documented (never assumed)",
          "Performed by: Not documented" in labs)
    acct = nina.get("/patient/A44219?section=HISTORY").get_data(as_text=True)
    check("accountability rows carry role + masked staff ID",
          "Staff ID" in acct and meta["1"]["role"] in acct)
    r = nina.post("/add-note", data={"handoff_id": hid, "text": "Repeat vitals taken at bedside",
                                     "note_type": "UPDATE", "category": "GENERAL",
                                     "performed_by": "8",
                                     "id_confirm_name": "on", "id_confirm_dob": "on"})
    check("a note can explicitly name its performer (302)", r.status_code == 302)
    upd = nina.get("/patient/A44219?section=UPDATES").get_data(as_text=True)
    check("the named performer renders separately from the recorder",
          ("Performed by: " + meta["8"]["name"]) in upd
          and ("Recorded by " + meta["3"]["name"]) in upd)

    print("== Notifications: deep links + Simulate ==")
    feed = nina.get("/notifications").get_data(as_text=True)
    check("alerts deep-link to a section with a highlight target",
          "section=" in feed and "hl=" in feed and "Open the exact record" in feed)
    check("the Simulate control is offered", "Simulate incoming alert" in feed)
    check("the audible-alert toggle is offered", 'id="audible-toggle"' in feed)
    r = nina.post("/notifications/simulate")
    check("simulate redirects back to the center", r.status_code == 302)
    feed = nina.get("/notifications").get_data(as_text=True)
    check("the simulated alert is clearly labeled",
          "Simulated incoming alert" in feed and "SIMULATION" in feed)
    m = re.search(r'href="(/patient/A44219\?section=[A-Z_]+&amp;hl=[^"]*)"', feed)
    check("an exact-record link is present for Johnson", m is not None)
    if m:
        target = nina.get(m.group(1).replace("&amp;", "&")).get_data(as_text=True)
        check("the linked record renders highlighted", ' hl"' in target or "hl-wrap" in target)

    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
