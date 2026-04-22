#!/usr/bin/env python3
"""
OTRS Ticket Intent Classification Report Generator
===================================================
Scrapes OTRS tickets matching search criteria, classifies them by intent
(Consulta/Duda vs Reclamo/Error), generates a word cloud, and publishes
an HTML report to GitHub Pages.
"""

import os
import sys
import json
import logging
from datetime import datetime, date, timedelta

from src.scraper import OTRSScraper
from src.analyzer import IntentClassifier
from src.topic_classifier import TopicClassifier
from src.report_generator import ReportGenerator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def _load_dotenv(path=".env"):
    """Minimal .env loader. Does not overwrite existing env vars."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


def _compute_effective_from(existing_tickets, hard_from_str, overlap_days):
    """Return the effective `date_from` for incremental scraping.

    Rule: we rescrape the last `overlap_days` days relative to the newest
    ticket already in cache (to catch staff replies / state changes on
    tickets created shortly before the previous run). We never go earlier
    than `hard_from_str` (the global DATE_FROM floor).
    """
    hard_from = datetime.strptime(hard_from_str, "%Y-%m-%d")
    if not existing_tickets:
        return hard_from_str

    max_created = None
    for t in existing_tickets:
        parsed = IntentClassifier._parse_date(t.get("created", ""))
        if parsed and (max_created is None or parsed > max_created):
            max_created = parsed

    if not max_created:
        return hard_from_str

    overlap_start = max_created - timedelta(days=overlap_days)
    effective = max(hard_from, overlap_start)
    return effective.strftime("%Y-%m-%d")


def main():
    _load_dotenv()
    # ── Configuration from environment / secrets ──
    otrs_url = os.environ.get("OTRS_URL", "https://webs.comarb.gob.ar/otrs/index.pl")
    otrs_user = os.environ.get("OTRS_USER")
    otrs_pass = os.environ.get("OTRS_PASS")

    if not otrs_user or not otrs_pass:
        log.error("OTRS_USER and OTRS_PASS environment variables are required.")
        sys.exit(1)

    # Search parameters
    search_fulltext = os.environ.get("SEARCH_FULLTEXT", "")
    search_queues = os.environ.get("SEARCH_QUEUES", "SIFERE,Módulo DDJJ")
    search_queues = [q.strip() for q in search_queues.split(",")]
    hard_date_from = os.environ.get("DATE_FROM", "2026-01-01")
    date_to = os.environ.get("DATE_TO", datetime.now().strftime("%Y-%m-%d"))
    overlap_days = int(os.environ.get("OVERLAP_DAYS", "14"))

    # ── Incremental mode: load cached tickets and narrow the scrape window ──
    cache_path = "data/tickets_analyzed.json"
    existing_tickets = []
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                existing_tickets = json.load(f)
        except Exception as e:
            log.warning(f"Could not read cache {cache_path}: {e}. Running full scan.")
            existing_tickets = []

    effective_date_from = _compute_effective_from(existing_tickets, hard_date_from, overlap_days)
    incremental = bool(existing_tickets) and effective_date_from != hard_date_from

    log.info("=" * 60)
    log.info("OTRS Ticket Intent Classification Report")
    log.info("=" * 60)
    log.info(f"Search: {f'{chr(39)}{search_fulltext}{chr(39)}' if search_fulltext else '(todas)'} | Queues: {search_queues}")
    log.info(f"Requested range: {hard_date_from} → {date_to}")
    if incremental:
        log.info(f"Incremental mode: cache has {len(existing_tickets)} tickets; "
                 f"scraping {effective_date_from} → {date_to} (overlap={overlap_days}d)")
    else:
        log.info("Full scan (no usable cache)")

    # ── Step 1: Scrape OTRS ──
    log.info("Step 1: Scraping OTRS tickets...")
    scraper = OTRSScraper(otrs_url, otrs_user, otrs_pass)

    if not scraper.login():
        log.error("Failed to authenticate with OTRS. Check credentials.")
        sys.exit(1)

    scraped_tickets = scraper.search_tickets(
        fulltext=search_fulltext,
        queues=search_queues,
        date_from=effective_date_from,
        date_to=date_to,
    )

    if not scraped_tickets and not existing_tickets:
        log.warning("No tickets found and no cache. Generating empty report.")

    log.info(f"Scraped {len(scraped_tickets)} tickets (in window). "
             f"Fetching articles and filtering staff responses...")

    scraped_tickets = scraper.fetch_first_articles(scraped_tickets)

    staff_filtered_count = sum(1 for t in scraped_tickets if t.get("staff_filtered"))
    log.info(f"Successfully fetched content for {len(scraped_tickets)} tickets "
             f"({staff_filtered_count} with staff responses filtered).")

    # ── Step 1b: Staff responses + close dates (for incognito tab) ──
    log.info("Step 1b: Fetching staff responses and close dates...")
    scraped_tickets = scraper.fetch_staff_articles(scraped_tickets)
    scraper.close()

    # ── Merge scraped with cache ──
    # Tickets in the overlap window get refreshed (new wins by ticket_id).
    merged_by_id = {t["ticket_id"]: t for t in existing_tickets}
    new_count = 0
    updated_count = 0
    for t in scraped_tickets:
        if t["ticket_id"] in merged_by_id:
            updated_count += 1
        else:
            new_count += 1
        merged_by_id[t["ticket_id"]] = t
    tickets_with_content = list(merged_by_id.values())
    log.info(f"Merge: {new_count} new, {updated_count} updated, "
             f"{len(tickets_with_content)} total tickets post-merge")

    # Save raw data for debugging (only the scraped window; full merged goes to analyzed)
    os.makedirs("data", exist_ok=True)
    with open("data/tickets_raw.json", "w", encoding="utf-8") as f:
        json.dump(scraped_tickets, f, ensure_ascii=False, indent=2, default=str)

    # ── Step 2: Intent Classification ──
    # Always run on the full merged set (cheap, CPU-only). Scraped tickets
    # come in without `intent` so they'd be classified anyway; re-running on
    # cached tickets is idempotent and keeps logic simple.
    log.info("Step 2: Classifying tickets by intent...")
    classifier = IntentClassifier()
    analyzed_tickets = classifier.analyze_tickets(tickets_with_content)

    intent_summary = classifier.get_summary(analyzed_tickets)
    log.info(f"Intent summary: {intent_summary}")

    # ── Step 2b: Topic Classification ──
    log.info("Step 2b: Classifying tickets by topic...")
    topic_classifier = TopicClassifier()
    analyzed_tickets = topic_classifier.classify_tickets(analyzed_tickets)
    topic_summary = topic_classifier.get_topic_summary(analyzed_tickets)
    log.info(f"Topic summary: {len(topic_summary['topics'])} topics, "
             f"{topic_summary['total_classified']} classified")

    # ── Step 3: Word Cloud ──
    log.info("Step 3: Generating word cloud...")
    wordcloud_result = classifier.generate_wordcloud(analyzed_tickets)
    wordcloud_b64 = wordcloud_result["image_b64"]
    top_bigrams = wordcloud_result["top_bigrams"]
    top_trigrams = wordcloud_result["top_trigrams"]

    # ── Step 3b: Timeline data ──
    log.info("Step 3b: Computing timeline data...")
    timeline_data = classifier.get_timeline_data(analyzed_tickets)

    # ── Step 3c: Incognito-suggestion layer ──
    log.info("Step 3c: Detecting incognito suggestions in staff responses...")
    classifier.detect_incognito_in_tickets(analyzed_tickets)
    incognito_tickets = [t for t in analyzed_tickets if t.get("has_incognito_suggestion")]
    incognito_kpis = classifier.compute_incognito_kpis(incognito_tickets, len(analyzed_tickets))
    incognito_timeline = classifier.get_incognito_timeline(incognito_tickets)
    incognito_resolution = classifier.compute_resolution_stats(incognito_tickets)
    baseline_resolution = classifier.compute_resolution_stats(analyzed_tickets)
    log.info(f"Incognito KPIs: {incognito_kpis}")
    log.info(f"Resolution (incognito): {incognito_resolution}")
    log.info(f"Resolution (baseline): {baseline_resolution}")

    # ── Step 4: Generate Report ──
    log.info("Step 4: Generating HTML report...")
    generator = ReportGenerator()

    report_html = generator.generate(
        tickets=analyzed_tickets,
        intent_summary=intent_summary,
        wordcloud_b64=wordcloud_b64,
        search_params={
            "fulltext": search_fulltext,
            "queues": search_queues,
            "date_from": hard_date_from,
            "date_to": date_to,
        },
        generated_at=datetime.now(),
        timeline_data=timeline_data,
        top_bigrams=top_bigrams,
        top_trigrams=top_trigrams,
        topic_summary=topic_summary,
        incognito_tickets=incognito_tickets,
        incognito_kpis=incognito_kpis,
        incognito_timeline=incognito_timeline,
        incognito_resolution=incognito_resolution,
        baseline_resolution=baseline_resolution,
    )

    # Write report to docs/ for GitHub Pages
    os.makedirs("docs", exist_ok=True)
    output_path = "docs/index.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_html)

    log.info(f"Report written to {output_path}")

    # Save analyzed data (sorted by ticket_id desc for deterministic git diffs)
    sorted_tickets = sorted(
        analyzed_tickets,
        key=lambda t: int(t.get("ticket_id") or 0),
        reverse=True,
    )
    with open("data/tickets_analyzed.json", "w", encoding="utf-8") as f:
        json.dump(sorted_tickets, f, ensure_ascii=False, indent=2, default=str)

    log.info("Done!")


if __name__ == "__main__":
    main()
