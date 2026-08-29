# LinkedIn Lead Generation Agent (5-Phase Pipeline)

An intelligent, cost-optimized LinkedIn lead generation pipeline that discovers leads via Google Search, filters out unqualified prospects locally for free, checks 14-day activity with low-cost actors, and enriches full profile data before persisting to Google Sheets.

---

## What This Agent Does

The agent replaces rate-limited LinkedIn search with a **5-Phase hierarchical funnel**:

1. **Phase 1 — Google Search Discovery (`google_linkedin_scraper.py`)**:
   - Queries Google Search using `apify/google-search-scraper` across 4 search variations per target niche and city.
   - Extracts personal `/in/` LinkedIn URLs while ignoring company, job, and school pages.
2. **Phase 2 — Zero-Cost Pre-Filter (`pre_filter.py`)**:
   - Runs locally on your machine / runner with **$0.00 API cost**.
   - Filters out female first names, profiles targeting women, organizational entities, and low follower counts (<250).
3. **Phase 3 — Posts Activity Check (`posts_checker.py`)**:
   - Runs the cheap `harvestapi/linkedin-profile-posts` actor (**$1.50 / 1,000 profiles**).
   - Keeps only leads who posted on LinkedIn within the last **14 days**.
4. **Phase 4 — Profile Scraper & Full Qualification (`linkedin_profile_scraper.py`, `linkedin_qualifier.py`)**:
   - Runs the expensive `harvestapi/linkedin-profile-scraper` actor (**$4.00 / 1,000 profiles**) **only** on confirmed active leads.
   - Validates follower count (250–31,000), confirms client service offering, and ensures `openToWork == False`.
5. **Phase 5 — Google Sheets Deduplication & Persistence (`sheets_writer_linkedin.py`)**:
   - Automatically skips duplicate URLs already in your `Leads` tab.
   - Appends qualified leads with 12 structured columns and marks the `Control` row `Done`.

---

## Google Sheets Setup

Your Google Sheet needs two tabs:

### 1. `Control` Tab
This drives the agent's work queue dynamically (no hardcoded cities or niches):

| Niche | City | Pages | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| `Executive Coach` | `Houston` | `10` | `Pending` | *(Agent updates this to Done + stats)* |
| `Business Coach` | `Dallas` | `8` | `Pending` | |
| `Leadership Coach` | `Miami` | `8` | `Pending` | |
| `Executive Coach` | `Wyoming` | `3` | `Pending` | |

- **Niche**: Keyword / target industry.
- **City**: City or State name (use state names for smaller states like Wyoming, Alaska, Montana).
- **Pages**: Total Google search pages to divide across query variations (e.g. 10 for mega cities, 8 for large, 5 for medium, 3 for small states).
- **Status**: Set to `Pending` for jobs to run. The agent updates this to `Done` or `Failed`.

### 2. `Leads` Tab
The agent writes verified leads across these columns:
`LinkedIn URL` | `First Name` | `Last Name` | `Headline` | `Follower Count` | `Location City` | `Location State` | `Location Country` | `Current Company` | `Last Post Date` | `Date Added` | `Status`

---

## Setting Up GitHub Actions & Secrets

The agent runs automatically every day at **6:00 PM Pakistan Time (1:00 PM UTC)** via GitHub Actions, and can also be triggered manually anytime.

### Step 1: Add GitHub Repository Secrets
1. Go to your GitHub Repository -> **Settings** -> **Secrets and variables** -> **Actions**.
2. Click **New repository secret** and add the following secrets:

| Secret Name | Description | Value Example |
| :--- | :--- | :--- |
| `APIFY_API_TOKEN` | Your Apify Personal API Token | `apify_api_...` |
| `GOOGLE_SHEETS_CREDENTIALS` | The **entire contents** of your Google Service Account JSON file | `{"type": "service_account", "project_id": "...", ...}` |
| `SPREADSHEET_ID` | The ID from your Google Sheet URL | `your_spreadsheet_id_here` |
| `NOTIFY_EMAIL_ADDRESS` | *(Optional)* Gmail address to send notification emails FROM | `your_email@gmail.com` |
| `NOTIFY_EMAIL_PASSWORD` | *(Optional)* 16-character Gmail App Password | `abcd efgh ijkl mnop` |
| `NOTIFY_EMAIL_TO` | *(Optional)* Email address to receive run reports | `recipient@gmail.com` |

> **Note**: Share your Google Sheet with the `client_email` found in your service account JSON file (with **Editor** permissions).

---

## How to Trigger Manually from GitHub Actions

1. Go to your repository on GitHub.
2. Click on the **Actions** tab.
3. Select **Run LinkedIn Lead Generation Agent** from the left sidebar.
4. Click the **Run workflow** dropdown button on the right.
5. Select branch `main` and click **Run workflow**.

The workflow will start immediately and stream live logs of all 5 pipeline phases.

---

## Local Development & Testing

1. Clone the repository:
   ```bash
   git clone <REPO_URL>
   cd "linkedin new phase agent"
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file (see `.env.example`):
   ```env
   APIFY_API_TOKEN=your_apify_token_here
   SPREADSHEET_ID=your_spreadsheet_id_here
   GOOGLE_SERVICE_ACCOUNT_FILE=credentials.json
   ```

4. Run all unit tests:
   ```bash
   python -m unittest discover -s . -p "test_*.py"
   ```

5. Run the agent locally:
   ```bash
   python run_agent.py
   ```
