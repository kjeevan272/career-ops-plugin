# Industry Archetypes

Each archetype defines a lens for how job postings in that industry should be
evaluated. When evaluating a JD, detect the primary archetype and apply its lens.

## Detection Rules

Scan the JD for these signals to classify:

| Archetype | Detection Keywords |
|---|---|
| Technology/Engineering | software, developer, engineer, DevOps, cloud, API, code, data science, ML, AI, product manager (at tech co), IT, full stack, backend, frontend |
| Finance/Accounting | CPA, CFA, audit, compliance, risk, portfolio, financial analyst, controller, bookkeeping, banking, fintech, treasury, tax |
| Healthcare/Medical | RN, MD, clinical, patient, HIPAA, EMR, nursing, therapy, pharmaceutical, medical device, radiology, surgical |
| Legal/Compliance | JD (Juris Doctor), bar admission, litigation, contract, paralegal, regulatory, counsel, compliance officer, IP, patent |
| Creative/Marketing/Design | designer, copywriter, content, brand, UX, SEO, social media, art director, creative director, campaign, video, photography |
| Operations/Supply Chain | logistics, warehouse, procurement, supply chain, inventory, fleet, distribution, operations manager, fulfillment |
| Sales/Business Development | quota, revenue, pipeline, account executive, BDR, SDR, territory, commission, sales engineer, enterprise sales |
| Education/Training | teacher, professor, curriculum, instructional, K-12, higher ed, training specialist, academic, dean, provost |
| Executive/Leadership | CEO, COO, CFO, VP, SVP, director (senior), P&L, board, strategy, transformation, C-suite, general manager |
| Trades/Skilled Labor | electrician, plumber, HVAC, welder, machinist, carpenter, foreman, journeyman, apprentice, CDL, mechanic |
| Customer Success/Support | customer success, account manager, implementation, onboarding, retention, NPS, CSAT, support engineer, technical support |
| People/HR | recruiter, talent acquisition, HRBP, people operations, benefits, compensation, SHRM, PHR, SPHR, DEI, employee relations |
| Government/Nonprofit | GS-level, clearance, public policy, grant, program officer, civic, federal, state, municipal, NGO, foundation |
| Scientific/R&D | PhD, research, lab, publications, principal investigator, biotech, chemistry, physics, clinical trials, peer review |
| Non-Software Engineering | PE, civil, mechanical, electrical, structural, chemical engineer, CAD, FEA, project engineer, EIT, construction |

## Detection Algorithm

1. Scan the JD for keyword frequency across all archetype keyword lists
2. Weight matches by position: title keywords = 3x, requirements = 2x, description = 1x
3. Select highest-scoring archetype as PRIMARY
4. If second-highest is within 50% of primary's score, note it as SECONDARY
5. Apply primary archetype's evaluation lens with secondary as domain context

Example: "Marketing Director at a hospital" = PRIMARY Creative/Marketing, SECONDARY Healthcare.

## Archetype Evaluation Lenses

### 1. Technology/Engineering
**Focus:** Skills > titles. Specific technologies and tools matter.
**Evaluate:** Language/framework match, system design experience level, open source contributions, architecture scope.
**Watch for:** "Full stack" roles that require specialist depth. Title inflation in startups. Unrealistic years-of-experience requirements for newer technologies.
**Resume tip:** Lead with tech stack. Quantify system scale (users, requests, uptime).

### 2. Finance/Accounting
**Focus:** Credentials + regulatory knowledge. CPA, CFA, Series licenses.
**Evaluate:** Required certifications (hard requirement), regulatory domain (SEC, SOX, Basel), software proficiency (SAP, Oracle, Bloomberg).
**Watch for:** "Big 4 preferred" signals significant bias. Industry specialization matters (banking vs. insurance vs. corporate finance).
**Resume tip:** Certifications near the top. Dollar values managed. Compliance metrics.

### 3. Healthcare/Medical
**Focus:** Licenses are non-negotiable. State-specific licensure matters.
**Evaluate:** Active license/certification in the required state, specific clinical experience, EMR system proficiency, specialty match.
**Watch for:** Scope-of-practice limitations across states. "BLS required" vs. "ACLS preferred." Union vs. non-union facilities.
**Resume tip:** License numbers and states. Patient population served. Clinical volume metrics.

### 4. Legal/Compliance
**Focus:** Bar admission in the required jurisdiction. Practice area match.
**Evaluate:** Bar status, practice area depth, billable hours expectations, firm tier, in-house vs. firm experience.
**Watch for:** Jurisdiction requirements (must be barred in specific state). "Portable" practice areas vs. jurisdiction-specific.
**Resume tip:** Bar admissions, practice areas, deal/case values, industry specializations.

### 5. Creative/Marketing/Design
**Focus:** Portfolio > resume. Demonstrated creative work matters most.
**Evaluate:** Portfolio relevance, tool proficiency (Figma, Adobe, analytics platforms), campaign results, brand recognition.
**Watch for:** "Agency experience preferred" means different pace/culture. In-house wants strategy; agency wants execution speed.
**Resume tip:** Link to portfolio. Lead with campaign results (impressions, conversion, revenue attributed). Name recognizable brands.

### 6. Operations/Supply Chain/Logistics
**Focus:** Scale and complexity of operations managed.
**Evaluate:** Facility/fleet/inventory scale, ERP system experience, certifications (APICS, Six Sigma, Lean), cost reduction track record.
**Watch for:** Industry-specific operations knowledge (cold chain, hazmat, regulated goods). Global vs. domestic experience.
**Resume tip:** Quantify everything: units shipped, cost saved, efficiency gained, headcount managed.

### 7. Sales/Business Development
**Focus:** Numbers. Quota attainment is the primary signal.
**Evaluate:** Quota attainment %, deal size, sales cycle length, territory/vertical match, tech stack (Salesforce, HubSpot).
**Watch for:** Vanity metrics ("managed $10M pipeline" means nothing without close rate). Hunter vs. farmer role mismatch.
**Resume tip:** Quota attainment percentages. Deal sizes. New logos won. Revenue generated. President's Club recognition.

### 8. Education/Training
**Focus:** Credentials + subject matter alignment.
**Evaluate:** Required certification/license (teaching license, state cert), subject area match, grade level experience, educational philosophy alignment.
**Watch for:** State-specific teaching licenses. Private vs. public school requirements. Higher ed wants publications; K-12 wants classroom management.
**Resume tip:** Certification details. Student outcomes. Curriculum developed. Technology integration.

### 9. Executive/Leadership
**Focus:** Scope, P&L ownership, transformation narrative.
**Evaluate:** Revenue/budget scope, team size, board experience, industry reputation, transformation results.
**Watch for:** "Strategic" roles that are actually operational. Title inflation across company sizes. Cultural fit signals.
**Resume tip:** P&L numbers. Transformation before/after. Board roles. Revenue growth attributed. Team scaling.

### 10. Trades/Skilled Labor
**Focus:** Certifications, licenses, hands-on experience, safety record.
**Evaluate:** Required licenses/certifications (journeyman, master, CDL class), union status, equipment proficiency, safety record.
**Watch for:** State/local licensing requirements. Union vs. non-union. Specialty certifications (OSHA 30, EPA 608, welding certs).
**Resume tip:** All certifications with numbers/dates. Equipment list. Safety record. Project scale (square footage, tonnage, voltage).

### 11. Customer Success/Support
**Focus:** Retention metrics + product/domain knowledge.
**Evaluate:** Retention/churn rates managed, book of business size, product complexity, escalation handling, implementation experience.
**Watch for:** "Customer Success" at an SMB startup is very different from enterprise CSM. Technical vs. relationship-driven roles.
**Resume tip:** Retention rates. NPS/CSAT scores. Revenue retained/expanded. Number of accounts managed.

### 12. People/HR
**Focus:** Certifications (SHRM, PHR) + functional specialization.
**Evaluate:** HR function match (recruiting, comp & ben, L&D, HRBP, employee relations), certification status, HRIS proficiency, headcount supported.
**Watch for:** "HR Generalist" vs. specialist roles. Tech company HR is different from manufacturing HR. Labor relations experience matters in unionized industries.
**Resume tip:** Certifications prominently. Headcount supported. Programs launched. Metrics improved (time-to-fill, retention, engagement scores).

### 13. Government/Nonprofit
**Focus:** Clearance level + domain expertise + mission alignment.
**Evaluate:** Security clearance status, GS-level alignment, grant management experience, regulatory knowledge, mission fit.
**Watch for:** Clearance requirements are hard stops (can take 6-18 months to obtain). Government experience strongly preferred for federal roles. Nonprofit values mission alignment over credentials.
**Resume tip:** Clearance level and status. Grant amounts managed. Policy areas. Stakeholder types (elected officials, agency heads).

### 14. Scientific/R&D
**Focus:** Education + publications + domain expertise.
**Evaluate:** Degree level (PhD often required), publication record, specific research techniques, lab/equipment experience, grant funding track record.
**Watch for:** Industry R&D (pharma, biotech) values speed to market; academic R&D values novelty. "PhD preferred" vs. "PhD required" is a real distinction.
**Resume tip:** Publications count and impact. Grants won and amounts. Techniques and equipment. Patents.

### 15. Non-Software Engineering
**Focus:** PE license + project scale + domain certifications.
**Evaluate:** PE/EIT status, specific engineering discipline match, CAD/analysis tools, project scale and complexity, regulatory compliance experience.
**Watch for:** PE license requirements vary by state and discipline. "Engineer" title is legally protected in some jurisdictions. Field vs. office role distinction.
**Resume tip:** PE/EIT status with state. Project values and scale. Standards and codes worked to. Software tools (AutoCAD, MATLAB, SolidWorks).
