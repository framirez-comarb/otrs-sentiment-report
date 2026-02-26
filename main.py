#!/usr/bin/env python3
"""
OTRS Sentiment Analysis Report Generator
=========================================
Scrapes OTRS tickets matching search criteria, performs sentiment analysis
on the first email of each ticket, generates a word cloud, and publishes
an HTML report to GitHub Pages.
"""

import os
import sys
import json
import logging
from datetime import datetime, date

from src.scraper import OTRSScraper
from src.analyzer import SentimentAnalyzer
from src.report_generator import ReportGenerator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def main():
    # ── Configuration from environment / secrets ──
    otrs_url = os.environ.get("OTRS_URL", "https://webs.comarb.gob.ar/otrs/index.pl")
    otrs_user = os.environ.get("OTRS_USER")
    otrs_pass = os.environ.get("OTRS_PASS")

    if not otrs_user or not otrs_pass:
        log.error("OTRS_USER and OTRS_PASS environment variables are required.")
        sys.exit(1)

    # Search parameters
    search_fulltext = os.environ.get("SEARCH_FULLTEXT", "incógnito")
    search_queues = os.environ.get("SEARCH_QUEUES", "SIFERE,Módulo Consultas,Módulo DDJJ")
    search_queues = [q.strip() for q in search_queues.split(",")]
    date_from = os.environ.get("DATE_FROM", "2025-01-01")
    date_to = os.environ.get("DATE_TO", datetime.now().strftime("%Y-%m-%d"))

    log.info("=" * 60)
    log.info("OTRS Sentiment Analysis Report")
    log.info("=" * 60)
    log.info(f"Search: '{search_fulltext}' | Queues: {search_queues}")
    log.info(f"Date range: {date_from} → {date_to}")

    # ── Step 1: Scrape OTRS ──
    log.info("Step 1: Scraping OTRS tickets...")
    scraper = OTRSScraper(otrs_url, otrs_user, otrs_pass)

    if not scraper.login():
        log.error("Failed to authenticate with OTRS. Check credentials.")
        sys.exit(1)

    tickets = scraper.search_tickets(
        fulltext=search_fulltext,
        queues=search_queues,
        date_from=date_from,
        date_to=date_to,
    )

    if not tickets:
        log.warning("No tickets found. Generating empty report.")

    log.info(f"Found {len(tickets)} tickets. Fetching first article of each...")

    tickets_with_content = scraper.fetch_first_articles(tickets)
    scraper.close()

    log.info(f"Successfully fetched content for {len(tickets_with_content)} tickets.")

    # Save raw data for debugging
    os.makedirs("data", exist_ok=True)
    with open("data/tickets_raw.json", "w", encoding="utf-8") as f:
        json.dump(tickets_with_content, f, ensure_ascii=False, indent=2, default=str)

    # ── Step 2: Sentiment Analysis ──
    log.info("Step 2: Running sentiment analysis...")
    analyzer = SentimentAnalyzer()
    analyzed_tickets = analyzer.analyze_tickets(tickets_with_content)

    sentiment_summary = analyzer.get_summary(analyzed_tickets)
    log.info(f"Sentiment summary: {sentiment_summary}")

    # ── Step 3: Word Cloud ──
    log.info("Step 3: Generating word cloud...")
    wordcloud_b64 = analyzer.generate_wordcloud(analyzed_tickets)

    # ── Step 4: Generate Report ──
    log.info("Step 4: Generating HTML report...")
    generator = ReportGenerator()

    report_html = generator.generate(
        tickets=analyzed_tickets,
        sentiment_summary=sentiment_summary,
        wordcloud_b64=wordcloud_b64,
        search_params={
            "fulltext": search_fulltext,
            "queues": search_queues,
            "date_from": date_from,
            "date_to": date_to,
        },
        generated_at=datetime.now(),
    )

    # Write report to docs/ for GitHub Pages
    os.makedirs("docs", exist_ok=True)
    output_path = "docs/index.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_html)

    log.info(f"Report written to {output_path}")

    # Also save analyzed data
    with open("data/tickets_analyzed.json", "w", encoding="utf-8") as f:
        json.dump(analyzed_tickets, f, ensure_ascii=False, indent=2, default=str)

    log.info("Done!")


if __name__ == "__main__":
    main()
