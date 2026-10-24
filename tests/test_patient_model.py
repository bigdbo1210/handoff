"""
Patient-centered model tests (Assessment #002, Stage 1).

Covers derivation of patient records from the existing handoff store:
grouping by case reference, multi-task patients, care-team derivation
from history, latest-activity summary lines with section deep links, and
the migration invariant — every history event preserved exactly.

Run:  python tests/test_patient_model.py
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

def main():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    handoff_app.DATA_FILE = path
    seed = build_seed_handoffs()
    handoff_app.save_handoffs(seed)
    handoffs = handoff_app.load_handoffs()
    meta = handoff_app.user_meta()

    print("== Patient derivation ==")
    patients = handoff_app.all_patients(handoffs)
    check("seed groups into 19 patients", len(patients) == 19)  # +journey patient, 2026-10-23
    check("JOHNSON is one patient with one task", len(patients["A44219"]["tasks"]) == 1)
    check("NGUYEN is one patient with two simultaneous tasks", len(patients["G20817"]["tasks"]) == 2)
    check("PATEL is one patient with two simultaneous tasks", len(patients["H51092"]["tasks"]) == 2)
    check("patient carries demographics from the record",
          patients["A44219"]["patient_name"] == "JOHNSON, M" and patients["A44219"]["age"] == 71)
    check("patient carries its care context", patients["A44219"]["context"] == "Stroke Protocol")

    print("== Migration invariant: history preserved exactly ==")
    src_events = sum(len(h["history"]) for h in seed)
    out_events = sum(len(h["history"]) for p in patients.values() for h in p["tasks"])
    check("every history event survives grouping", src_events == out_events)
    same = all(
        json.dumps(h["history"], sort_keys=True) in
        [json.dumps(x["history"], sort_keys=True) for x in seed if x["handoff_id"] == h["handoff_id"]]
        for p in patients.values() for h in p["tasks"]
    )
    check("history payloads are byte-for-byte identical", same)

    print("== Care-team derivation from history ==")
    johnson_team = handoff_app.derived_member_ids(handoffs, "A44219")
    check("JOHNSON team includes initiator, contributor, owner",
          {"1", "2", "3"} <= johnson_team)
    lee_team = handoff_app.derived_member_ids(handoffs, "E90214")
    check("LEE team includes the transfer recipient", {"3", "7"} <= lee_team)
    nguyen_team = handoff_app.derived_member_ids(handoffs, "G20817")
    check("NGUYEN team merges both tasks' people", {"1", "2", "4", "7"} <= nguyen_team)

    print("== Latest-activity lines + deep-link sections ==")
    j = handoff_app.patient_latest(patients["A44219"]["tasks"], meta)
    check("JOHNSON latest line is the MRI update", "MRI in progress" in j["line"])
    check("JOHNSON latest deep-links to DIAGNOSTICS", j["section"] == "DIAGNOSTICS")
    s = handoff_app.patient_latest(patients["C30981"]["tasks"], meta)
    check("SMITH latest deep-links to LABS", s["section"] == "LABS")
    l = handoff_app.patient_latest(patients["E90214"]["tasks"], meta)
    check("LEE latest line is the cardiology update", "Cardiology paged" in l["line"])
    check("LEE latest deep-links to CONSULTS", l["section"] == "CONSULTS")

    print("== Status summary strip ==")
    strip_j = handoff_app.patient_section_statuses(patients["A44219"]["tasks"], meta)
    check("JOHNSON strip: diagnostics shows the MRI status", strip_j["DIAGNOSTICS"] is not None and "MRI" in strip_j["DIAGNOSTICS"])
    check("JOHNSON strip: consults shows neurology consulted-or-task line", strip_j["CONSULTS"] is None or isinstance(strip_j["CONSULTS"], str))
    strip_s = handoff_app.patient_section_statuses(patients["C30981"]["tasks"], meta)
    check("SMITH strip: labs shows the troponin task", strip_s["LABS"] is not None and "Troponin" in strip_s["LABS"])
    check("SMITH strip: diagnostics honestly empty", strip_s["DIAGNOSTICS"] is None)

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
