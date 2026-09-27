# Handoff

**Handoff** is a healthcare workflow and care-coordination application designed to make responsibility during patient transitions **visible, transferable, time-stamped, and accountable**.

Handoff creates a transparent, trackable “baton pass” between the people responsible for moving patient care forward.

The goal is simple:

> **Know where the handoff is. Know who owns it. Know what happens next.**

Handoff is being designed to work alongside existing healthcare systems rather than requiring organizations to replace their electronic medical record (EMR) platforms.

---

## 🚨 The Problem

Healthcare transitions often involve multiple people, departments, and systems.

A referral may be sent.  
A lab may be ordered.  
A patient may be waiting for placement.  
A discharge may require several approvals.

But once responsibility changes hands, a basic question can become surprisingly difficult to answer:

> **Who owns the next step right now?**

When handoffs are unclear:

- Patients may wait longer for care.
- Providers may duplicate work.
- Information can fall through the cracks.
- Responsibility for the next action may become unclear.
- Staff may spend time chasing calls, messages, and updates.
- Patients and families may be left wondering what is happening and what comes next.

Handoff is being built around that accountability gap.

---

## 💡 The Solution

Handoff provides a visible workflow for transitions of responsibility.

It does **not** aim to replace the EMR.

The long-term vision is for Handoff to function as a workflow and accountability layer that can work alongside existing healthcare technology.

### Think of a pizza tracker — for healthcare handoffs.

When you order a pizza, you can often see when:

- The order was received
- Preparation started
- The pizza entered the oven
- The order was completed
- Delivery began
- The order arrived

Handoff applies a similar principle to healthcare workflow:

- What was initiated?
- Who initiated it?
- Who currently owns it?
- What stage is it in?
- When did it last move?
- Who received responsibility next?
- Was it escalated?
- Was it completed?

Healthcare is obviously far more complex than delivering a pizza.

But the principle is powerful:

**Important work should not become invisible when responsibility changes hands.**

---

## 🏃 The Baton-Pass Model

The name **Handoff** comes from the relay-race concept of passing a baton.

The race cannot continue successfully unless responsibility for the baton moves clearly from one runner to the next.

Handoff applies that idea to healthcare.

A physician may initiate a process.

Responsibility may then move to a nurse.

The nurse may transfer responsibility to a care coordinator.

The care coordinator may complete the next step or transfer responsibility again.

Handoff creates a visible record of those transitions.

---

## 🔄 Current Handoff Lifecycle

The current web application supports four primary workflow states:

1. **NEW** — A handoff has been created.
2. **IN PROGRESS** — Work on the handoff is underway.
3. **ESCALATED** — The handoff requires additional attention.
4. **COMPLETED** — The handoff has been completed.

The workflow is designed around both **status** and **ownership**.

A handoff's status describes where the work stands.

Its current owner identifies who presently has responsibility for moving it forward.

---

## 👤 Ownership & Accountability

Each handoff currently records information including:

- Patient reference
- Case ID
- Event or reason for the handoff
- Initiator
- Current owner
- Current status
- Created timestamp
- Updated timestamp
- Handoff history

Ownership can be transferred between supported roles while preserving the history of the handoff.

This creates a basic chain of accountability:

**Who started it → who received it → what happened → who received it next.**

---

## 📋 Handoff History

Handoff maintains a history of workflow activity.

The current application can record and display events such as:

- Handoff created
- Status changed
- Ownership transferred
- Current owner updated

Instead of displaying internal role IDs to the user, the interface translates ownership history into readable roles.

For example:

**ED Attending Physician → Registered Nurse (RN)**

followed by:

**Registered Nurse (RN) → Care Coordinator**

This allows users to see how responsibility moved through the workflow.

---

## 👥 Current Roles

The current development version includes:

- ED Attending Physician
- Resident Physician
- Registered Nurse (RN)
- Charge Nurse
- Unit Clerk
- Care Coordinator
- Case Manager

These roles are part of the current development model and may evolve as Handoff is tested against real healthcare workflows.

---

## 💻 Current Application

Handoff has progressed beyond its original command-line proof of concept.

The current version includes a working **Flask web application** with a browser-based dashboard.

### Working functionality currently includes:

- Create a new handoff
- Display active handoffs on a dashboard
- Assign an initiator
- Assign a current owner
- Change workflow status
- Transfer ownership
- Preserve ownership-transfer history
- Display readable role-to-role transfers
- Track created and updated timestamps
- Display relative time such as “just now” or “16 min ago”
- Expand and review handoff history
- Persist development data using JSON

The application is still under active development.

---

## 🛠️ Current Technology

Handoff currently uses:

- **Python 3**
- **Flask**
- **HTML**
- **CSS**
- **JavaScript**
- **JSON** for temporary development persistence
- **Git/GitHub** for version control

JSON is being used during development and is **not intended to be the production database architecture**.

---

## 🛣️ Development Roadmap

### Phase 1 — Core Workflow Foundation ✅

- Handoff data model
- Status workflow
- Ownership model
- Ownership transfer
- History tracking
- JSON persistence

### Phase 2 — Working Web Application 🚧

- Flask backend ✅
- Browser-based dashboard ✅
- Create handoffs ✅
- Update status ✅
- Transfer ownership ✅
- Readable handoff history ✅
- Timestamp display ✅
- User authentication
- Improved role and identity management
- UI/UX redesign
- Expanded workflow testing

### Phase 3 — Application Foundation

Planned areas of development include:

- Production database architecture
- Authentication
- Authorization and permissions
- User and organization management
- Stronger audit logging
- Automated testing
- Secure configuration
- API architecture
- Deployment infrastructure

### Phase 4 — Healthcare Integration & Validation

Future exploration includes:

- Healthcare workflow pilots
- Clinical and operational user testing
- Standards-based interoperability
- FHIR/API integration patterns
- EMR-compatible workflow integration
- Security and privacy requirements
- Compliance assessment
- Organizational configuration
- Reporting and workflow analytics

---

## 🔐 Security & Healthcare Compliance

Handoff is currently a development application.

It is **not currently a HIPAA-compliant production system** and should not be used to store or process real protected health information (PHI).

Production deployment in healthcare would require substantial additional work involving areas such as:

- Authentication
- Authorization
- Encryption
- Secure data storage
- Audit controls
- Infrastructure security
- Privacy controls
- Organizational policies
- Healthcare regulatory and compliance requirements

Development and testing should use fictional or appropriately de-identified information.

---

## 🎯 Vision

Handoff exists to bring **clarity, accountability, visibility, and continuity** to transitions of responsibility in healthcare.

The moments between people, departments, and organizations are often where communication becomes difficult.

Handoff is being designed to make those moments visible.

When responsibility is clear:

- Staff can see who owns the next step.
- Workflow progress becomes easier to understand.
- Delays and escalations can become more visible.
- Administrators can better understand workflow movement.
- Patients and families can ultimately receive greater transparency into the progress of their care.

The long-term vision is straightforward:

> **Make responsibility visible.  
> Make ownership transferable.  
> Make progress time-stamped.  
> Make handoffs accountable.**

---

## ⚠️ Development Disclaimer

Handoff is currently under development and is intended for prototype, demonstration, research, and workflow-validation purposes.

It is **not currently a production healthcare system and is not currently intended for use with real patient PHI.**

---

## 👤 Author

**Derrick D. Dennis**

Healthcare professional, entrepreneur, and systems thinker focused on patient-centered operations, care continuity, accountability, and practical technology solutions.

Handoff is being developed from a simple question:

> **When responsibility for patient care changes hands, why shouldn't everyone who needs to know be able to see where the baton is?**
