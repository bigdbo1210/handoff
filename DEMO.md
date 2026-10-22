# Handoff — Demo Guide

Everything needed to run Handoff and present it. Demo data is fictional —
never enter real patient information (PHI) into this development build.

---

## Live demo

**https://handoff-demo.onrender.com** — sign in with any demo account below
(password: handoff123). Hosted on Render's free plan: the service sleeps
when idle, so the first load can take up to a minute to wake; after that
it's fast. The board re-seeds itself fresh on every wake-up.

## Run it locally

```bash
pip install -r requirements.txt
python seed_demo.py     # load the demo ER board (re-run anytime to reset)
python app.py           # then open http://127.0.0.1:5000
```

## Demo logins

All demo accounts share the password **handoff123**.

| Username    | Person          | Role                     |
|-------------|-----------------|--------------------------|
| dcarter     | Dr. Carter      | ED Attending Physician   |
| dwilliams   | Dr. Williams    | Resident Physician       |
| njohnson    | Nina Johnson    | Nurse Practitioner (NP)  |
| epriddy     | Erin Priddy     | Registered Nurse (RN)    |
| nthompson   | Nurse Thompson  | Charge Nurse             |
| amorgan     | Alex Morgan     | Unit Clerk               |
| jlee        | Jordan Lee      | Care Coordinator         |
| tbrooks     | Taylor Brooks   | Case Manager             |

---

## The 5-minute executive demo

**The one-line problem (say this first):**
"When a patient's next step changes hands, ownership goes invisible — and
that's where delays, duplicated work, and dropped balls live. Handoff makes
the baton visible."

**0:00 — The board (sign in as dcarter)**
"This is a live unit board. Every card answers three questions at a glance:
what is it, whose is it, and how long have they had it."

**0:45 — The escalated one (GARCIA, L — red, ESCALATED)**
"This discharge has been stuck waiting on SNF placement. Notice — nobody
had to make a phone call to find out who owns it. It's Jordan Lee, it's
escalated, and the whole unit can see for how long. That red is invisible
work, made visible."

**1:30 — The quiet one (SMITH, J — amber, NEW for 2+ hours)**
"This lab follow-up hasn't moved in over two hours, so the board flags it.
In the old world, that's a result nobody is watching. Here, it glows."

**2:00 — The baton (open JOHNSON, M → View History)**
"Five different people have touched this stroke patient — the attending,
the resident who ordered the MRI, the nurse practitioner running it. Read the chain:
created → order added → baton passed attending to NP → updates. Many hands
on the record. Exactly one name on the next step."

**3:00 — The contributor moment (sign in as dwilliams)**
Add an ORDER to any handoff Dr. Williams doesn't own.
"On a real floor, five clinicians chart on the same patient. Dr. Williams
doesn't own this baton — but his order belongs on the record: time-stamped,
attributed, and the baton didn't move. Ownership stays singular; the
record stays collaborative."

**3:45 — Pass the baton, then try to break a rule**
Sign in as njohnson and transfer the MRI handoff to the Care Coordinator.
Then, as anyone else, try changing its status — the app refuses.
"The rules aren't a policy poster. The system enforces them: only the
owner moves the baton, nobody passes it to themselves, and completed is
final."

**4:30 — The executive view (metrics strip)**
"Across the top: how much is new, in progress, escalated, completed — how
many handoffs are waiting too long, and average completion time. This is
the view leadership gets: where care is flowing, and where it's stuck."

**Close**
"Handoff works alongside your EMR — it doesn't replace it. This is a
working development build: no real patient data yet, and the compliance
work comes before any clinical pilot. What I'm asking for is a pilot
conversation."

---

## Resetting the demo

Run `python seed_demo.py` again — timestamps regenerate relative to the
current time, so the board always looks like a live shift.

## Tests

```bash
python tests/test_workflow.py   # 29 end-to-end checks
```

---

## Patient-centered update (October 2026 — Clinical Feedback #002)

The application is now organized around the patient, in the two-screen
flow Nina specified:

**Screen 1 — My Patients (the home page).** A clean list of the patients
you follow or hold an open baton for. Each patient shows ONE latest-update
line (clicking it opens that patient's matching section), an unread dot,
and a compact strip of the latest Labs / Diagnostics / Consultations
status. Below it, "All Authorized Patients" lists every patient whose
care team you are on. The original status board still exists as the
**Operations Board** (link in the header) — nothing was taken away.

**Screen 2 — the patient workspace.** Only that patient: status summary
strip, care team, and sections for Labs, Diagnostics / Imaging,
Consultations, Pending Tasks, and the Handoff Accountability History.
Every entry shows who recorded it and that it was entered manually —
Handoff has no EMR feed and never pretends to.

**Three ideas that used to be blended are now separate:**

- **Care-team membership** decides who may open a patient's workspace —
  enforced by the server, not just hidden in the UI. Charge nurses and
  care coordinators hold unit-wide access by role.
- **The baton** decides accountability for one task — unchanged rules:
  only the owner changes status or transfers, completed is final.
- **Following** is personal: it shapes only your own My Patients list.
  Stop Following is blocked while you own an open task on that patient.

**Owner ≠ acknowledged.** Holding the baton means a task is yours;
**acknowledgment** means you confirmed you received it. Assignments to
someone else start unacknowledged, transfers reset acknowledgment, and
both facts show on every card.

**Cancel Handoff** is its own action (owner, charge nurse, or care
coordinator) and always records a reason.

**Automatic updates.** Pages poll for new activity every 20 seconds.
Updates never overwrite unsaved writing: the worklist swaps in fresh
patient blocks only when no form is dirty, and the patient page raises a
"tap to refresh" notice instead of reloading over your work.

The demo board now carries **18 fictional patients** (20 tasks — NGUYEN
and PATEL carry two simultaneous tasks each). New test suites:
`test_patient_model.py`, `test_permissions.py`, `test_ack_cancel.py`,
`test_navigation_load.py` — all suites pass alongside the original two.
