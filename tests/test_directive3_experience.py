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
import io
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

    print("== Vitals: entry form + attributed correction (Derrick, 2026-10-23) ==")
    lee_v = nina.get("/patient/E90214?section=VITALS").get_data(as_text=True)
    check("the Vitals pane offers a real entry form", 'action="/vitals/add"' in lee_v)
    check("the Vitals pane offers a measurer-correction control",
          'action="/vitals/amend"' in lee_v and "Document or correct the measurer" in lee_v)
    r = nina.post("/vitals/add", data={
        "case_id": "E90214", "bp": "121/76", "hr": "72", "rr": "15",
        "spo2": "99% RA", "temp": "98.2°F", "measured_by": "8"})
    check("documenting vitals without two identifiers is refused (400)", r.status_code == 400)
    r = nina.post("/vitals/add", data={
        "case_id": "E90214", "bp": "121/76", "hr": "72", "rr": "15",
        "spo2": "99% RA", "temp": "98.2°F", "measured_by": "8",
        "id_confirm_name": "on", "id_confirm_dob": "on"})
    check("an authorized clinician can record new vital signs", r.status_code == 302)
    lee_v = nina.get("/patient/E90214?section=VITALS").get_data(as_text=True)
    check("the new set keeps measurer and recorder separate",
          "121/76" in lee_v and ("Measured by: " + meta["8"]["name"]) in lee_v
          and ("Recorded by " + meta["3"]["name"]) in lee_v)
    williams = login("dwilliams")
    r = williams.post("/vitals/add", data={
        "case_id": "E90214", "bp": "120/80", "hr": "70", "rr": "14",
        "spo2": "99% RA", "temp": "98.0°F", "measured_by": "",
        "id_confirm_name": "on", "id_confirm_dob": "on"})
    check("a clinician outside the care team cannot document vitals (403)",
          r.status_code == 403)
    m2 = re.search(r'name="entry_at" value="([^"]+)"', lee_v)
    check("the seeded entry exposes its amendment key", m2 is not None)
    if m2:
        r = nina.post("/vitals/amend", data={
            "case_id": "E90214", "entry_at": m2.group(1), "performed_by": "4",
            "reason": "Measurer confirmed with the charge nurse after the fact.",
            "id_confirm_name": "on", "id_confirm_dob": "on"})
        check("documenting a measurer later succeeds as an amendment", r.status_code == 302)
        lee_v2 = nina.get("/patient/E90214?section=VITALS").get_data(as_text=True)
        check("the amendment names the measurer and preserves the original recorder",
              ("Measured by: " + meta["4"]["name"]) in lee_v2
              and ("Recorded by " + meta["7"]["name"]) in lee_v2
              and "Correction · Measurer documented as" in lee_v2
              and "Original entry preserved" in lee_v2)
        lee_u = nina.get("/patient/E90214?section=UPDATES").get_data(as_text=True)
        check("the correction is filed on the patient's record (audit trail)",
              "Correction — measurer documented" in lee_u)

    print("== The complete demonstration journey (PATTERSON, R) ==")
    meta = handoff_app.user_meta()
    pov = nina.get("/patient/H72410?section=OVERVIEW").get_data(as_text=True)
    check("the journey patient is labeled a demonstration record",
          "Fictional demonstration record" in pov)
    check("the journey ends in a completed responsibility transfer",
          "Responsibility transferred" in pov and "Internal Medicine (Hospitalist)" in pov)
    pvit = nina.get("/patient/H72410?section=VITALS").get_data(as_text=True)
    check("journey vitals carry documented measurers (triage split included)",
          ("Measured by: " + meta["8"]["name"]) in pvit and "104/66" in pvit)
    plab = nina.get("/patient/H72410?section=LABS").get_data(as_text=True)
    check("journey labs tell the transfusion story", "Hemoglobin 7.1" in plab and "Hemoglobin 8.9" in plab)
    pcon = nina.get("/patient/H72410?section=CONSULTS").get_data(as_text=True)
    check("journey consult shows request, acknowledgment, performance, review",
          "consultation requested" in pcon.lower() and "acknowledged by the GI service" in pcon
          and "Consultation performed at bedside" in pcon and "recommendations reviewed" in pcon.lower())
    ptask = nina.get("/patient/H72410?section=TASKS").get_data(as_text=True)
    check("journey tasks carry specific documented outcomes",
          "transfused without reaction" in ptask and "bleeding duodenal ulcer treated with clips" in ptask)
    phist = nina.get("/patient/H72410?section=HISTORY").get_data(as_text=True)
    check("journey accountability timeline includes the baton pass", "Baton passed" in phist)

    print("== Sign-off summary display (Patterson + Garcia live flow) ==")
    pov = nina.get("/patient/H72410?section=OVERVIEW").get_data(as_text=True)
    check("Patterson's sign-off summary is on the record",
          "Sign-off summary" in pov and "Acceptance confirmed by the Hospitalist Service" in pov
          and "Outstanding at sign-off" in pov and "Repeat Hgb" in pov)
    jlee = login("jlee")
    r = jlee.post("/disposition/sign-off", data={
        "case_id": "B77102", "new_responsible": "7",
        "summary": "Intent to admit to Inpatient Rehabilitation. Acceptance confirmed by Maple Grove Rehab — Admissions. Completed: surgical repair and discharge planning. Outstanding: transport coordination."})
    check("an org-wide clinician can sign off with a summary", r.status_code == 302)
    gov = jlee.get("/patient/B77102?section=OVERVIEW").get_data(as_text=True)
    check("the summary renders in the disposition panel",
          "Sign-off summary" in gov and "Maple Grove Rehab — Admissions" in gov)
    gupd = jlee.get("/patient/B77102?section=UPDATES").get_data(as_text=True)
    check("the summary is filed on the patient's record", "Sign-off summary —" in gupd)

    print("== Structured consultation tracking ==")
    pcon = nina.get("/patient/H72410?section=CONSULTS").get_data(as_text=True)
    check("Patterson's GI consult is fully staged through sign-off",
          "Consultation status:" in pcon and "Consultant signed off" in pcon
          and "Service notified:" in pcon and "Recommendations documented:" in pcon)
    check("consult stages carry actor, role, staff ID, and exact time",
          "GI service — fellow on call" in pcon and "Staff ID" in pcon
          and re.search(r"[A-Z][a-z]{2} \d{1,2}, \d{4} · \d{1,2}:\d{2} (AM|PM) E[DS]T", pcon))
    jcon = nina.get("/patient/A44219?section=CONSULTS").get_data(as_text=True)
    check("Johnson's neurology consult is honestly mid-flight",
          "Neurology" in jcon and "Not yet recorded" in jcon)
    r = nina.post("/consults/request", data={
        "case_id": "E90214", "service": "Cardiology",
        "reason": "Rule-out pathway — staged tracking test",
        "id_confirm_name": "on", "id_confirm_dob": "on"})
    check("a clinician can request a tracked consultation", r.status_code == 302)
    lee_con_html = nina.get("/patient/E90214?section=CONSULTS").get_data(as_text=True)
    check("the requested consult shows its first stage",
          "Consultation status:" in lee_con_html and "Requested" in lee_con_html)
    import json as _json
    care_now = handoff_app.load_care()
    new_consult = care_now["consults"]["E90214"][-1]
    cid = new_consult["id"]
    r = nina.post("/consults/stage", data={
        "case_id": "E90214", "consult_id": cid, "stage": "PERFORMED",
        "id_confirm_name": "on", "id_confirm_dob": "on"})
    check("stages cannot skip ahead (PERFORMED before NOTIFIED -> 400)", r.status_code == 400)
    r = nina.post("/consults/stage", data={
        "case_id": "E90214", "consult_id": cid, "stage": "NOTIFIED",
        "note": "Cardiology service paged", "id_confirm_name": "on", "id_confirm_dob": "on"})
    check("the next stage records in order", r.status_code == 302)
    r = nina.post("/consults/stage", data={
        "case_id": "E90214", "consult_id": cid, "stage": "ACKNOWLEDGED",
        "actor_label": "Cardiology — fellow on call",
        "id_confirm_name": "on", "id_confirm_dob": "on"})
    check("an external acknowledger is recorded as an actor label", r.status_code == 302)
    lee_con_html = nina.get("/patient/E90214?section=CONSULTS").get_data(as_text=True)
    check("the tracker renders the recorded stages with the external actor",
          "Cardiology — fellow on call" in lee_con_html and "Service notified:" in lee_con_html)

    print("== UAT testing-session snapshots ==")
    home = nina.get("/").get_data(as_text=True)
    check("the home page offers session save/restore", "Testing session" in home
          and "/session/export" in home and "/session/import" in home)
    williams2 = login("dwilliams")
    home_w = williams2.get("/").get_data(as_text=True)
    check("restore is not offered to ordinary accounts", "/session/import" not in home_w
          and "/session/export" in home_w)
    r = nina.get("/session/export")
    check("export returns a snapshot file", r.status_code == 200
          and "handoff-uat-snapshot" in r.get_data(as_text=True))
    snap = r.get_data()
    payload = _json.loads(snap.decode("utf-8"))
    check("the snapshot carries the whole fictional world",
          payload["format"] == "handoff-uat-snapshot" and len(payload["handoffs"]) >= 24
          and "H72410" in payload["care"]["snapshots"])
    r = williams2.post("/session/import", data={
        "snapshot": (io.BytesIO(snap), "snap.json")}, content_type="multipart/form-data")
    check("an ordinary account cannot restore a snapshot (403)", r.status_code == 403)
    r = nina.post("/session/import", data={
        "snapshot": (io.BytesIO(snap), "snap.json")}, content_type="multipart/form-data")
    check("the reviewer can restore her own snapshot", r.status_code == 302)
    pov2 = nina.get("/patient/H72410?section=OVERVIEW").get_data(as_text=True)
    check("the world is intact after the restore round-trip",
          "PATTERSON" in pov2 or "GI bleed" in pov2)

    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
