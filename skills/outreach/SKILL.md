---
name: outreach
description: "Draft personalized outreach messages for LinkedIn connections, hiring managers, or recruiters. Creates targeted messages using a hook + proof + proposal structure. Under 300 characters for connection requests. Use when someone says 'draft outreach', 'message the recruiter', 'reach out to', or 'write a LinkedIn message'."
argument-hint: "<contact name and company, or 'outreach for Company'>"
user-invocable: true
allowed-tools:
  - Read
  - Write
  - WebSearch
  - Glob
---

# Draft Outreach

Create personalized outreach messages for job search networking.

## Step 0: Load Context

1. Read `data/profile.yml`
2. Check `data/research/{company}.md` for company intelligence
3. Check `data/evaluations/` for any evaluation at this company

If no company research exists:
> "I don't have research on {company} yet. Better outreach comes from
> better intel. Want me to research them first, or should I draft
> something with what I know?"

## Step 1: Identify the Contact

Parse user input for: contact name, title, company, platform.

If no specific contact named, suggest based on research file:
> "Based on my research, here are contacts at {company}:
> {list from research}
> Who would you like to reach out to?"

## Step 2: Determine Message Type

| Type | When | Length |
|---|---|---|
| LinkedIn connection request | No existing connection | Under 300 characters |
| LinkedIn message | Already connected | 100-200 words |
| Cold email | Have their email | 100-150 words |
| Follow-up | Already reached out, no response 5+ days | 50-75 words |

Ask the user which type if not clear from context.

## Step 3: Generate Using 3-Part Structure

### Part 1: Hook (about THEM, not you)

Reference something specific about the company, their work, or a recent event.

Bad: "I'm really interested in your company" (about you)
Bad: "I'd love to connect" (generic)
Good: "Your team's work on {specific project/launch} caught my attention"
Good: "I noticed {company} just {recent event from research}"

### Part 2: Proof (one quantifiable thing about you)

One sentence. One number. Directly relevant to their world.

Bad: "I have 10 years of experience in marketing"
Good: "I grew organic traffic 3x at {Company} in 8 months"
Good: "I managed a $2M portfolio with 98% client retention"

Pull the most relevant proof point from the user's profile that connects
to the target company's needs.

### Part 3: Proposal (low-pressure ask)

Bad: "Can you refer me?" (presumptuous)
Bad: "I'd love to pick your brain" (vague, one-sided)
Good: "Would you be open to a 15-minute chat about what {team} looks for?"
Good: "I'd appreciate any advice on standing out for the {role} opening"

## Step 4: Output

```
## Outreach: {Contact Name} at {Company}

**Platform:** {LinkedIn connection / LinkedIn message / Email / Follow-up}
**Context:** {role or department}

---

{the message, properly formatted}

---

**Character count:** {n} / {limit for platform}
**Tone:** {Professional / Warm / Direct}
```

## Step 5: Offer Variations

> "Want me to:
> - **Adjust the tone?** (more formal / more casual / more direct)
> - **Write for a different platform?** (email instead of LinkedIn)
> - **Draft a follow-up** for if they don't respond in a week?"

## Rules

- NEVER draft messages that misrepresent the user's background
- NEVER suggest the user claim a connection that doesn't exist
- NEVER draft overly flattering or sycophantic messages
- Keep LinkedIn connection requests under 300 characters (hard limit)
- Every message must contain something specific (not a template)
- If no company research and no web search available, be honest:
  "This message would be stronger with specific company context.
  Consider researching them first."
