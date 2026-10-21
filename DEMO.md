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
