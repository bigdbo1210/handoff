"""
Phone alerts — Web Push (Oct 31 round, branch uat-nina).

Derrick's directive: phone alerts at zero operating cost, Web Push
only, arriving like clinical text messages (Halo-style): patient +
what changed, tap opens the exact record. Nina's amendment: the alert
must be AUDIBLE/attention-getting — urgent items (the feed's existing
ack-required semantics: escalations, consult requests, assignments)
carry an `urgent` flag the service worker turns into a distinct
vibration pattern, renotify, and requireInteraction.

Covers:
  - installability: /sw.js (root scope, push handler with urgent
    vibration/renotify/requireInteraction), /manifest.webmanifest
    (standalone, 192/512 icons), manifest links on the main pages
  - the enable control on the bell panel + Notifications Center
  - /api/push/key: auth'd, serves the server's VAPID public key
  - /push/subscribe + /push/unsubscribe: per-user, auth'd, validated,
    deduplicated; several devices per clinician; subscribing sets a
    baseline — the backlog is never pushed
  - dispatch (transport mocked): a teammate's consult request pushes
    both of the subscriber's devices with a payload naming the patient
    + change + exact-record link and urgent=True; stage changes push
    urgent=False; the actor is never pushed their own action; nothing
    is pushed twice; dead subscriptions (410) are pruned
  - the open-session audible beep for ack-required items is present in
    the Notifications Center (wired in the Directive 3.0 round and the
    bell round — verified here, unchanged)

Run:  python tests/test_push_alerts.py
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

def sub(endpoint):
    return {"endpoint": endpoint,
            "keys": {"p256dh": "BP" + endpoint[-8:], "auth": "auth-" + endpoint[-4:]}}

ID2 = {"id_confirm_name": "on", "id_confirm_dob": "on"}
EP_A = "https://push.example/A-device"
EP_B = "https://push.example/B-device"
EP_N = "https://push.example/N-device"
EP_T = "https://push.example/T-device"

CALLS = []          # (endpoint, payload) recorded by the mock transport
GONE = set()        # endpoints the mock reports dead (410)

def mock_send(subscription, payload):
    ep = subscription.get("endpoint")
    if ep in GONE:
        raise handoff_app.PushGoneError("410 (mock)")
    CALLS.append((ep, payload))
    return True

def calls_to(ep):
    return [p for (e, p) in CALLS if e == ep]

def main():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    handoff_app.DATA_FILE = path
    care_path = handoff_app.care_file()
    if os.path.exists(care_path):
        os.unlink(care_path)
    handoff_app.save_handoffs(build_seed_handoffs())
    handoff_app.save_care(build_seed_care())
    handoff_app.send_web_push = mock_send   # transport mocked throughout

    anon = handoff_app.app.test_client()
    nina = login("njohnson")        # id 3
    brooks = login("tbrooks")       # id 7 — on Lee's team
    thompson = login("nthompson")   # id 4 — charge nurse, unit-wide

    print("== Installability: service worker, manifest, icons ==")
    r = anon.get("/sw.js")
    sw = r.get_data(as_text=True)
    check("/sw.js is served from the root scope", r.status_code == 200)
    check("the service worker receives pushes and shows notifications",
          "addEventListener('push'" in sw and "showNotification" in sw)
    check("urgent pushes vibrate distinctly, renotify, and persist",
          "vibrate" in sw and "renotify" in sw and "requireInteraction" in sw)
    check("tapping a notification opens its record",
          "notificationclick" in sw and "openWindow" in sw)
    r = anon.get("/manifest.webmanifest")
    man = json.loads(r.get_data(as_text=True)) if r.status_code == 200 else {}
    check("the web app manifest is served", r.status_code == 200
          and man.get("display") == "standalone")
    sizes = {i.get("sizes") for i in man.get("icons", [])}
    check("the manifest carries 192 and 512 icons",
          "192x192" in sizes and "512x512" in sizes)
    check("the icon asset itself is served",
          anon.get("/static/img/icon-192.png").status_code == 200)

    print("== The enable control is where clinicians already look ==")
    html = brooks.get("/").get_data(as_text=True)
    check("the bell panel carries the phone-alerts control",
          'id="push-alerts-box"' in html and "push.js" in html)
    check("pages link the manifest (installable / iPhone home screen)",
          'rel="manifest"' in html)
    html = brooks.get("/notifications").get_data(as_text=True)
    check("the Notifications Center carries the phone-alerts control",
          'id="push-alerts-box"' in html and "push.js" in html)
    check("the Center keeps its open-session audible beep for ack-required items",
          "audible-toggle" in html and "chip.need" in html and "AudioContext" in html)

    print("== The VAPID public key endpoint ==")
    r = anon.get("/api/push/key")
    check("the push key requires sign-in", r.status_code in (302, 401))
    r = brooks.get("/api/push/key")
    body = json.loads(r.get_data(as_text=True)) if r.status_code == 200 else {}
    pub, _pem, _subj = handoff_app._vapid_keys()
    check("a signed-in clinician gets the server's public key",
          r.status_code == 200 and body.get("publicKey") == pub and len(pub) > 40)

    print("== Subscription management: per-user, validated, deduplicated ==")
    r = anon.post("/push/subscribe", json=sub(EP_A))
    check("subscribing requires sign-in", r.status_code in (302, 401))
    r = brooks.post("/push/subscribe", json={"endpoint": EP_A})
    check("a subscription without keys is rejected", r.status_code == 400)
    r = brooks.post("/push/subscribe", json=sub(EP_A))
    body = json.loads(r.get_data(as_text=True)) if r.status_code == 200 else {}
    check("brooks registers device A", r.status_code == 200 and body.get("devices") == 1)
    care = handoff_app.load_care()
    check("the subscription is stored under brooks alone",
          [s["endpoint"] for s in care["push_subscriptions"].get("7", [])] == [EP_A]
          and not care["push_subscriptions"].get("3"))
    r = brooks.post("/push/subscribe", json=sub(EP_A))
    body = json.loads(r.get_data(as_text=True)) if r.status_code == 200 else {}
    check("re-registering the same device replaces, never duplicates",
          body.get("devices") == 1)
    r = brooks.post("/push/subscribe", json=sub(EP_B))
    body = json.loads(r.get_data(as_text=True)) if r.status_code == 200 else {}
    check("a second device is welcome", body.get("devices") == 2)

    print("== Subscribing sets a baseline: the backlog is never pushed ==")
    brooks.post("/notifications/mark-read")
    nina2 = login("njohnson")
    check("no pushes for anything that predates the subscription", CALLS == [])

    print("== Dispatch: a consult request reaches the subscriber's phone ==")
    r = nina.post("/consults/request", data={
        "case_id": "E90214", "service": "Cardiology",
        "reason": "Chest pain evaluation", **ID2})
    check("consult request is recorded (302)", r.status_code == 302)
    pa, pb = calls_to(EP_A), calls_to(EP_B)
    check("both of brooks's devices were pushed", len(pa) == 1 and len(pb) == 1)
    p = pa[0] if pa else {}
    check("the payload names the change and the patient",
          "CONSULT REQUESTED" in p.get("title", "") and "LEE" in p.get("title", ""))
    check("the payload body carries the essentials + ack note",
          "Acknowledgment required" in p.get("body", ""))
    check("the payload deep-links to the exact record",
          "section=CONSULTS" in p.get("url", "") and "/patient/E90214" in p.get("url", ""))
    check("a consult request is urgent (ack-required semantics)",
          p.get("urgent") is True)
    brooks.post("/notifications/mark-read")
    check("nothing is pushed twice", len(CALLS) == 2)

    print("== Stage changes push too, without the urgent flag ==")
    cid = handoff_app.load_care()["consults"]["E90214"][-1]["id"]
    r = nina.post("/consults/stage", data={
        "case_id": "E90214", "consult_id": cid, "stage": "NOTIFIED", **ID2})
    check("stage NOTIFIED is recorded (302)", r.status_code == 302)
    pa = calls_to(EP_A)
    check("the stage change was pushed",
          len(pa) == 2 and "SERVICE NOTIFIED" in pa[-1].get("title", ""))
    check("a stage change is not urgent", pa and pa[-1].get("urgent") is False)

    print("== The actor is never pushed their own action ==")
    r = nina.post("/push/subscribe", json=sub(EP_N))
    check("nina registers her own device", r.status_code == 200)
    before = len(calls_to(EP_N))
    r = brooks.post("/create-handoff", data={
        "patient_name": "LEE, K", "case_id": "E90214",
        "event": "Push check assignment", "owner": "3"})
    check("brooks creates a handoff for nina (302)", r.status_code == 302)
    pn = calls_to(EP_N)
    check("the assignee is pushed the new assignment",
          len(pn) == before + 1 and "NEW ASSIGNMENT" in pn[-1].get("title", ""))
    check("a new assignment is urgent (ack-required)",
          pn and pn[-1].get("urgent") is True)
    n_brooks_before = len(calls_to(EP_A))
    r = nina.post("/consults/stage", data={
        "case_id": "E90214", "consult_id": cid, "stage": "ACKNOWLEDGED", **ID2})
    check("nina's own stage change does not push nina",
          len(calls_to(EP_N)) == len(pn))
    check("...but it does push the teammate",
          len(calls_to(EP_A)) == n_brooks_before + 1)

    print("== Escalation pushes urgent to a unit-wide subscriber ==")
    r = thompson.post("/push/subscribe", json=sub(EP_T))
    check("thompson registers a device", r.status_code == 200)
    r = brooks.post("/create-handoff", data={
        "patient_name": "LEE, K", "case_id": "E90214",
        "event": "Push escalation check", "owner": "7"})
    h = [h for h in handoff_app.load_handoffs()
         if h.get("event") == "Push escalation check"][0]
    brooks.post("/update-status", data={"handoff_id": h["handoff_id"], "status": "IN_PROGRESS"})
    n_t = len(calls_to(EP_T))
    r = brooks.post("/update-status", data={"handoff_id": h["handoff_id"], "status": "ESCALATED"})
    check("escalation is recorded (302)", r.status_code == 302)
    pt = calls_to(EP_T)
    esc = [p for p in pt[n_t:] if "ESCALATED" in p.get("title", "")]
    check("the escalation was pushed to thompson", len(esc) == 1)
    check("an escalation payload is urgent", esc and esc[0].get("urgent") is True)

    print("== Dead subscriptions are pruned, live ones kept ==")
    GONE.add(EP_B)
    cid2 = cid
    r = nina.post("/consults/stage", data={
        "case_id": "E90214", "consult_id": cid2, "stage": "PERFORMED", **ID2})
    check("another stage change is recorded (302)", r.status_code == 302)
    care = handoff_app.load_care()
    eps = [s["endpoint"] for s in care["push_subscriptions"].get("7", [])]
    check("the 410 device was removed from the store", EP_B not in eps)
    check("the live device remains", EP_A in eps)
    GONE.clear()

    print("== Unsubscribe stops the phone, not the record ==")
    r = brooks.post("/push/unsubscribe", json={"endpoint": EP_A})
    check("unsubscribe answers ok", r.status_code == 200)
    care = handoff_app.load_care()
    check("the store no longer holds brooks's device",
          care["push_subscriptions"].get("7") == [])
    n_a = len(calls_to(EP_A))
    r = nina.post("/consults/stage", data={
        "case_id": "E90214", "consult_id": cid, "stage": "RECOMMENDATIONS", **ID2})
    check("a later change is recorded (302)", r.status_code == 302)
    check("no push is attempted to the removed device",
          len(calls_to(EP_A)) == n_a)
    feed = handoff_app.notification_feed(
        handoff_app.USERS["7"], handoff_app.load_handoffs(),
        handoff_app.load_care(), handoff_app.user_meta())
    check("...yet the change is still in brooks's bell feed (channel ≠ state)",
          any("RECOMMENDATIONS" in it["label"].upper() or "Recommendations" in it["label"]
              for it in feed))

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
