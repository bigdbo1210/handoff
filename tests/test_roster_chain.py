"""
Roster + baton-chain verification for the Handoff demo.

Covers the full demo account roster (all eight team members can sign in,
appear in the transfer dropdown, and carry the correct identity/role) and
the requested transfer chain on the JOHNSON stroke case:

    Nina Johnson -> Alex Morgan -> Nurse Thompson -> Dr. Carter

At every hop the Transfer form must be present for the current owner and
absent for the previous owner; a non-owner must still be able to add to
the record but must be refused a transfer; the audit history must show
every hop.

Run:  python tests/test_roster_chain.py
Uses a temporary data file — the development board is never touched.
"""
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as handoff_app
from seed_demo import build_seed_handoffs

ROSTER = [
    ("1", "dcarter", "Dr. Carter", "ED Attending Physician"),
    ("2", "dwilliams", "Dr. Williams", "Resident Physician"),
    ("3", "njohnson", "Nina Johnson", "Nurse Practitioner (NP)"),
    ("4", "nthompson", "Nurse Thompson", "Charge Nurse"),
    ("5", "amorgan", "Alex Morgan", "Unit Clerk"),
    ("6", "jlee", "Jordan Lee", "Care Coordinator"),
    ("7", "tbrooks", "Taylor Brooks", "Case Manager"),
    ("8", "epriddy", "Erin Priddy", "Registered Nurse (RN)"),
]
CASE = "A44219"  # JOHNSON, M — MRI Stroke Protocol, owned by Nina Johnson

passed = failed = 0


def check(label, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        print(f"  FAIL  {label}")


def fresh_board():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    handoff_app.DATA_FILE = path
    handoff_app.save_handoffs(build_seed_handoffs())
    return path


def login(username, password="handoff123"):
    if username == "njohnson" and password == "handoff123":
        password = "NinaUAT2026!"  # reviewer holds an individual UAT credential on this branch
    client = handoff_app.app.test_client()
    resp = client.post("/login", data={"username": username, "password": password})
    return client, resp


def card_for(client, case_id=CASE):
    html = client.get("/").get_data(as_text=True)
    # Split on card CONTAINERS only: class="card" or class="card stale-...",
    # not the inner card-head / card-case / card-meta divs.
    for chunk in re.split(r'(?=<div class="card[" ])', html):
        if f"Case {case_id}" in chunk and "card-case" in chunk:
            return chunk
    return ""


def has_transfer_form(card_html):
    return 'action="/transfer-owner"' in card_html


def dropdown_values(card_html):
    m = re.search(r'<select name="new_owner">(.*?)</select>', card_html, re.S)
    if not m:
        return []
    return re.findall(r'<option value="(\d+)"', m.group(1))


def johnson_id():
    for h in handoff_app.load_handoffs():
        if h["case_id"] == CASE:
            return h["handoff_id"]
    raise AssertionError("seed case missing")


def main():
    fresh_board()
    hid = johnson_id()

    print("== Roster: identity, role, sign-in ==")
    for uid, username, name, role in ROSTER:
        user = handoff_app.USERS[uid]
        check(f"{username} is {name}", user.name == name and user.username == username)
        check(f"{username} role is {role}", user.role_name == role)
        client, resp = login(username)
        check(f"{username} signs in", resp.status_code == 302)
        client.get("/logout")

    print("== Login page lists all eight demo accounts ==")
    anon = handoff_app.app.test_client()
    page = anon.get("/login").get_data(as_text=True)
    for _, username, _, _ in ROSTER:
        check(f"login page lists {username}", username in page)

    print("== Transfer dropdown contains the whole team ==")
    client, _ = login("njohnson", "NinaUAT2026!")
    card = card_for(client)
    values = dropdown_values(card)
    expected = sorted(uid for uid, *_ in ROSTER if uid != "3")
    check("dropdown offers all 7 other team members", sorted(values) == expected)

    print("== Baton chain: Nina -> Alex -> Thompson -> Carter ==")
    chain = [("njohnson", "3", "5"), ("amorgan", "5", "4"),
             ("nthompson", "4", "1"), ("dcarter", "1", None)]
    previous = None
    for username, uid, next_uid in chain:
        client, resp = login(username)
        check(f"{username} signs in", resp.status_code == 302)
        card = card_for(client)
        check(f"{username} (current owner) sees the Transfer form", has_transfer_form(card))
        if previous:
            p_client, _ = login(previous)
            p_card = card_for(p_client)
            check(f"{previous} (previous owner) no longer sees the Transfer form",
                  not has_transfer_form(p_card))
            p_client.get("/logout")
        if next_uid:
            resp = client.post("/transfer-owner",
                               data={"handoff_id": hid, "new_owner": next_uid})
            check(f"{username} transfers the baton", resp.status_code == 302)
            card = card_for(client)
            check(f"{username} loses the Transfer form right after passing",
                  not has_transfer_form(card))
        previous = username
        client.get("/logout")

    print("== Non-owner rights: contribute yes, transfer no ==")
    client, _ = login("jlee")
    resp = client.post("/add-note", data={"handoff_id": hid, "note_type": "NOTE",
                                          "text": "Chain test: coordinator note.", "id_confirm_name": "on", "id_confirm_dob": "on"})
    check("non-owner can add to the record", resp.status_code == 302)
    resp = client.post("/transfer-owner", data={"handoff_id": hid, "new_owner": "6"})
    check("non-owner transfer is refused (403)", resp.status_code == 403)
    resp = client.post("/update-status", data={"handoff_id": hid, "status": "COMPLETED"})
    check("non-owner status change is refused (403)", resp.status_code == 403)
    client.get("/logout")

    print("== Owner status change + audit history ==")
    client, _ = login("dcarter")
    resp = client.post("/update-status", data={"handoff_id": hid, "status": "ESCALATED"})
    check("current owner can change status", resp.status_code == 302)
    client.get("/logout")
    target = handoff_app.find_handoff(handoff_app.load_handoffs(), hid)
    hops = [e["by"] for e in target["history"] if e["event"] == "OWNERSHIP_TRANSFERRED"]
    check("audit shows 3 -> 5 -> 4 -> 1 (after the seed hop)",
          hops[-3:] == ["3 → 5", "5 → 4", "4 → 1"])
    events = [e["event"] for e in target["history"]]
    check("audit records the status change", "STATUS_CHANGED_TO_ESCALATED" in events)
    notes = [e for e in target["history"]
             if e["event"] == "RECORD_ADDED" and e.get("by") == 6]
    check("audit attributes the non-owner note to jlee", len(notes) == 1)
    check("final owner is Dr. Carter", str(target["owner"]) == "1")

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
