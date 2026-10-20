"""
Seed the Handoff demo board with a realistic ER scenario.

Timestamps are generated relative to "now" every time this runs, so the
dashboard always looks like a live shift: relative times, time-with-owner,
and stale highlights all read correctly whenever the demo is given.

Usage:  python seed_demo.py
Writes: data/handoffs.json  (the app's development data file)
Demo patients are fictional. Never seed real PHI.
"""
import json
import os
from datetime import datetime, timedelta, timezone

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "handoffs.json")

def build_seed_handoffs():
    """Return the demo board, with timestamps relative to right now."""
    NOW = datetime.now(timezone.utc)

    def t(minutes_ago):
        return (NOW - timedelta(minutes=minutes_ago)).isoformat()

    def hid(minutes_ago, suffix):
        return (NOW - timedelta(minutes=minutes_ago)).strftime("%Y%m%d%H%M%S") + "-" + suffix

    return [
    # 1) The hero journey: full baton chain, currently with the NP, in progress.
    {
        "handoff_id": hid(187, "a1b2"),
        "patient_name": "JOHNSON, M",
        "case_id": "A44219",
        "event": "MRI — Stroke Protocol",
        "initiator": 1,
        "owner": 3,
        "status": "IN_PROGRESS",
        "created_at": t(187),
        "updated_at": t(24),
        "history": [
            {"at": t(187), "event": "CREATED", "by": 1},
            {"at": t(180), "event": "STATUS_CHANGED_TO_IN_PROGRESS", "by": 1},
            {"at": t(176), "event": "RECORD_ADDED", "type": "ORDER", "text": "STAT MRI brain without contrast. NIHSS 14 on arrival.", "by": 2},
            {"at": t(150), "event": "OWNERSHIP_TRANSFERRED", "by": "1 → 3"},
            {"at": t(96), "event": "RECORD_ADDED", "type": "NOTE", "text": "Patient prepped for scanner. IV access confirmed, contrast allergy checked — none.", "by": 3},
            {"at": t(24), "event": "RECORD_ADDED", "type": "UPDATE", "text": "MRI in progress. Results expected within the hour — will escalate if not back by then.", "by": 3},
        ],
    },
    # 2) The escalated one: discharge placement stuck — the pain executives recognize.
    {
        "handoff_id": hid(322, "c3d4"),
        "patient_name": "GARCIA, L",
        "case_id": "B77102",
        "event": "Discharge — SNF Placement",
        "initiator": 7,
        "owner": 6,
        "status": "ESCALATED",
        "created_at": t(322),
        "updated_at": t(52),
        "history": [
            {"at": t(322), "event": "CREATED", "by": 7},
            {"at": t(300), "event": "STATUS_CHANGED_TO_IN_PROGRESS", "by": 7},
            {"at": t(210), "event": "RECORD_ADDED", "type": "NOTE", "text": "Two SNFs reviewing. Family prefers a facility near home (40222).", "by": 7},
            {"at": t(140), "event": "OWNERSHIP_TRANSFERRED", "by": "7 → 6"},
            {"at": t(52), "event": "STATUS_CHANGED_TO_ESCALATED", "by": 6},
            {"at": t(52), "event": "RECORD_ADDED", "type": "UPDATE", "text": "No bed offers yet. Bed has been held since morning — escalating for visibility.", "by": 6},
        ],
    },
    # 3) The quiet one: sitting NEW for over 2 hours — invisible work, made visible.
    {
        "handoff_id": hid(148, "e5f6"),
        "patient_name": "SMITH, J",
        "case_id": "C30981",
        "event": "Lab — Troponin Follow-Up",
        "initiator": 2,
        "owner": 4,
        "status": "NEW",
        "created_at": t(148),
        "updated_at": t(148),
        "history": [
            {"at": t(148), "event": "CREATED", "by": 2},
        ],
    },
    # 4) The proof it works: a completed chain from earlier in the shift.
    {
        "handoff_id": hid(410, "g7h8"),
        "patient_name": "BROWN, D",
        "case_id": "D55231",
        "event": "Bed Assignment — Telemetry",
        "initiator": 1,
        "owner": 5,
        "status": "COMPLETED",
        "created_at": t(410),
        "updated_at": t(296),
        "history": [
            {"at": t(410), "event": "CREATED", "by": 1},
            {"at": t(402), "event": "STATUS_CHANGED_TO_IN_PROGRESS", "by": 1},
            {"at": t(380), "event": "OWNERSHIP_TRANSFERRED", "by": "1 → 5"},
            {"at": t(340), "event": "RECORD_ADDED", "type": "NOTE", "text": "Telemetry bed 412 confirmed. Transport requested.", "by": 5},
            {"at": t(296), "event": "STATUS_CHANGED_TO_COMPLETED", "by": 5},
        ],
    },
    # 5) Fresh and moving: cardiology consult with the case manager.
    {
        "handoff_id": hid(38, "i9j0"),
        "patient_name": "LEE, K",
        "case_id": "E90214",
        "event": "Cardiology Consult",
        "initiator": 3,
        "owner": 7,
        "status": "IN_PROGRESS",
        "created_at": t(38),
        "updated_at": t(11),
        "history": [
            {"at": t(38), "event": "CREATED", "by": 3},
            {"at": t(30), "event": "STATUS_CHANGED_TO_IN_PROGRESS", "by": 3},
            {"at": t(18), "event": "OWNERSHIP_TRANSFERRED", "by": "3 → 7"},
            {"at": t(11), "event": "RECORD_ADDED", "type": "NOTE", "text": "Cardiology paged. Echo scheduled after consult.", "by": 7},
        ],
    },
    ]

def main():
    handoffs = build_seed_handoffs()
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(handoffs, f, indent=2)
    print(f"Seeded {len(handoffs)} demo handoffs -> {DATA_FILE}")
    for h in handoffs:
        print(f"  {h['status']:<12} {h['event']:<28} owner={h['owner']}  history={len(h['history'])} events")

if __name__ == "__main__":
    main()
