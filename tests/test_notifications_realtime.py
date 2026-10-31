"""
Real-time notification alerts (Oct 31 round, branch uat-nina).

Answers the reviewer finding (Nina): "we don't get notifications — we
have to search, and we don't know things have changed until they've
changed." Covers:
  - /api/notifications: the bell's JSON feed (unread counts + latest
    items with exact-record links), consistent with the server-side feed
  - the bell (badge + panel + polling script) on My Patients, the
    Operations Board, and the patient workspace
  - consult requests and stage changes arriving LABELED as consult
    notifications, deep-linked to the Consultations tab, instead of
    anonymous "New record" items; seeded consult records surface as
    "Consult update"
  - handoff creation alerting the assignee ("New assignment") and the
    rest of the care team ("New handoff") — never the creator
  - escalation (the app's urgent state) arriving ack-required, plus
    completion and cancellation alerts
  - /notifications/mark-read: reading zeroes the unread count and is
    NOT acknowledgment (ack-required items stay unacknowledged)

Run:  python tests/test_notifications_realtime.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as handoff_app
from seed_demo import build_seed_care, build_seed_handoffs

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
    pw = "NinaUAT2026!" if username == "njohnson" else "handoff123"
    resp = client.post("/login", data={"username": username, "password": pw})
    assert resp.status_code == 302, username
    return client

def api(client):
    r = client.get("/api/notifications")
    assert r.status_code == 200
    return json.loads(r.get_data(as_text=True))

def feed_for(uid):
    return handoff_app.notification_feed(
        handoff_app.USERS[uid], handoff_app.load_handoffs(),
        handoff_app.load_care(), handoff_app.user_meta())

def find_handoff(event_text):
    for h in handoff_app.load_handoffs():
        if h.get("event") == event_text:
            return h
    return None

ID2 = {"id_confirm_name": "on", "id_confirm_dob": "on"}

def main():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    handoff_app.DATA_FILE = path
    care_path = handoff_app.care_file()
    if os.path.exists(care_path):
        os.unlink(care_path)
    handoff_app.save_handoffs(build_seed_handoffs())
    handoff_app.save_care(build_seed_care())

    nina = login("njohnson")        # id 3 — the reviewer
    thompson = login("nthompson")   # id 4 — charge nurse, unit-wide
    brooks = login("tbrooks")       # id 7 — clinician on Lee's team

    print("== The bell's JSON feed ==")
    data = api(brooks)
    check("api/notifications returns unread + items",
          isinstance(data.get("unread"), int) and isinstance(data.get("items"), list))
    server_unread = handoff_app.notif_unread_count(
        handoff_app.USERS["7"], handoff_app.load_handoffs(),
        handoff_app.load_care(), handoff_app.user_meta())
    check("api unread count matches the server-side feed", data["unread"] == server_unread)
    check("every api item carries an exact-record link",
          all("/patient/" in it["url"] and "section=" in it["url"] for it in data["items"]))
    r = handoff_app.app.test_client().get("/api/notifications")
    check("the api requires sign-in", r.status_code in (302, 401))

    print("== Seeded consult records surface as consult notifications ==")
    # The full feed, not the bell's latest-8 window: a unit-wide feed is
    # long, and the seeded consult records are not among its newest 8.
    consult_items = [it for it in feed_for("4") if it["kind"] == "CONSULT_RECORD"]
    check("a seeded consult record reaches a teammate labeled 'Consult update'",
          any(it["label"] == "Consult update" and it["case_id"] == "H72410"
              for it in consult_items))

    print("== The bell is on every main surface ==")
    for url in ["/", "/board", "/patient/E90214"]:
        html = brooks.get(url).get_data(as_text=True)
        check(f"bell + badge + panel + polling at {url}",
              'id="hn-bell"' in html and 'id="hn-badge"' in html
              and 'id="hn-panel"' in html and "/api/notifications" in html)

    print("== Consult request + stage changes notify the team, labeled ==")
    r = nina.post("/consults/request", data={
        "case_id": "E90214", "service": "Cardiology",
        "reason": "Chest pain evaluation", **ID2})
    check("consult request is recorded (302)", r.status_code == 302)
    data = api(brooks)
    req = [it for it in data["items"] if it["kind"] == "CONSULT_REQUESTED"
           and it["case_id"] == "E90214"]
    check("teammate's bell feed shows 'Consult requested'",
          len(req) == 1 and req[0]["label"] == "Consult requested")
    check("a consult request requires acknowledgment", req and req[0]["ack_required"] is True)
    check("the alert deep-links to the Consultations tab",
          req and "section=CONSULTS" in req[0]["url"])
    check("the requester is not notified about her own request",
          not any(it["kind"] == "CONSULT_REQUESTED" for it in feed_for("3")))
    cid = handoff_app.load_care()["consults"]["E90214"][-1]["id"]
    r = nina.post("/consults/stage", data={
        "case_id": "E90214", "consult_id": cid, "stage": "NOTIFIED", **ID2})
    check("stage NOTIFIED is recorded (302)", r.status_code == 302)
    labels = [it["label"] for it in api(brooks)["items"]]
    check("the team sees 'Consult — Service notified'", "Consult — Service notified" in labels)
    r = nina.post("/consults/stage", data={
        "case_id": "E90214", "consult_id": cid, "stage": "ACKNOWLEDGED", **ID2})
    check("stage ACKNOWLEDGED is recorded (302)", r.status_code == 302)
    labels = [it["label"] for it in api(brooks)["items"]]
    check("the team sees 'Consult — Acknowledged'", "Consult — Acknowledged" in labels)

    print("== Handoff creation alerts the assignee and the team ==")
    r = nina.post("/create-handoff", data={
        "patient_name": "LEE, K", "case_id": "E90214",
        "event": "STAT ECG review", "owner": "7"})
    check("handoff is created (302)", r.status_code == 302)
    h1 = find_handoff("STAT ECG review")
    check("the new handoff is on the record", h1 is not None)
    mine = [it for it in feed_for("7") if "STAT ECG review" in it["text"]]
    check("the assignee gets 'New assignment' (ack required)",
          any(it["label"] == "New assignment" and it["ack_required"] for it in mine))
    team = [it for it in feed_for("4") if "STAT ECG review" in it["text"]]
    check("a unit-wide teammate gets 'New handoff'",
          any(it["label"] == "New handoff" for it in team))
    check("the creator is not alerted about her own handoff",
          not any("STAT ECG review" in it["text"] for it in feed_for("3")))

    print("== Escalation (urgent), completion, cancellation ==")
    hid = h1["handoff_id"]
    r = brooks.post("/update-status", data={"handoff_id": hid, "status": "IN_PROGRESS"})
    check("owner starts the handoff (302)", r.status_code == 302)
    r = brooks.post("/update-status", data={"handoff_id": hid, "status": "ESCALATED"})
    check("owner escalates the handoff (302)", r.status_code == 302)
    data = api(nina)
    esc = [it for it in data["items"] if it["label"] == "Task escalated"
           and "STAT ECG review" in it["text"]]
    check("the escalation reaches the team through the bell feed",
          len(esc) == 1 and esc[0]["ack_required"] is True)
    check("ack_unread counts unacknowledged alerts", api(thompson)["ack_unread"] >= 1)
    r = brooks.post("/update-status", data={
        "handoff_id": hid, "status": "COMPLETED",
        "outcome": "ECG reviewed — no acute changes; cardiology aware."})
    check("owner completes with a documented outcome (302)", r.status_code == 302)
    done = [it for it in feed_for("3") if it["label"] == "Task completed"
            and "STAT ECG review" in it["text"]]
    check("the completion reaches the team", len(done) == 1)
    r = nina.post("/create-handoff", data={
        "patient_name": "LEE, K", "case_id": "E90214",
        "event": "Family meeting follow-up", "owner": "7"})
    h2 = find_handoff("Family meeting follow-up")
    r = brooks.post("/cancel-handoff", data={
        "handoff_id": h2["handoff_id"], "reason": "Family rescheduled"})
    check("owner cancels with a reason (302)", r.status_code == 302)
    canc = [it for it in feed_for("3") if it["label"] == "Handoff canceled"
            and "Family meeting follow-up" in it["text"]]
    check("the cancellation reaches the team", len(canc) == 1)

    print("== Mark read is not acknowledgment ==")
    check("brooks has unread alerts before mark-read", api(brooks)["unread"] > 0)
    r = brooks.post("/notifications/mark-read")
    body = json.loads(r.get_data(as_text=True)) if r.status_code == 200 else {}
    check("mark-read answers ok", r.status_code == 200 and body.get("ok") is True)
    check("unread count is zero after mark-read", api(brooks)["unread"] == 0)
    req = [it for it in feed_for("7") if it["kind"] == "CONSULT_REQUESTED"]
    check("the consult alert is read...", req and req[0]["read"] is True)
    check("...but still unacknowledged", req and req[0]["acked"] is False)
    r = brooks.post("/notifications/ack", data={"key": req[0]["key"]})
    check("acknowledging still works through the Center route (302)", r.status_code == 302)
    req = [it for it in feed_for("7") if it["kind"] == "CONSULT_REQUESTED"]
    check("acknowledgment is recorded separately", req and req[0]["acked"] is True)

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
