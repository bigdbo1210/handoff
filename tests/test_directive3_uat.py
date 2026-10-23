"""
Directive 3.0 UAT tests (branch uat-nina).

Covers the clinical-terminology integration into the functional app:
  - the reviewer's individual credential (the shared demo password no
    longer opens the reviewer account; everyone else is unchanged)
  - patient identifiers: DOB / MRN / FIN on the record, and search by
    name, DOB, MRN, and FIN
  - the two-identifier confirmation gate before documenting care
  - itemized task completion: outcome required, completion record kept,
    and completion never touches the patient's disposition
  - disposition staging: intent -> bed request -> acceptance -> sign-off,
    where a bed request or an acceptance never transfers responsibility,
    sign-off is blocked before acceptance, and only the responsible
    clinician can sign off
  - the Notifications Center: bed-request alerts reach the team with
    acknowledgment tracked separately from reading

Run:  python tests/test_directive3_uat.py
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

def login(username, password):
    client = handoff_app.app.test_client()
    resp = client.post("/login", data={"username": username, "password": password})
    return client, resp

def main():
    tmpdir = tempfile.mkdtemp()
    handoff_app.DATA_FILE = os.path.join(tmpdir, "handoffs.json")
    handoff_app.save_handoffs(build_seed_handoffs())

    print("== Reviewer credential ==")
    _, r = login("njohnson", "handoff123")
    check("shared demo password no longer opens the reviewer account", r.status_code == 200)
    nina, r = login("njohnson", "NinaUAT2026!")
    check("reviewer signs in with her individual credential", r.status_code == 302)
    _, r = login("dcarter", "handoff123")
    check("other demo accounts are unchanged", r.status_code == 302)
    brooks, _ = login("tbrooks", "handoff123")

    print("== Identifiers on the record and in search ==")
    html = nina.get("/").get_data(as_text=True)
    check("roster rows show DOB and MRN", "DOB 07/02/1955" in html and "MRN 7712045" in html)
    html = nina.get("/?q=7712045").get_data(as_text=True)
    check("search by MRN finds JOHNSON", "A44219" in html)
    check("search by MRN excludes LEE", "E90214" not in html)
    html = nina.get("/?q=07/02/1955").get_data(as_text=True)
    check("search by DOB finds JOHNSON", "A44219" in html)
    html = nina.get("/?q=5520117").get_data(as_text=True)
    check("search by FIN finds JOHNSON", "A44219" in html)
    page = nina.get("/patient/A44219").get_data(as_text=True)
    check("workspace header shows DOB, MRN, FIN",
          "DOB 07/02/1955" in page and "MRN 7712045" in page and "FIN 5520117" in page)

    print("== Two-identifier gate before documenting care ==")
    hid = [h["handoff_id"] for h in handoff_app.load_handoffs() if h["case_id"] == "A44219"][0]
    before = len(handoff_app.find_handoff(handoff_app.load_handoffs(), hid)["history"])
    r = nina.post("/add-note", data={"handoff_id": hid, "note_type": "NOTE",
                                     "text": "Ungated note should fail."})
    check("documenting without two identifiers -> 400", r.status_code == 400)
    after = len(handoff_app.find_handoff(handoff_app.load_handoffs(), hid)["history"])
    check("the ungated note changed nothing", after == before)
    r = nina.post("/add-note", data={"handoff_id": hid, "note_type": "NOTE",
                                     "text": "Identifiers confirmed at the bedside.",
                                     "id_confirm_name": "on", "id_confirm_dob": "on"})
    check("documenting with two identifiers -> 302", r.status_code == 302)
    ev = handoff_app.find_handoff(handoff_app.load_handoffs(), hid)["history"][-1]
    check("the entry records the identifier confirmation", ev.get("id_confirmed") is True)

    print("== Itemized completion ==")
    r = nina.post("/update-status", data={"handoff_id": hid, "status": "COMPLETED"})
    check("completing without a documented outcome -> 400", r.status_code == 400)
    r = nina.post("/update-status", data={"handoff_id": hid, "status": "COMPLETED",
                                          "outcome": "MRI completed; preliminary report in Diagnostics."})
    check("completing with a documented outcome -> 302", r.status_code == 302)
    h = handoff_app.find_handoff(handoff_app.load_handoffs(), hid)
    comp = h.get("completion") or {}
    check("completion record keeps who + role + outcome",
          comp.get("by") == 3 and comp.get("role") == "Nurse Practitioner (NP)"
          and "MRI completed" in comp.get("outcome", ""))
    page = nina.get("/patient/A44219?section=TASKS").get_data(as_text=True)
    check("workspace itemizes the completion", "Completed — MRI" in page and "Documented outcome:" in page)
    care = handoff_app.load_care()
    check("completing a task created no disposition change", "A44219" not in care["dispositions"])

    print("== Disposition: admit flow on LEE (E90214) ==")
    r = nina.post("/disposition/bed-request", data={"case_id": "E90214"})
    check("bed request before intent -> 400", r.status_code == 400)
    r = nina.post("/disposition/intent", data={"case_id": "E90214", "intent": "ADMIT",
                                               "service": "Cardiology (telemetry)"})
    check("intent to admit recorded", r.status_code == 302)
    care = handoff_app.load_care()
    d = care["dispositions"]["E90214"]
    check("the recorder is the responsible clinician", d["responsible"] == "3")
    r = nina.post("/disposition/bed-request", data={"case_id": "E90214"})
    check("bed request recorded", r.status_code == 302)
    care = handoff_app.load_care()
    d = care["dispositions"]["E90214"]
    check("a bed request does NOT transfer responsibility", d["responsible"] == "3" and d["completed"] is None)
    notif = [n for n in care["notifications"] if n["kind"] == "BED_REQUEST" and n["case_id"] == "E90214"]
    check("an attributed, ack-required bed-request notification exists",
          len(notif) == 1 and notif[0]["ack_required"] is True and notif[0]["by"] == "3")
    r = nina.post("/disposition/sign-off", data={"case_id": "E90214", "new_responsible": "7"})
    check("sign-off before acceptance -> 400", r.status_code == 400)
    r = nina.post("/disposition/acceptance", data={"case_id": "E90214",
                                                   "acceptor_label": "Cardiology — attending of record",
                                                   "service": "Cardiology (telemetry)"})
    check("acceptance recorded", r.status_code == 302)
    care = handoff_app.load_care()
    check("acceptance still does NOT transfer responsibility",
          care["dispositions"]["E90214"]["responsible"] == "3")
    r = brooks.post("/disposition/sign-off", data={"case_id": "E90214", "new_responsible": "7"})
    check("sign-off by a non-responsible clinician -> 403", r.status_code == 403)
    r = nina.post("/disposition/sign-off", data={"case_id": "E90214", "new_responsible": "7"})
    check("responsible clinician signs off", r.status_code == 302)
    care = handoff_app.load_care()
    d = care["dispositions"]["E90214"]
    check("sign-off records who signed, who accepted, and completes the disposition",
          d["completed"]["signed_off_by"] == "3" and d["completed"]["accepted_by"] == "7"
          and d["responsible"] == "7")
    check("a transfer notification was stored",
          any(n["kind"] == "TRANSFER_COMPLETE" and n["case_id"] == "E90214" for n in care["notifications"]))

    print("== Disposition: discharge flow on JOHNSON (A44219) ==")
    r = nina.post("/disposition/intent", data={"case_id": "A44219", "intent": "DISCHARGE",
                                               "service": "Home (self-care)"})
    check("intent to discharge recorded", r.status_code == 302)
    r = nina.post("/disposition/sign-off", data={"case_id": "A44219", "new_responsible": "7"})
    check("admit sign-off route refuses a discharge disposition", r.status_code == 400)
    r = nina.post("/disposition/complete", data={"case_id": "A44219"})
    check("responsible clinician completes the discharge", r.status_code == 302)
    care = handoff_app.load_care()
    check("discharge completion is on the record",
          care["dispositions"]["A44219"]["completed"]["signed_off_by"] == "3")

    print("== Notifications Center ==")
    feed = handoff_app.notification_feed(handoff_app.USERS["7"], handoff_app.load_handoffs(),
                                         handoff_app.load_care(), handoff_app.user_meta())
    bed = [i for i in feed if i["kind"] == "BED_REQUEST" and i["case_id"] == "E90214"]
    check("the bed-request alert reaches a teammate's feed", len(bed) == 1)
    check("it starts unacknowledged", bed and bed[0]["acked"] is False)
    r = brooks.get("/notifications")
    check("notifications page serves the teammate", r.status_code == 200 and "bed request" in r.get_data(as_text=True))
    r = brooks.post("/notifications/ack", data={"key": bed[0]["key"]})
    check("acknowledging returns to the center", r.status_code == 302)
    feed = handoff_app.notification_feed(handoff_app.USERS["7"], handoff_app.load_handoffs(),
                                         handoff_app.load_care(), handoff_app.user_meta())
    bed = [i for i in feed if i["kind"] == "BED_REQUEST" and i["case_id"] == "E90214"]
    check("acknowledgment is recorded (separate from reading)", bed and bed[0]["acked"] is True)
    feed_nina = handoff_app.notification_feed(handoff_app.USERS["3"], handoff_app.load_handoffs(),
                                              handoff_app.load_care(), handoff_app.user_meta())
    check("a clinician is not notified about her own bed request",
          not any(i["kind"] == "BED_REQUEST" and i["case_id"] == "E90214" for i in feed_nina))

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
