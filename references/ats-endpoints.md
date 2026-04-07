# ATS API Endpoints

> **Cowork sandbox note:** These API domains (boards-api.greenhouse.io,
> api.lever.co, api.ashbyhq.com, api.smartrecruiters.com, *.myworkdayjobs.com)
> are blocked by the Cowork network proxy. Do NOT call them directly via WebFetch.
> Use WebSearch with site-scoped queries instead (see skills/scan/SKILL.md).
> This file is kept as a reference for URL pattern detection and slug extraction.

Free, public, no authentication required (but blocked in Cowork sandbox).

## Greenhouse

**List all jobs:**
```
GET https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true
```

Returns JSON array. Each job has:
- `id`, `title`, `location.name`, `content` (HTML description)
- `departments[]`, `offices[]`, `absolute_url`, `updated_at`

**Single job detail:**
```
GET https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{job_id}
```

**Slug:** From the company's careers URL. If URL contains
`boards.greenhouse.io/company` or `company.greenhouse.io`, slug = `company`.

**Example:** `https://boards-api.greenhouse.io/v1/boards/airbnb/jobs?content=true`

## Lever

**List all postings:**
```
GET https://api.lever.co/v0/postings/{slug}
```

Returns JSON array. Each posting has:
- `id`, `text` (title), `categories` (team, location, commitment, department)
- `descriptionPlain`, `hostedUrl`, `applyUrl`
- `workplaceType` (on-site/remote/hybrid), `salaryRange` (currency, min, max)

**Filtering:** `?location=`, `?team=`, `?department=`, `?commitment=`

**EU endpoint:** `https://api.eu.lever.co/v0/postings/{slug}`

**Slug:** From `jobs.lever.co/{slug}`.

**Example:** `https://api.lever.co/v0/postings/netflix`

## Ashby

**List all jobs:**
```
GET https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true
```

Returns JSON with `jobs[]`. Each has:
- `title`, `location`, `departmentName`, `teamName`
- `descriptionHtml`, `descriptionPlain`, `jobUrl`, `applyUrl`
- `isRemote`, `workplaceType`, `employmentType`
- `compensationTierSummary` (with `includeCompensation=true`)

**Slug:** From `jobs.ashbyhq.com/{slug}`.

**Example:** `https://api.ashbyhq.com/posting-api/job-board/ramp?includeCompensation=true`

## SmartRecruiters

**List postings:**
```
GET https://api.smartrecruiters.com/v1/companies/{slug}/postings
```

Returns JSON with `content[]`. Each has:
- `name` (title), `location` (city, region, country)
- `department`, `refNumber`

**Example:** `https://api.smartrecruiters.com/v1/companies/BOSCH/postings`

Note: Auth status is ambiguous in docs. Test before relying on this endpoint.
If it returns 401, fall back to WebSearch.

## Workday (best-effort)

**List jobs (POST, not GET):**
```
POST https://{tenant}.{wd_server}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
Content-Type: application/json

{"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}
```

**Single job:**
```
GET https://{tenant}.{wd_server}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/job/{externalPath}
```

**Complexity:** `tenant` and `wd_server` (wd1, wd3, wd5, etc.) must be
extracted from the company's actual careers page URL. No standard slug pattern.

This endpoint is undocumented and may change. Treat as best-effort.

## Detecting ATS from URL

| URL Pattern | ATS |
|---|---|
| `boards.greenhouse.io/{slug}` | Greenhouse |
| `{company}.greenhouse.io` | Greenhouse |
| `job-boards.greenhouse.io/{slug}` | Greenhouse |
| `jobs.lever.co/{slug}` | Lever |
| `jobs.ashbyhq.com/{slug}` | Ashby |
| `{company}.ashbyhq.com` | Ashby |
| `jobs.smartrecruiters.com/{slug}` | SmartRecruiters |
| `{company}.recruitee.com` | Recruitee (no API, use WebSearch) |
| `apply.workable.com/{slug}` | Workable (widget API available) |
| `*.myworkdayjobs.com` | Workday |

## Rate Limiting

No documented rate limits on GET endpoints. Be respectful:
- One request per company per scan
- If scanning a watchlist, add a brief pause between companies
- Cache results in scan-history.md to avoid redundant calls
