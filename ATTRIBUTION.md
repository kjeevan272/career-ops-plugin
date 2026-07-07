# Attribution

career-ops-plugin is a Claude Cowork adaptation of
[career-ops](https://github.com/santifer/career-ops) by santifer.

The original career-ops is a Claude Code skill for job search automation,
featuring the A-F scoring rubric, ATS-optimized resume generation, and
application tracking system that this plugin builds upon.

## What we adapted

- Blocks A-F evaluation system (generalized for all industries)
- ATS compliance rules for resume generation
- Application state machine and tracking
- Outreach 3-part message structure (hook + proof + proposal)
- "Never fabricate, never auto-submit" ethical principles

## What we changed

- Converted from Claude Code skill to Cowork plugin format
- Replaced 6 tech-specific archetypes with 15 industry-general archetypes
- Replaced Playwright/Node dependencies with computer use + WebFetch
- Added resume ingestion (paste your resume, Claude parses it)
- Added conversational setup wizard for non-technical users
- Redesigned output for Cowork's GUI (tables, checkboxes, scannable format)
- Added persona modifiers (recent grad, career changer, international)
- Added pipeline triage skill for bulk evaluation of scan results

## License

Both the original career-ops and this adaptation are MIT licensed.
