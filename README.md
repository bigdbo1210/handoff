# Handoff

**Handoff** is a lightweight, system-agnostic healthcare handoff and care-coordination tool designed to reduce delays, miscommunication, and anxiety during patient transitions of care.

It acts as a transparent, trackable “baton pass” between providers, administrators, care coordinators, and families—without replacing or modifying existing EMR systems.


## 🚨 The Problem

Healthcare handoffs are broken.

Patients are routinely delayed in receiving care because:
- Information is scattered across incompatible systems (Epic, Cerner, Allscripts, etc.)
- Referrals, labs, and documents are “sent” but not confirmed as received
- Ownership of the next step is unclear
- Families are left in the dark, increasing anxiety and mistrust

These gaps don’t just slow care—they create real risk.


## 💡 The Solution: Handoff

Handoff provides a **single source of truth** for patient transitions.

It does **not** replace EMRs.  
It **layers on top** of them.

Think of it like a **Domino’s Pizza Tracker for healthcare handoffs**:
- Everyone can see where the handoff is
- Who currently owns it
- What step is next
- When it last moved
- Why it might be blocked

No guessing. No chasing emails. No “I thought they had it.”


## 🧠 Core Concepts

### Handoff Record
Each handoff includes:
- Patient reference (MRN or initials + DOB)
- Initiator (who started the handoff)
- Current owner (who has the baton)
- Status (CREATED, IN_PROGRESS, COMPLETED, BLOCKED)
- Timestamped history of every action

Every action is logged. Nothing is invisible.


## 🔄 Handoff Lifecycle

1. **Created** – Handoff initiated
2. **In Progress** – Actively being worked
3. **Blocked** – Action stalled (reason required)
4. **Completed** – Successfully handed off and closed

Ownership can be reassigned at any time, with a clear audit trail.


## 👥 Intended Users

- Nursing Home Administrators
- Care Coordinators
- Nurses
- Physicians
- Social Workers
- Case Managers
- Families (read-only, future phase)


## 🧪 Current State (Prototype)

This repository currently contains a **Python CLI prototype** that demonstrates the core business logic of Handoff:

- Create a handoff
- List all handoffs
- View handoff details
- Update status
- Change ownership
- Persist data to JSON
- Maintain a full history log

This validates the workflow **before** building the web application.


## 🛠️ Tech Stack (Current)

- Python 3
- JSON (temporary persistence)
- CLI interface


## 🛣️ Roadmap

### Phase 1 – Logic Prototype ✅
- Core handoff model
- Status rules
- History tracking

### Phase 2 – Web App (Next)
- Flask backend
- Simple web UI
- Role-based access
- REST API

### Phase 3 – Healthcare-Ready
- Authentication
- Permissions
- Audit compliance
- EMR-agnostic integration patterns


## 🎯 Vision

Handoff exists to **return clarity, accountability, and dignity** to patient care transitions.

When handoffs are clear:
- Care moves faster
- Providers communicate better
- Administrators gain visibility
- Families feel informed, not ignored

This project is built from real-world frontline healthcare experience—not theory.


## ⚠️ Disclaimer

This is a prototype for educational and conceptual purposes.
It is **not** a HIPAA-compliant production system in its current form.


## 👤 Author

Built by a healthcare professional and systems thinker focused on patient-centered operations, care continuity, and practical technology solutions.
