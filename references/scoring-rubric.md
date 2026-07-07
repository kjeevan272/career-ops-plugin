# Evaluation Scoring Rubric

## Score Dimensions (weighted)

| Dimension | Base Weight | What It Measures |
|---|---|---|
| Hard requirement coverage | 30% | % of required qualifications matched by real experience |
| Seniority alignment | 15% | Your level vs. the role's level |
| Domain/industry match | 10% | Industry experience relevance |
| Compensation alignment | 10% | Your target vs. stated/estimated range |
| Location/remote fit | 10% | Geographic/work arrangement match |
| Career trajectory fit | 5% | Does this role make sense as your next step? |
| Credentials/licenses | 10% | Required certifications, degrees, clearances, bar admissions |
| Skills/portfolio | 10% | Specific skills, tools, or demonstrated work |

## Archetype Weight Adjustments

Different archetypes shift the weights. Adjustments are relative to the base weights above.

| Archetype | Adjustments |
|---|---|
| Technology/Engineering | Skills/portfolio +5%, Seniority -5% (skills matter more than titles) |
| Finance/Accounting | Credentials +10%, Location -5%, Trajectory -5% (CPA/CFA/Series licenses critical) |
| Healthcare/Medical | Credentials are **PASS/FAIL** (active license in required state is non-negotiable) |
| Legal/Compliance | Credentials are **PASS/FAIL** (bar admission in required jurisdiction) |
| Creative/Marketing/Design | Skills/portfolio +15%, Credentials -10%, Trajectory -5% (portfolio is the resume) |
| Operations/Supply Chain | Domain +5%, Skills -5% (industry-specific ops knowledge matters) |
| Sales/Business Development | Hard requirements reframed as "track record" (quota attainment replaces skills) |
| Education/Training | Credentials +5%, Domain +5%, Skills -10% (certification + subject match) |
| Executive/Leadership | Seniority +10%, Domain +5%, Skills -15% (scope and P&L matter most) |
| Trades/Skilled Labor | Credentials are **PASS/FAIL** (journeyman/master license, CDL class) |
| Customer Success/Support | Domain +5%, Skills +5%, Seniority -5%, Trajectory -5% |
| People/HR | Credentials +5%, Domain +5%, Skills -5%, Trajectory -5% (SHRM/PHR matter) |
| Government/Nonprofit | Credentials +5%, Domain +10%, Compensation -10%, Skills -5% |
| Scientific/R&D | Hard requirements +5%, Credentials +5%, Skills -5%, Trajectory -5% |
| Non-Software Engineering | Credentials +10%, Skills +5%, Seniority -10%, Trajectory -5% (PE license, certifications) |

## PASS/FAIL Credential Rules

For Healthcare, Legal, Trades, and Non-Software Engineering archetypes:

1. If the JD lists a **required** credential (license, certification, bar admission, PE stamp)
   AND the user's profile does NOT include it:
   - Cap the overall score at **2.0** regardless of other dimensions
   - Flag prominently: "This role requires [credential] which is not in your profile"
2. If the credential is listed as **preferred** (not required):
   - Reduce Credentials dimension score by 50%, but do not cap overall score
3. If profile data is incomplete (user hasn't listed credentials):
   - Score Credentials at 5/10 (neutral)
   - Flag: "Add your certifications and licenses to your profile for more accurate scoring"

## Score Thresholds

| Score | Label | Action |
|---|---|---|
| 4.5 - 5.0 | Excellent Match | Generate resume + draft application answers |
| 3.5 - 4.4 | Good Match | Generate resume |
| 3.0 - 3.4 | Worth Considering | Evaluate fully, flag risks clearly |
| 2.0 - 2.9 | Weak Match | Warn user, suggest better-matched roles |
| 1.0 - 1.9 | Poor Match | Advise against applying, explain why |

## Scoring Rules

1. Never inflate scores. A 3.2 is a real score. Honesty serves the user.
2. PASS/FAIL credentials override everything in regulated industries.
3. If the profile lacks information to score a dimension, score it at 5/10
   (neutral) and flag "incomplete data" so the user can add more detail.
4. Compensation misalignment (target is 30%+ above the role's range)
   does not kill the score but must be flagged in the summary.
5. "Years of experience" requirements are guidelines, not hard cutoffs.
   If the user has 5 years and the JD asks for 7, that's a partial match,
   not a disqualification.

## Persona Modifiers

Apply these adjustments when the user's profile indicates a special situation:

| Persona | Adjustment |
|---|---|
| Recent graduate | Reduce Hard Requirements weight by 10%, increase Trajectory by 10%. Emphasize internships, projects, education. |
| Career changer | Reduce Domain weight by 5%, increase Trajectory by 5%. Emphasize transferable skills and narrative. |
| Career returner (gap) | Score normally but add a "Gap Strategy" section to Block C with framing advice. |
| International/visa | Add a Location modifier: if role requires authorization the user doesn't have, flag prominently but don't auto-disqualify (sponsorship is possible). |
