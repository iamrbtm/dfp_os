### **Master Prompt: AI Design Trend Scout Implementation**

**Context:** You are an expert full-stack Python/Flask developer tasked with building a massive new feature for "DFPos" (a local 3D printing farm OS and point-of-sale system). This feature is called the **AI Design Trend Scout**. It is an autonomous agent that monitors the 3D printing ecosystem to detect rising product trends, analyze business viability, and generate weekly actionable reports.

**CRITICAL INSTRUCTIONS BEFORE YOU BEGIN:**

1.  **Read `AGENTS.md` and `DESIGN.md`** in the repository root. You must adhere to all architectural patterns, coding standards, and agent protocols defined there.
2.  **Update `TODO.md`:** Throughout this development process, you must maintain and update the `TODO.md` file to reflect current progress, active phase, and completed milestones. Do not proceed to the next phase without updating the tracker.
3.  **Stay in Scope:** This is a large feature. We are breaking it down into phases. Only work on the phase explicitly requested. Do not hallucinate database models or imports that belong in later phases.

### **System Architecture (Strict Adherence Required)**

We are implementing this using **Option A (Monolith + Celery + MariaDB JSON)**.

-   **No Microservices:** Everything lives within the existing Flask application.
-   **No NoSQL DBs:** We are using MariaDB. You will use SQLAlchemy's `JSON` data type (or `sqlalchemy.dialects.mysql.JSON`) to store the scraped, unstructured `raw_metadata`.
-   **Isolation:** The scraping/aggregation logic will live in pure Python modules inside `app/services/ai/trend_scout/`. **Do not import Flask globals** (`current_app`, `request`, etc.) into the service layer.
-   **Execution:** The pipeline runs via a Celery Beat cron job (`app/tasks/trend_scout.py`).

### **Data Sources (The Ecosystem)**

The system will aggregate data from the following sources. You will build modular scraper/API integrations for each:

**Reliable API Sources:**

1.  **MyMiniFactory:** API v2 (Swagger documented, highly stable).
2.  **Etsy:** Search API v3 (OAuth).
3.  **eBay:** Browse API (sold prices).
4.  **Thangs (Shapeways):** Geometric deep-learning search API.
5.  **BoardGameGeek (BGG):** XML API (for tabletop/gaming trends).

**Scraping / Unofficial Sources:** 6. **MakerWorld (Bambu Lab):** Scrape popular/trending pages (Critical source). 7. **Printables (Prusa):** RSS feeds + page scraping (Focus on "Makes" count). 8. **Cults3D:** Scrape trending topics page. 9. **Thingiverse / STLFinder:** Scrape for cross-platform model indexing. 10. **Amazon:** Product Advertising API / Scraping (BSR, price history). 11. **TikTok & Pinterest:** Viral social trends and visual discovery (Pinterest lifestyle trends vs. TikTok spikes). 12. **Graphtreon (Patreon):** Scrape 3D creator leaderboards for macro-trends. 13. **Google Trends:** Unofficial `pytrends` library.

**Reddit (The "Unknown Unknowns" Engine):** 14. Target subreddits via JSON endpoints or PRAW: \* `r/3Dprinting` (General trends) \* `r/functionalprint` (Practical solutions) \* `r/boardgameupgrades` (Niche tabletop demand) \* `r/Gridfinity` (Organization trends) \* `r/PrintedMinis` (Resin/tabletop trends) \* `r/3Dprintmything` (Direct consumer demand/requests) \* `r/BambuLab` (Hardware-specific trends)

### **Development Phases**

#### **Phase 1: Database & Foundation**

1.  Create the SQLAlchemy models in `app/models/trend.py`:
    
    -   `TrendSnapshot`: Columns for `id`, `source` (String), `keyword_or_category` (String), `scraped_at` (DateTime), and **`raw_metadata` (JSON)**. Ensure indexing on `source`, `keyword_or_category`, and `scraped_at`.
    -   `TrendReport`: Columns to store weekly synthesized results (e.g., `id`, `report_date`, `summary`, `top_opportunities` JSON).
2.  Generate and apply the Alembic migrations.
3.  Create the empty directory structure for `app/services/ai/trend_scout/` (sources, analyzer, models).

#### **Phase 2: Source Integrations (The Fetchers)**

1.  In `app/services/ai/trend_scout/sources/`, build the individual data fetchers.
2.  Start with the structured APIs: `myminifactory.py`, `etsy.py`, `bgg.py`.
3.  Build the scrapers utilizing `BeautifulSoup`, sensible rate-limiting (1 req/3s), and random user-agents: `makerworld.py`, `printables.py` (parse RSS and "Makes"), `reddit.py` (looping through the specific subreddits listed above).
4.  **Standardization:** Ensure every source returns a Python dictionary that can be cleanly dumped into the MariaDB `JSON` column.

#### **Phase 3: The Pipeline & Celery Task**

1.  Create the orchestration logic in `app/services/ai/trend_scout/__init__.py` or `pipeline.py` that calls all sources asynchronously/concurrently (using `asyncio` or `concurrent.futures`).
2.  Implement `app/tasks/trend_scout.py`. This Celery task must:
    
    -   Call the pipeline.
    -   Catch and isolate any source failures (graceful degradation).
    -   Write all results as new `TrendSnapshot` rows to the database.
3.  Add the Celery Beat schedule to run every Monday at 6:00 AM with a strict 15-minute timeout.

#### **Phase 4: Analysis & NLP Discovery**

1.  In `app/services/ai/trend_scout/analyzer/trend_detector.py`, write the logic to query MariaDB, extract data from the `JSON` fields, and compute week-over-week velocity, momentum, and cross-source correlation.
2.  In `new_category_discovery.py`, write the NLP clustering script. Extract all noun phrases from scraped titles, embed them using `text-embedding-3-small`, and cluster them using DBSCAN to detect new, emerging categories.
3.  Synthesize this data into a `TrendReport` row using a prompt sent to `gpt-4o-mini`.

#### **Phase 5: Flask Blueprint & Dashboard**

1.  Create `app/blueprints/trend_scout/routes.py` with API endpoints to fetch the latest `TrendReport`.
2.  Build the UI components for the DFPos admin dashboard to visualize the urgent opportunities, growing categories, and declining trends.

**Execution Command for Agent:** Acknowledge these instructions. Confirm you have read `AGENTS.md` and `DESIGN.md`. Then, update `TODO.md` with the 5 phases, mark Phase 1 as "In Progress", and generate the code for **Phase 1: Database & Foundation**. Do not start Phase 2 until instructed.