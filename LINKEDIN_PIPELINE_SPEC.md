# LinkedIn Lead Generation Pipeline — System Specification

## Overview
A 5-phase lead generation pipeline that replaces single-actor LinkedIn search with a cost-effective, intelligent discovery and qualification architecture. Leads are discovered via Google Search and processed through a funnel that filters out low-quality or inactive profiles before calling paid/expensive data enrichment actors.

---

## 5-Phase Pipeline Architecture

```
                                  [ Control Tab ]
                             (Niche, City, Pages, Status)
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Phase 1: Google Search Scraper (apify/google-search-scraper)                    │
│ • Runs 3–4 query variations with site: operators                                │
│ • Splits total page count across queries                                        │
│ • Validates clean /in/ profile URLs (rejects company/jobs/pulse/groups)          │
│ • Deduplicates and extracts Google snippet metadata                             │
└────────────────────────────────────────┬────────────────────────────────────────┘
                                         │ Clean URLs + Snippet Data
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Phase 2: Pre-filter (Local / No API Cost)                                       │
│ • Filter 1: Remove female first names from websiteTitle / snippet               │
│ • Filter 2: Remove profiles targeting women / female audiences                  │
│ • Filter 3: Remove organization / institution keywords                          │
│ • Filter 4: Remove low follower count (< 250) if visible in displayedUrl        │
└────────────────────────────────────────┬────────────────────────────────────────┘
                                         │ Filtered URLs
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Phase 3: Posts Scraper / Activity Check ($1.50 / 1k profiles)                   │
│ Actor: harvestapi/linkedin-profile-posts                                        │
│ • maxPosts: 5, postedLimit: month, no reactions/comments                        │
│ • Activity Rule: Must have at least 1 post within the last 14 days              │
│ • Batch size: ≤ 50 URLs with 30s delay between batches                          │
│ • Removes inactive / dormant / private profiles                                 │
└────────────────────────────────────────┬────────────────────────────────────────┘
                                         │ Confirmed Active Profile URLs
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Phase 4: Profile Scraper & Full Qualification ($4.00 / 1k profiles)             │
│ Actor: harvestapi/linkedin-profile-scraper                                      │
│ • Runs ONLY on leads confirmed active in Phase 3                                │
│ • Full Qualification Rules:                                                     │
│   - Gender: Not female (name, headline, pronouns)                               │
│   - Followers: 250 – 31,000 inclusive                                           │
│   - Open to Work: False                                                         │
│   - Service: Personal coaching/consulting/mentoring/advising client service     │
│   - Page Type: Not organization / company / school                              │
│   - Role: Not employee-only with no coaching/service offering                   │
│ • Batch size: ≤ 50 URLs with 30s delay between batches                          │
└────────────────────────────────────────┬────────────────────────────────────────┘
                                         │ Qualified Full Profile Data
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Phase 5: Save to Google Sheets                                                  │
│ • Checks existing LinkedIn URLs in Leads tab to prevent duplicates              │
│ • Writes new leads to Leads tab with 12 metadata columns                        │
│ • Appends full run metrics & drop-offs to Run Log tab                           │
│ • Logs diagnostics & failure reasons to Error Log tab                           │
│ • Updates Control Tab row: Status = Done (or Failed) + Summary Notes            │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Cost Optimization Rationale
- **Posts Scraper**: $1.50 per 1,000 profiles.
- **Profile Scraper**: $4.00 per 1,000 profiles.
- By running the cheap posts activity check (Phase 3) *before* the expensive profile scraper (Phase 4), we only pay for full profile data on leads that are already confirmed active within 14 days.
- This saves approximately 18–20% on Apify credits every month.

---

## Google Sheets Structure

The agent integrates with 4 worksheets within the target Google Spreadsheet:

### 1. `Control` Tab
Drives the dynamic work queue:
| Column | Description | Example |
| :--- | :--- | :--- |
| **Niche** | Target niche / keyword | `Executive Coach` |
| **City** | Target city or state | `Houston` or `Wyoming` |
| **Pages** | Total Google search pages to scrape | `8` |
| **Status** | Processing status | `Pending`, `Done`, `Failed` |
| **Notes** | Summary log or error message | `12 leads added. Credits: ~$0.18` |

### 2. `Leads` Tab
Stores enriched, verified leads with deduplication:
`LinkedIn URL` | `First Name` | `Last Name` | `Headline` | `Follower Count` | `Location City` | `Location State` | `Location Country` | `Current Company` | `Last Post Date` | `Date Added` | `Status`

### 3. `Run Log` Tab
Historical tracking log appended on every single pipeline execution:
`Timestamp (UTC)` | `Niche` | `City` | `Pages` | `Phase 1 Found` | `Phase 2 Passed` | `Phase 3 Active` | `Phase 4 Qualified` | `New Leads Saved` | `Duplicates Skipped` | `Status` | `Notes / Summary` | `Estimated Cost ($)`

### 4. `Error Log` Tab
Detailed error and filter drop-out diagnostics log:
`Timestamp (UTC)` | `Niche` | `City` | `Failed Phase` | `Error Message / Reason` | `Details / Exception`

### Control Tab Processing Rules
1. Agent reads all rows where `Status == "Pending"`.
2. Processes rows sequentially from top to bottom.
3. If no pending rows exist, exits cleanly with `"No pending jobs found"`.
4. If a row succeeds, sets `Status = Done`, writes summary into `Notes`, and logs to `Run Log`.
5. If a row fails, sets `Status = Failed`, writes failure reason into `Notes`, and logs to both `Run Log` and `Error Log`.

---

## Phase Details

### Phase 1: Google Search Scraper
- **Actor**: `apify/google-search-scraper`
- **Query Strategy**: Multi-query (3 to 4 variations per job). Divides total pages across queries.
  - *Q1 (Exact match)*: `site:linkedin.com/in/ "[Niche]" "[City]"`
  - *Q2 (Coaching variant)*: `site:linkedin.com/in/ "[Niche]ing" "[City]"` (e.g. `Executive Coaching`)
  - *Q3 (Broad match)*: `linkedin.com "[Niche]" "[City]" coach`
  - *Q4 (Consultant variant)*: `site:linkedin.com "[Niche]" "[City]" consultant`
- **URL Validation**:
  - Must match: `https://www.linkedin.com/in/[username]`
  - Exclude: `/company/`, `/jobs/`, `/school/`, `/pulse/`, `/feed/`, `/groups/`, or any URL without `/in/`.
- **Output**: List of deduplicated profile URLs + Google snippet data (`title`, `websiteTitle`, `displayedUrl`, `description`, `emphasizedKeywords`).

### Phase 2: Pre-filter (Local / No Cost)
- **Filter 1 (Female Names)**: Check parsed first name against comprehensive female names list. If female, remove. If unsure, keep.
- **Filter 2 (Targeting Women)**: Reject if description/title contains: `"I help women"`, `"helping women"`, `"for women"`, `"women entrepreneurs"`, `"women in business"`, `"female founders"`, `"for moms"`, `"for mothers"`, `"ambitious moms"`, `"working moms"`, `"ladies"`, `"girls"`, `"sisterhood"`, `"she/her"`, `"her/she"`, `"girls in business"`, `"womens coach"`, `"women's coach"`.
- **Filter 3 (Organizations)**: Reject if title/description contains: `"University"`, `"College"`, `"Academy"`, `"School"`, `"Institute"`, `"Hospital"`, `"Clinic"`, `"Church"`, `"Ministry"`, `"Ministries"`, `"Pastor"`, `"Nonprofit"`, `"Non-profit"`, `"Foundation"`, `"Association"`, `"Chamber"`, `"Government"`, `"Department"`, `"Agency"`, `"Inc."`, `"LLC"`, `"Ltd."`, `"Corporation"`, `"Corp."`, `"Media"`, `"Magazine"`, `"News"`, `"Team"`, `"Group"`.
- **Filter 4 (Low Follower Count)**: Parse follower count from `displayedUrl` (e.g. `"3.8K+ followers"`). If visible and `< 250`, remove. If not visible, keep for Phase 4.

### Phase 3: Posts Scraper (Activity Check)
- **Actor**: `harvestapi/linkedin-profile-posts`
- **Settings**: `maxPosts: 5`, `postedLimit: "month"`, `scrapeReactions: false`, `scrapeComments: false`.
- **Rule**: Check `postedAt.date`. Keep only if at least 1 post is within the last 14 days.
- **Batching**: Max 50 URLs per actor call with 30s pause between batches.

### Phase 4: Profile Scraper & Full Qualification
- **Actor**: `harvestapi/linkedin-profile-scraper`
- **Qualification Criteria**:
  - `openToWork == False`
  - `250 <= followerCount <= 31,000`
  - Person offers client service (coaching/consulting/mentoring/speaking/training/advising).
  - Not an organization / company page.
  - Not employee-only without personal service offerings.
  - Gender: Not clearly female.
- **Batching**: Max 50 URLs per actor call with 30s pause between batches.

### Phase 5: Google Sheets Writer
- **Duplicate Check**: Query existing URLs in `Leads` sheet.
- **Columns Written**:
  1. `LinkedIn URL`
  2. `First Name`
  3. `Last Name`
  4. `Headline`
  5. `Follower Count`
  6. `Location City`
  7. `Location State`
  8. `Location Country`
  9. `Current Company`
  10. `Last Post Date` (from Phase 3)
  11. `Date Added` (current date)
  12. `Status` (blank for manual tracking)
- **Control Tab Update**: Sets `Status = Done` and logs summary in `Notes`.

---

## Error Handling & Rate Limiting Rules
- **Batch Size**: Never send more than 50 URLs in a single call for Phase 3 or Phase 4.
- **Batch Delays**: 30-second delay between batch calls.
- **Credits Exhaustion**: Catch `"By launching this job you will exceed your remaining usage"` error, mark current row as `Failed (Credits Out)`, and cleanly stop remaining runs.
- **Phase Failures**:
  - Phase 1 (0 results) -> Mark `Failed` ("Google returned 0 results").
  - Phase 2 (all filtered) -> Mark `Failed` ("All profiles removed in pre-filter").
  - Phase 3 (0 active) -> Mark `Failed` ("No active profiles found").
  - Phase 4 (0 qualified) -> Mark `Failed` ("No qualified profiles after full filter").
  - Phase 5 (all duplicates) -> Mark `Done` ("All leads already exist in sheet").
