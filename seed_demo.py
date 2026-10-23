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

# Patient identifiers for the Directive 3.0 UAT build: every seeded patient
# carries a date of birth and MRN, and a FIN where the encounter has one.
# The five review patients use the same fictional identifiers as the
# Directive 3.0 wireframe; the rest are derived deterministically so a
# re-seed always produces the same searchable values. All fictional.
_IDENTIFIERS = {
    "A44219": {"dob": "07/02/1955", "mrn": "7712045", "fin": "5520117"},
    "B77102": {"dob": "11/30/1943", "mrn": "6630982", "fin": "5520091"},
    "C30981": {"dob": "03/14/1958", "mrn": "8841207", "fin": "5520103"},
    "E90214": {"dob": "02/08/1961", "mrn": "5502716", "fin": "5520130"},
    "F31407": {"dob": "05/19/2019", "mrn": "9026118", "fin": None},
}

def _identifiers_for(case_id, age):
    if case_id in _IDENTIFIERS:
        return dict(_IDENTIFIERS[case_id])
    h = sum((i + 1) * ord(c) for i, c in enumerate(str(case_id)))
    year = 2026 - (age if isinstance(age, int) and age else 40)
    return {
        "dob": f"{1 + h % 12:02d}/{1 + h % 28:02d}/{year}",
        "mrn": str(1000000 + (h * 7919) % 8999999),
        "fin": "55" + str(10000 + (h * 104729) % 89999),
    }

def build_seed_care():
    """Seed the patient-centered sidecar for the UAT build: two worked
    disposition examples (Directive 3.0) with their notifications.
    Johnson: intent to admit + bed request recorded, acceptance pending —
    responsibility has NOT moved. Garcia: acceptance recorded, sign-off
    still pending — responsibility has NOT moved either."""
    NOW = datetime.now(timezone.utc)
    def t(minutes_ago):
        return (NOW - timedelta(minutes=minutes_ago)).isoformat()
    return {
        "members_added": {},
        "members_removed": {},
        "follows": [],
        "read_state": {},
        "dispositions": {
            "A44219": {
                "intent": "ADMIT", "service": "Cardiology (telemetry)",
                "intent_recorded": {"by": "3", "at": t(95)},
                "order_placed": {"by": "2", "entered_by": "5", "at": t(88)},
                "acceptance": None, "completed": None, "responsible": "3",
            },
            "B77102": {
                "intent": "ADMIT", "service": "Inpatient Rehabilitation \u2014 Maple Grove Rehab",
                "intent_recorded": {"by": "7", "at": t(300)},
                "order_placed": {"by": "7", "entered_by": None, "at": t(250)},
                "acceptance": {"recorded_by": "7", "acceptor_label": "Maple Grove Rehab \u2014 Admissions",
                               "service": "Inpatient Rehabilitation", "at": t(125)},
                "completed": None, "responsible": "3",
            },
        },
        "snapshots": {
            "A44219": {
                "overview": [{"text": "71-year-old admitted through the ED with acute ischemic stroke symptoms. Stroke protocol active; MRI completed, neurology engaged, thrombolysis window assessed on arrival.", "by": "1", "at": t(180), "source": "Manually entered"}],
                "hpi": [{"text": "Sudden onset left-sided weakness and slurred speech beginning ~07:40 today, witnessed by family. Last known well 07:30. NIHSS 14 on arrival. No head trauma, no seizure activity reported.", "by": "1", "at": t(178), "source": "Manually entered"}],
                "medical_history": [
                    {"text": "Hypertension — diagnosed 2011, on lisinopril.", "by": "3", "at": t(170), "source": "Manually entered"},
                    {"text": "Type 2 diabetes mellitus — metformin; last A1c 7.4 (per patient report).", "by": "3", "at": t(170), "source": "Manually entered"},
                    {"text": "Prior TIA (2024) — no residual deficits.", "by": "3", "at": t(169), "source": "Manually entered"}],
                "vitals": [
                    {"bp": "158/92", "hr": "88", "rr": "18", "spo2": "97% RA", "temp": "98.4\u00b0F", "by": "8", "at": t(150), "source": "Manually entered"},
                    {"bp": "149/88", "hr": "84", "rr": "17", "spo2": "98% RA", "temp": "98.6\u00b0F", "by": "3", "at": t(40), "source": "Manually entered"}],
            },
            "B77102": {
                "overview": [{"text": "82-year-old with a hip fracture after a fall at home. Surgical repair completed; discharge planning to inpatient rehabilitation is the active work.", "by": "7", "at": t(300), "source": "Manually entered"}],
                "hpi": [{"text": "Mechanical fall at home two days ago with immediate right hip pain and inability to bear weight. No loss of consciousness; denies chest pain or palpitations before the fall.", "by": "7", "at": t(295), "source": "Manually entered"}],
                "medical_history": [
                    {"text": "Osteoporosis — on calcium/vitamin D.", "by": "7", "at": t(290), "source": "Manually entered"},
                    {"text": "Chronic kidney disease, stage 3 — baseline creatinine 1.4.", "by": "7", "at": t(290), "source": "Manually entered"}],
                "vitals": [
                    {"bp": "132/78", "hr": "76", "rr": "16", "spo2": "96% RA", "temp": "98.2\u00b0F", "by": "6", "at": t(120), "source": "Manually entered"}],
            },
            "C30981": {
                "overview": [{"text": "67-year-old under evaluation for chest pain. Serial troponins and cardiology input are the active work; no disposition intent recorded yet.", "by": "2", "at": t(140), "source": "Manually entered"}],
                "hpi": [{"text": "Substernal chest pressure beginning ~3 hours before arrival, radiating to the left arm, with mild shortness of breath. Pain improved after aspirin in triage.", "by": "2", "at": t(138), "source": "Manually entered"}],
                "medical_history": [
                    {"text": "Hypertension — on amlodipine.", "by": "2", "at": t(130), "source": "Manually entered"},
                    {"text": "Hyperlipidemia — on atorvastatin.", "by": "2", "at": t(130), "source": "Manually entered"}],
                "vitals": [
                    {"bp": "146/84", "hr": "92", "rr": "18", "spo2": "98% RA", "temp": "98.1\u00b0F", "by": "4", "at": t(125), "source": "Manually entered"}],
            },
            "E90214": {
                "overview": [{"text": "65-year-old with chest pain under a cardiology rule-out pathway. Cardiology consultation is the active work.", "by": "3", "at": t(200), "source": "Manually entered"}],
                "hpi": [{"text": "Intermittent chest tightness over two days, worse with exertion, easing at rest. No radiation; mild nausea yesterday evening.", "by": "3", "at": t(198), "source": "Manually entered"}],
                "medical_history": [
                    {"text": "GERD — on omeprazole.", "by": "3", "at": t(195), "source": "Manually entered"},
                    {"text": "Former smoker — quit 2015.", "by": "3", "at": t(195), "source": "Manually entered"}],
                "vitals": [
                    {"bp": "138/82", "hr": "79", "rr": "16", "spo2": "99% RA", "temp": "98.3\u00b0F", "by": "7", "at": t(90), "source": "Manually entered"}],
            },
            "F31407": {
                "overview": [{"text": "7-year-old seen for a barky cough and noisy breathing overnight. Family at bedside; childcare setting notified per family request.", "by": "8", "at": t(100), "source": "Manually entered"}],
                "hpi": [{"text": "Barky cough and stridor beginning last night, worse when lying flat. Low-grade fever at home. Eating and drinking less than usual today.", "by": "8", "at": t(98), "source": "Manually entered"}],
                "medical_history": [
                    {"text": "No chronic conditions reported by family.", "by": "8", "at": t(95), "source": "Manually entered"},
                    {"text": "Immunizations per family report are current (record not yet verified).", "by": "8", "at": t(95), "source": "Source-verified entry"}],
                "vitals": [
                    {"bp": "102/64", "hr": "118", "rr": "24", "spo2": "97% RA", "temp": "99.8\u00b0F", "by": "8", "at": t(80), "source": "Manually entered"}],
            },
        },
        "notifications": [
            {"id": "seed-bed-a44219", "case_id": "A44219", "kind": "BED_REQUEST", "by": "2",
             "text": "Admission order recorded \u2014 bed request (bed-slip) for Cardiology (telemetry). A bed request does not transfer responsibility.",
             "at": t(88), "ack_required": True},
            {"id": "seed-acc-b77102", "case_id": "B77102", "kind": "ACCEPTANCE", "by": "7",
             "text": "Receiving acceptance recorded \u2014 Maple Grove Rehab accepted (Inpatient Rehabilitation). Sign-off still pending; responsibility has not transferred.",
             "at": t(125), "ack_required": False},
        ],
        "notif_state": {},
    }

def build_seed_handoffs():
    """Return the demo board, with timestamps relative to right now."""
    NOW = datetime.now(timezone.utc)

    def t(minutes_ago):
        return (NOW - timedelta(minutes=minutes_ago)).isoformat()

    def hid(minutes_ago, suffix):
        return (NOW - timedelta(minutes=minutes_ago)).strftime("%Y%m%d%H%M%S") + "-" + suffix

    board = [
    # 1) The hero journey: full baton chain, currently with the NP, in progress.
    {
        "handoff_id": hid(187, "a1b2"),
        "patient_name": "JOHNSON, M",
        "age": 71,
        "sex": "F",
        "case_id": "A44219",
        "event": "MRI — Stroke Protocol",
        "section": "DIAGNOSTICS",
        "patient_context": "Stroke Protocol",
        "initiator": 1,
        "owner": 3,
        "status": "IN_PROGRESS",
        "created_at": t(187),
        "updated_at": t(24),
        "acknowledged_at": t(150),
        "acknowledged_by": 3,
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
        "age": 82,
        "sex": "F",
        "case_id": "B77102",
        "event": "Discharge — SNF Placement",
        "section": "TASKS",
        "patient_context": "Discharge Planning",
        "initiator": 7,
        "owner": 6,
        "status": "ESCALATED",
        "created_at": t(322),
        "updated_at": t(52),
        "acknowledged_at": t(140),
        "acknowledged_by": 6,
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
        "age": 68,
        "sex": "M",
        "case_id": "C30981",
        "event": "Lab — Troponin Follow-Up",
        "section": "LABS",
        "patient_context": "Chest Pain Workup",
        "initiator": 2,
        "owner": 4,
        "status": "NEW",
        "created_at": t(148),
        "updated_at": t(148),
        "acknowledged_at": None,
        "acknowledged_by": None,
        "history": [
            {"at": t(148), "event": "CREATED", "by": 2},
        ],
    },
    # 4) The proof it works: a completed chain from earlier in the shift.
    {
        "handoff_id": hid(410, "g7h8"),
        "patient_name": "BROWN, D",
        "age": 58,
        "sex": "M",
        "case_id": "D55231",
        "event": "Bed Assignment — Telemetry",
        "section": "TASKS",
        "patient_context": "Telemetry Placement",
        "initiator": 1,
        "owner": 5,
        "status": "COMPLETED",
        "created_at": t(410),
        "updated_at": t(296),
        "acknowledged_at": t(380),
        "acknowledged_by": 5,
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
        "age": 65,
        "sex": "M",
        "case_id": "E90214",
        "event": "Cardiology Consult",
        "section": "CONSULTS",
        "patient_context": "Cardiology Evaluation",
        "initiator": 3,
        "owner": 7,
        "status": "IN_PROGRESS",
        "created_at": t(38),
        "updated_at": t(11),
        "acknowledged_at": t(15),
        "acknowledged_by": 7,
        "history": [
            {"at": t(38), "event": "CREATED", "by": 3},
            {"at": t(30), "event": "STATUS_CHANGED_TO_IN_PROGRESS", "by": 3},
            {"at": t(18), "event": "OWNERSHIP_TRANSFERRED", "by": "3 → 7"},
            {"at": t(11), "event": "RECORD_ADDED", "type": "NOTE", "text": "Cardiology paged. Echo scheduled after consult.", "by": 7},
        ],
    },
    # 6) Care coordination beyond the ER: a pediatric care-plan review,
    #    owned by Erin Priddy — family, therapy team, and nursing in sync.
    {
        "handoff_id": hid(64, "k4m9"),
        "patient_name": "MOORE, T",
        "age": 7,
        "sex": "M",
        "case_id": "F31407",
        "event": "Care Plan Review — Autism Services",
        "section": "TASKS",
        "patient_context": "Pediatric Care Plan",
        "initiator": 1,
        "owner": 8,
        "status": "IN_PROGRESS",
        "created_at": t(64),
        "updated_at": t(9),
        "acknowledged_at": t(41),
        "acknowledged_by": 8,
        "history": [
            {"at": t(64), "event": "CREATED", "by": 1},
            {"at": t(58), "event": "STATUS_CHANGED_TO_IN_PROGRESS", "by": 1},
            {"at": t(41), "event": "OWNERSHIP_TRANSFERRED", "by": "1 → 8"},
            {"at": t(9), "event": "RECORD_ADDED", "type": "NOTE", "text": "Weekly care plan reviewed with the therapy team. Family updated — new goals set for the week.", "by": 8},
        ],
    },
    # 7) Two simultaneous tasks on one patient — the multi-task case.
    {
        "handoff_id": hid(95, "n2p7"),
        "patient_name": "NGUYEN, T",
        "age": 54,
        "sex": "F",
        "case_id": "G20817",
        "event": "Lab — CBC Follow-Up",
        "section": "LABS",
        "patient_context": "GI Bleed Watch",
        "initiator": 1,
        "owner": 4,
        "status": "IN_PROGRESS",
        "created_at": t(95),
        "updated_at": t(33),
        "acknowledged_at": t(66),
        "acknowledged_by": 4,
        "history": [
            {"at": t(95), "event": "CREATED", "by": 1},
            {"at": t(88), "event": "STATUS_CHANGED_TO_IN_PROGRESS", "by": 1},
            {"at": t(70), "event": "OWNERSHIP_TRANSFERRED", "by": "1 → 4"},
            {"at": t(33), "event": "RECORD_ADDED", "type": "NOTE", "text": "CBC resulted — hemoglobin stable at 9.8. Recheck in 4 hours.", "by": 4},
        ],
    },
    {
        "handoff_id": hid(47, "q3r8"),
        "patient_name": "NGUYEN, T",
        "age": 54,
        "sex": "F",
        "case_id": "G20817",
        "event": "GI Consult",
        "section": "CONSULTS",
        "patient_context": "GI Bleed Watch",
        "initiator": 2,
        "owner": 7,
        "status": "NEW",
        "created_at": t(47),
        "updated_at": t(47),
        "acknowledged_at": None,
        "acknowledged_by": None,
        "history": [
            {"at": t(47), "event": "CREATED", "by": 2},
        ],
    },
    # 8) Escalated imaging with a resulted study on the record.
    {
        "handoff_id": hid(130, "s5t1"),
        "patient_name": "PATEL, R",
        "age": 63,
        "sex": "M",
        "case_id": "H51092",
        "event": "CT Head — Fall Evaluation",
        "section": "DIAGNOSTICS",
        "patient_context": "Fall Evaluation",
        "initiator": 2,
        "owner": 2,
        "status": "ESCALATED",
        "created_at": t(130),
        "updated_at": t(40),
        "acknowledged_at": t(128),
        "acknowledged_by": 2,
        "history": [
            {"at": t(130), "event": "CREATED", "by": 2},
            {"at": t(120), "event": "STATUS_CHANGED_TO_IN_PROGRESS", "by": 2},
            {"at": t(45), "event": "RECORD_ADDED", "type": "UPDATE", "category": "DIAGNOSTIC", "text": "CT head resulted: no acute bleed. Small chronic subdural noted — neurosurgery reviewing images.", "by": 2},
            {"at": t(40), "event": "STATUS_CHANGED_TO_ESCALATED", "by": 2},
        ],
    },
    {
        "handoff_id": hid(25, "u6v2"),
        "patient_name": "PATEL, R",
        "age": 63,
        "sex": "M",
        "case_id": "H51092",
        "event": "Transport — To Stepdown Unit",
        "section": "TASKS",
        "patient_context": "Fall Evaluation",
        "initiator": 6,
        "owner": 5,
        "status": "NEW",
        "created_at": t(25),
        "updated_at": t(25),
        "acknowledged_at": None,
        "acknowledged_by": None,
        "history": [
            {"at": t(25), "event": "CREATED", "by": 6},
        ],
    },
    # 9) A completed discharge from earlier in the shift.
    {
        "handoff_id": hid(500, "w8x3"),
        "patient_name": "DAVIS, S",
        "age": 47,
        "sex": "F",
        "case_id": "J66348",
        "event": "Discharge — Home with Services",
        "section": "TASKS",
        "patient_context": "Post-Op Recovery",
        "initiator": 7,
        "owner": 6,
        "status": "COMPLETED",
        "created_at": t(500),
        "updated_at": t(390),
        "acknowledged_at": t(425),
        "acknowledged_by": 6,
        "history": [
            {"at": t(500), "event": "CREATED", "by": 7},
            {"at": t(480), "event": "STATUS_CHANGED_TO_IN_PROGRESS", "by": 7},
            {"at": t(430), "event": "OWNERSHIP_TRANSFERRED", "by": "7 → 6"},
            {"at": t(400), "event": "RECORD_ADDED", "type": "NOTE", "text": "Home health arranged. Family confirmed pickup at 3 PM.", "by": 6},
            {"at": t(390), "event": "STATUS_CHANGED_TO_COMPLETED", "by": 6},
        ],
    },
    # 10) Echo in motion with Nina.
    {
        "handoff_id": hid(75, "y9z4"),
        "patient_name": "WILSON, J",
        "age": 59,
        "sex": "M",
        "case_id": "K90271",
        "event": "Echo — Ejection Fraction",
        "section": "DIAGNOSTICS",
        "patient_context": "Heart Failure Workup",
        "initiator": 1,
        "owner": 3,
        "status": "IN_PROGRESS",
        "created_at": t(75),
        "updated_at": t(20),
        "acknowledged_at": t(50),
        "acknowledged_by": 3,
        "history": [
            {"at": t(75), "event": "CREATED", "by": 1},
            {"at": t(70), "event": "STATUS_CHANGED_TO_IN_PROGRESS", "by": 1},
            {"at": t(55), "event": "OWNERSHIP_TRANSFERRED", "by": "1 → 3"},
            {"at": t(20), "event": "RECORD_ADDED", "type": "UPDATE", "category": "DIAGNOSTIC", "text": "Echo tech confirmed — study begins within 30 minutes.", "by": 3},
        ],
    },
    # 11) Fresh lab task awaiting its owner.
    {
        "handoff_id": hid(55, "b1c5"),
        "patient_name": "THOMAS, A",
        "age": 71,
        "sex": "F",
        "case_id": "L11845",
        "event": "Lab — Insulin Drip Titration",
        "section": "LABS",
        "patient_context": "DKA Management",
        "initiator": 2,
        "owner": 8,
        "status": "NEW",
        "created_at": t(55),
        "updated_at": t(55),
        "acknowledged_at": None,
        "acknowledged_by": None,
        "history": [
            {"at": t(55), "event": "CREATED", "by": 2},
        ],
    },
    # 12) Self-assigned consult, attending holding his own baton.
    {
        "handoff_id": hid(160, "d2e6"),
        "patient_name": "HARRIS, B",
        "age": 66,
        "sex": "M",
        "case_id": "M37720",
        "event": "Pulmonology Consult",
        "section": "CONSULTS",
        "patient_context": "COPD Exacerbation",
        "initiator": 1,
        "owner": 1,
        "status": "IN_PROGRESS",
        "created_at": t(160),
        "updated_at": t(28),
        "acknowledged_at": t(160),
        "acknowledged_by": 1,
        "history": [
            {"at": t(160), "event": "CREATED", "by": 1},
            {"at": t(150), "event": "STATUS_CHANGED_TO_IN_PROGRESS", "by": 1},
            {"at": t(28), "event": "RECORD_ADDED", "type": "NOTE", "text": "Pulmonology paged twice — fellow reviewing chart, callback expected shortly.", "by": 1},
        ],
    },
    # 13) Bed assignment moving through the clerk.
    {
        "handoff_id": hid(85, "f3g7"),
        "patient_name": "CLARK, E",
        "age": 78,
        "sex": "F",
        "case_id": "N54016",
        "event": "Bed Assignment — Medical Floor",
        "section": "TASKS",
        "patient_context": "Pneumonia Admission",
        "initiator": 4,
        "owner": 5,
        "status": "IN_PROGRESS",
        "created_at": t(85),
        "updated_at": t(12),
        "acknowledged_at": t(26),
        "acknowledged_by": 5,
        "history": [
            {"at": t(85), "event": "CREATED", "by": 4},
            {"at": t(80), "event": "STATUS_CHANGED_TO_IN_PROGRESS", "by": 4},
            {"at": t(30), "event": "OWNERSHIP_TRANSFERRED", "by": "4 → 5"},
            {"at": t(12), "event": "RECORD_ADDED", "type": "NOTE", "text": "Bed 618 assigned. Waiting on room cleaning — ETA 20 minutes.", "by": 5},
        ],
    },
    # 14) Escalated wound care with Erin.
    {
        "handoff_id": hid(200, "h4j8"),
        "patient_name": "LEWIS, D",
        "age": 52,
        "sex": "M",
        "case_id": "P78193",
        "event": "Wound Care — Dressing Change",
        "section": "TASKS",
        "patient_context": "Post-Surgical Wound",
        "initiator": 3,
        "owner": 8,
        "status": "ESCALATED",
        "created_at": t(200),
        "updated_at": t(60),
        "acknowledged_at": t(110),
        "acknowledged_by": 8,
        "history": [
            {"at": t(200), "event": "CREATED", "by": 3},
            {"at": t(190), "event": "STATUS_CHANGED_TO_IN_PROGRESS", "by": 3},
            {"at": t(120), "event": "OWNERSHIP_TRANSFERRED", "by": "3 → 8"},
            {"at": t(65), "event": "RECORD_ADDED", "type": "NOTE", "text": "Dressing changed. Wound edges reddened — surgeon notified, awaiting review.", "by": 8},
            {"at": t(60), "event": "STATUS_CHANGED_TO_ESCALATED", "by": 8},
        ],
    },
    # 15) Completed imaging from earlier in the shift.
    {
        "handoff_id": hid(600, "k5m9"),
        "patient_name": "WALKER, N",
        "age": 35,
        "sex": "F",
        "case_id": "Q22684",
        "event": "Ultrasound — Abdominal",
        "section": "DIAGNOSTICS",
        "patient_context": "Abdominal Pain Workup",
        "initiator": 2,
        "owner": 4,
        "status": "COMPLETED",
        "created_at": t(600),
        "updated_at": t(450),
        "acknowledged_at": t(530),
        "acknowledged_by": 4,
        "history": [
            {"at": t(600), "event": "CREATED", "by": 2},
            {"at": t(580), "event": "STATUS_CHANGED_TO_IN_PROGRESS", "by": 2},
            {"at": t(540), "event": "OWNERSHIP_TRANSFERRED", "by": "2 → 4"},
            {"at": t(470), "event": "RECORD_ADDED", "type": "UPDATE", "category": "DIAGNOSTIC", "text": "Ultrasound complete — gallbladder unremarkable, no stones seen.", "by": 4},
            {"at": t(450), "event": "STATUS_CHANGED_TO_COMPLETED", "by": 4},
        ],
    },
    # 16) Pharmacy review, brand new.
    {
        "handoff_id": hid(35, "n6p1"),
        "patient_name": "HALL, C",
        "age": 80,
        "sex": "M",
        "case_id": "R91537",
        "event": "Pharmacy Review — Med Rec",
        "section": "TASKS",
        "patient_context": "Medication Reconciliation",
        "initiator": 6,
        "owner": 7,
        "status": "NEW",
        "created_at": t(35),
        "updated_at": t(35),
        "acknowledged_at": None,
        "acknowledged_by": None,
        "history": [
            {"at": t(35), "event": "CREATED", "by": 6},
        ],
    },
    # 17) Rehab evaluation under way.
    {
        "handoff_id": hid(110, "q7r2"),
        "patient_name": "YOUNG, P",
        "age": 61,
        "sex": "F",
        "case_id": "S60429",
        "event": "PT Evaluation — Post Stroke",
        "section": "TASKS",
        "patient_context": "Stroke Rehabilitation",
        "initiator": 3,
        "owner": 6,
        "status": "IN_PROGRESS",
        "created_at": t(110),
        "updated_at": t(15),
        "acknowledged_at": t(85),
        "acknowledged_by": 6,
        "history": [
            {"at": t(110), "event": "CREATED", "by": 3},
            {"at": t(100), "event": "STATUS_CHANGED_TO_IN_PROGRESS", "by": 3},
            {"at": t(90), "event": "OWNERSHIP_TRANSFERRED", "by": "3 → 6"},
            {"at": t(15), "event": "RECORD_ADDED", "type": "NOTE", "text": "PT evaluated — patient ambulated 40 ft with walker. Sessions twice daily.", "by": 6},
        ],
    },
    # 18) Sepsis labs moving with the resident.
    {
        "handoff_id": hid(90, "s8t3"),
        "patient_name": "KING, M",
        "age": 57,
        "sex": "M",
        "case_id": "T34960",
        "event": "Lab — Blood Cultures",
        "section": "LABS",
        "patient_context": "Sepsis Workup",
        "initiator": 1,
        "owner": 2,
        "status": "IN_PROGRESS",
        "created_at": t(90),
        "updated_at": t(8),
        "acknowledged_at": t(55),
        "acknowledged_by": 2,
        "history": [
            {"at": t(90), "event": "CREATED", "by": 1},
            {"at": t(85), "event": "STATUS_CHANGED_TO_IN_PROGRESS", "by": 1},
            {"at": t(60), "event": "OWNERSHIP_TRANSFERRED", "by": "1 → 2"},
            {"at": t(8), "event": "RECORD_ADDED", "type": "UPDATE", "category": "LAB", "text": "Blood cultures drawn x2 before antibiotics. Results pending — preliminary at 24 hours.", "by": 2},
        ],
    },
    ]
    for h in board:
        h.update(_identifiers_for(h["case_id"], h.get("age")))
    return board

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
