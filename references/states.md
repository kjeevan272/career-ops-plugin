# Application States

Source of truth for the status field in data/applications.md.

## State Machine

| State | Description | Can Transition To |
|---|---|---|
| Evaluated | JD scored, no action yet | Resume Ready, Skipped |
| Resume Ready | Resume tailored for this role | Applied, Skipped |
| Applied | Application submitted | Responded, Interview, Rejected, Withdrawn |
| Responded | Company sent a response | Interview, Rejected |
| Interview | Interview scheduled or in progress | Offer, Rejected, Withdrawn |
| Offer | Received an offer | Accepted, Withdrawn |
| Accepted | Accepted the offer | (terminal) |
| Rejected | Application rejected at any stage | (terminal) |
| Withdrawn | You withdrew from the process | (terminal) |
| Skipped | Decided not to apply after evaluation | (terminal) |

## Rules

1. The Status field in applications.md must contain EXACTLY one of these values
2. Status is case-insensitive when reading but should be written in Title Case
3. Withdrawn can be reached from any non-terminal state
4. Only update status with user confirmation
