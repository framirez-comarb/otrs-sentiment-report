"""
OTRS Web Scraper
================
Handles authentication, search, and ticket content extraction from OTRS 3.3.x
via web scraping (no API access required).

Key points:
- Plain-text emails: inline in <div class="ArticleBody">
- HTML emails: in <iframe> → fetch via AgentTicketAttachment;Subaction=HTMLView
- Some articles only have image/PDF attachments → use ticket title as fallback
- Binary detection on raw bytes to avoid returning garbage
"""

import re
import time
import logging
from datetime import datetime
from urllib.parse import urljoin
from html import unescape

import requests
from bs4 import BeautifulSoup

from src.analyzer import is_staff_response

log = logging.getLogger(__name__)

REQUEST_DELAY = 0.15

KNOWN_QUEUE_IDS = {
    "SIFERE": "12", "SIFERE WEB": "35", "Módulo Consultas": "37",
    "Módulo DDJJ": "36", "SIRCAR": "9", "SIRCREB": "7", "SIRCUPA": "82",
    "SIRPEI": "18", "SIRTAC": "47", "SICOM": "15", "PADRON WEB": "27",
    "ENCUESTAS": "48", "SUPERVISION": "103", "SIRCIP": "144",
    "PORTAL FEDERAL TRIBUTARIO": "143",
}

# ── Binary content detection ──

# Content-Type values that indicate binary (non-text) content
BINARY_CONTENT_TYPES = [
    "image/", "application/pdf", "application/octet-stream",
    "application/zip", "application/vnd.", "application/x-",
    "audio/", "video/",
]

# Magic bytes for common binary formats
BINARY_MAGIC = [
    b"%PDF",          # PDF
    b"\x89PNG",       # PNG
    b"\xff\xd8\xff",  # JPEG
    b"GIF8",          # GIF
    b"PK\x03\x04",   # ZIP/DOCX/XLSX/PPTX
    b"PK\x05\x06",   # ZIP empty
    b"RIFF",          # WAV/AVI
    b"\x00\x00\x01\x00",  # ICO
    b"\xd0\xcf\x11\xe0",  # MS Office old format
    b"\x7fELF",       # ELF binary
]


def _is_binary_response(resp):
    """Check if an HTTP response contains binary data (not useful text)."""
    # Check Content-Type header
    ct = resp.headers.get("Content-Type", "").lower()
    for bt in BINARY_CONTENT_TYPES:
        if bt in ct:
            return True

    # Check Content-Disposition (attachment with binary filename)
    cd = resp.headers.get("Content-Disposition", "").lower()
    if cd:
        for ext in [".pdf", ".png", ".jpg", ".jpeg", ".gif", ".docx", ".xlsx", ".zip", ".doc"]:
            if ext in cd:
                return True

    # Check raw bytes (first 20 bytes)
    raw = resp.content[:20]
    for magic in BINARY_MAGIC:
        if raw.startswith(magic):
            return True

    # Check for high ratio of non-ASCII bytes (binary garbage)
    sample = resp.content[:500]
    if len(sample) > 50:
        non_text = sum(1 for b in sample if b > 127 or (b < 32 and b not in (9, 10, 13)))
        if non_text / len(sample) > 0.10:
            return True

    return False


def _is_valid_text(text):
    """Check if extracted text is actual useful email body."""
    if not text or len(text.strip()) < 10:
        return False
    # Check for binary garbage that slipped through as string
    if text.startswith("%PDF"):
        return False
    # Check for just embedded image references
    clean = re.sub(r"\[cid:[^\]]+\]", "", text)
    clean = re.sub(r"\[image:[^\]]*\]", "", clean).strip()
    if len(clean) < 15:
        return False
    # Check for high non-printable characters
    if len(text) > 50:
        non_print = sum(1 for c in text[:300] if ord(c) > 127 or (ord(c) < 32 and c not in '\n\r\t'))
        if non_print / min(len(text), 300) > 0.10:
            return False
    return True


class OTRSScraper:
    def __init__(self, base_url, username, password):
        self.base_url = base_url
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.verify = True
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
        })
        self._challenge_token = None

    # ── Authentication ──

    def login(self):
        log.info(f"Logging into OTRS at {self.base_url}...")
        self.session.auth = (self.username, self.password)
        try:
            resp = self.session.get(self.base_url, timeout=30, allow_redirects=True)
            resp.raise_for_status()
        except requests.exceptions.HTTPError:
            if resp.status_code == 401:
                log.error("HTTP Basic Auth failed.")
                return False
            raise

        if "AgentDashboard" in resp.url or "AgentDashboard" in resp.text:
            log.info("Authenticated → Dashboard reached.")
            self._extract_challenge_token(resp.text)
            return True
        if "Action=Login" in resp.text or 'id="Login"' in resp.text:
            return self._form_login(resp)
        return False

    def _form_login(self, initial_resp):
        soup = BeautifulSoup(initial_resp.text, "html.parser")
        data = {"Action": "Login", "RequestedURL": "", "Lang": "es",
                "TimeOffset": "180", "User": self.username, "Password": self.password}
        form = soup.find("form", {"id": "Login"}) or soup.find("form")
        if form:
            for h in form.find_all("input", {"type": "hidden"}):
                n = h.get("name")
                if n and n not in data:
                    data[n] = h.get("value", "")
        resp = self.session.post(self.base_url, data=data, timeout=30, allow_redirects=True)
        if "AgentDashboard" in resp.url or "AgentDashboard" in resp.text:
            self._extract_challenge_token(resp.text)
            return True
        return False

    def _extract_challenge_token(self, html):
        m = re.search(r'ChallengeToken["\s:]+["\']([^"\']+)', html)
        if not m:
            m = re.search(r'name="ChallengeToken"\s+value="([^"]+)"', html)
        if m:
            self._challenge_token = m.group(1)
            log.info(f"ChallengeToken: {self._challenge_token[:8]}...")

    # ── HTTP helpers ──

    def _get(self, url):
        time.sleep(REQUEST_DELAY)
        resp = self.session.get(url, timeout=60, allow_redirects=True)
        resp.raise_for_status()
        return resp

    def _post(self, url, data):
        time.sleep(REQUEST_DELAY)
        resp = self.session.post(url, data=data, timeout=60, allow_redirects=True)
        resp.raise_for_status()
        return resp

    def _get_text_or_none(self, url):
        """GET a URL, return response only if it contains text (not binary)."""
        resp = self._get(url)
        if _is_binary_response(resp):
            log.debug(f"    Binary response from {url.split('?')[1][:60]}")
            return None
        return resp

    # ── Ticket Search ──

    def search_tickets(self, fulltext, queues, date_from, date_to):
        selected_queue_ids = []
        for q in queues:
            q = q.strip()
            if q in KNOWN_QUEUE_IDS:
                selected_queue_ids.append(KNOWN_QUEUE_IDS[q])
                log.info(f"  Queue '{q}' → ID {KNOWN_QUEUE_IDS[q]}")
            else:
                for name, qid in KNOWN_QUEUE_IDS.items():
                    if q.lower() in name.lower() or name.lower() in q.lower():
                        selected_queue_ids.append(qid)
                        log.info(f"  Queue '{q}' ~ '{name}' → ID {qid}")
                        break
                else:
                    log.warning(f"  Queue '{q}' not found.")

        df = datetime.strptime(date_from, "%Y-%m-%d")
        dt = datetime.strptime(date_to, "%Y-%m-%d")

        # Build ShownAttributes based on whether fulltext is used
        shown_attrs = "LabelQueueIDs,LabelTicketCreateTimeSlot"
        if fulltext:
            shown_attrs = "LabelFulltext," + shown_attrs

        search_data = [
            ("Action", "AgentTicketSearch"), ("Subaction", "Search"),
            ("EmptySearch", ""),
            ("ShownAttributes", shown_attrs),
            ("TimeSearchType", "TimeSlot"),
            ("TicketCreateTimeStartDay", str(df.day)),
            ("TicketCreateTimeStartMonth", str(df.month)),
            ("TicketCreateTimeStartYear", str(df.year)),
            ("TicketCreateTimeStopDay", str(dt.day)),
            ("TicketCreateTimeStopMonth", str(dt.month)),
            ("TicketCreateTimeStopYear", str(dt.year)),
            ("ResultForm", "Normal"),
        ]
        if fulltext:
            search_data.append(("Fulltext", fulltext))
        for qid in selected_queue_ids:
            search_data.append(("QueueIDs", qid))
        if self._challenge_token:
            search_data.append(("ChallengeToken", self._challenge_token))

        log.info(f"Searching: fulltext='{fulltext or '(none)'}', queues={selected_queue_ids}, "
                 f"dates={date_from}→{date_to}")

        resp = self._post(self.base_url, data=search_data)
        tickets = self._parse_search_results(resp)
        log.info(f"Page 1: {len(tickets)} tickets")

        seen_ticket_ids = {t["ticket_id"] for t in tickets}
        visited_hits = {1}  # StartHit=1 is the first page
        page = 1

        while True:
            soup = BeautifulSoup(resp.text, "html.parser")
            next_url, next_hit = self._find_next_page(soup, visited_hits)
            if not next_url:
                break
            visited_hits.add(next_hit)
            page += 1
            resp = self._get(next_url)
            more = self._parse_search_results(resp)
            if not more:
                break
            # Deduplicate: only add tickets we haven't seen
            new_tickets = [t for t in more if t["ticket_id"] not in seen_ticket_ids]
            if not new_tickets:
                log.info(f"Page {page}: all duplicates, stopping pagination")
                break
            seen_ticket_ids.update(t["ticket_id"] for t in new_tickets)
            tickets.extend(new_tickets)
            log.info(f"Page {page}: +{len(new_tickets)} (total: {len(tickets)})")

        log.info(f"Total tickets: {len(tickets)}")
        return tickets

    def _find_next_page(self, soup, visited_hits):
        """Find the next unvisited pagination link. Returns (url, start_hit) or (None, None)."""
        # Only match actual pagination links (id="AgentTicketSearchPageN")
        links = soup.find_all("a", id=re.compile(r"AgentTicketSearchPage\d+"))
        if not links:
            return None, None
        # Sort by StartHit ascending and pick the first one we haven't visited
        sorted_links = sorted(links, key=lambda l: int(re.search(r"StartHit=(\d+)", l["href"]).group(1)))
        for link in sorted_links:
            hit = int(re.search(r"StartHit=(\d+)", link["href"]).group(1))
            if hit not in visited_hits:
                href = link["href"]
                url = href if href.startswith("http") else urljoin(self.base_url, href)
                return url, hit
        return None, None

    def _parse_search_results(self, resp):
        tickets = []
        soup = BeautifulSoup(resp.text, "html.parser")
        for item in soup.find_all("li", id=re.compile(r"TicketID_\d+")):
            tid = re.search(r"TicketID_(\d+)", item["id"]).group(1)
            link = item.find("a", class_="MasterActionLink")
            if not link:
                continue
            href = link.get("href", "")
            text = link.text.strip()
            tn, title = "", text
            m = re.match(r"Ticket#:\s*(\d+)\s*[–—\-]\s*(.*)", text)
            if m:
                tn, title = m.group(1), m.group(2).strip()

            queue, created, state = "", "", ""
            ql = item.find("label", string=re.compile(r"Cola"))
            if ql:
                qd = ql.find_next_sibling("div")
                if qd:
                    queue = qd.get("title", "") or qd.text.strip()
            cl = item.find("label", string=re.compile(r"Creado"))
            if cl and cl.next_sibling:
                created = str(cl.next_sibling).strip()
            sl = item.find("label", string=re.compile(r"Estado"))
            if sl:
                sd = sl.find_next_sibling("div")
                if sd:
                    state = (sd.get("title", "") or sd.text.strip()).lower()

            # Skip merged/closed tickets — they have no useful content
            if state in ("fusionado", "merged"):
                continue

            # Extract article body and sender from preview section
            article_body, article_from = self._extract_preview_content(item)

            tickets.append({
                "ticket_id": tid, "ticket_number": tn, "title": title,
                "queue": queue, "created": created,
                "url": urljoin(self.base_url, href) if href else "",
                "first_article_body": article_body,
                "first_article_from": article_from,
            })
        return tickets

    def _extract_preview_content(self, item):
        """Extract article body text and sender from the search result preview."""
        body = ""
        article_from = ""

        preview = item.find("div", class_="Preview")
        if not preview:
            return body, article_from

        # Extract sender from the Headline span (e.g. "SIFERE WEB –")
        headline = preview.find("span", class_="Headline")
        if headline:
            headline_text = headline.get_text(separator=" ", strip=True)
            # The sender is the part before the – separator
            m = re.match(r"^(.+?)\s*[–—\-]\s*", headline_text)
            if m:
                article_from = m.group(1).strip()

        # Extract body: get all text content after the h3 header
        li = preview.find("li")
        if li:
            h3 = li.find("h3")
            if h3:
                body_parts = []
                for sibling in h3.find_next_siblings():
                    text = sibling.get_text(separator=" ", strip=True)
                    if text:
                        body_parts.append(text)
                body = " ".join(body_parts)

        # Clean up: remove "Contestar: - Contestar - RESPONDER" prefix
        body = re.sub(r"^Contestar:\s*-\s*Contestar\s*-\s*RESPONDER\s*", "", body).strip()

        return body, article_from

    # ══════════════════════════════════════════════════════════════
    #  Article Extraction
    # ══════════════════════════════════════════════════════════════

    def fetch_first_articles(self, tickets):
        """Process tickets using preview content from search results.
        Only fetches individual tickets when preview body is missing or too short.
        """
        results = []
        total = len(tickets)
        fetched_count = 0

        for i, ticket in enumerate(tickets, 1):
            tn = ticket.get("ticket_number") or ticket["ticket_id"]
            body = ticket.get("first_article_body", "")

            # If preview body is missing/short, fetch the ticket individually
            if not _is_valid_text(body):
                log.info(f"  [{i}/{total}] Ticket {tn}: no preview, fetching...")
                fetched_count += 1
                try:
                    content = self._fetch_ticket_first_article(
                        ticket["ticket_id"], ticket.get("title", ""))
                    body = content.get("body", "")
                    ticket["first_article_body"] = body
                    ticket["first_article_from"] = (
                        content.get("from", "") or ticket.get("first_article_from", ""))
                    ticket["first_article_subject"] = content.get("subject", "")
                    ticket["first_article_date"] = content.get("date", "")
                except Exception as e:
                    log.error(f"    Error: {e}")
                    body = ""

            # Apply staff detection on the body we have
            if _is_valid_text(body) and is_staff_response(body):
                # Body looks like staff — mark it but still use it (we only have
                # one article from the preview; fetching all articles for 1500+
                # tickets would be too slow)
                ticket["user_message_body"] = body
                ticket["is_user_message"] = False
                ticket["staff_filtered"] = False
            else:
                ticket["user_message_body"] = body
                ticket["is_user_message"] = True
                ticket["staff_filtered"] = False

            if body:
                preview_text = body[:80].replace("\n", " ")
                staff_flag = " [staff]" if not ticket["is_user_message"] else ""
                log.info(f"  [{i}/{total}] {tn}{staff_flag}: {preview_text}...")
            else:
                log.warning(f"  [{i}/{total}] {tn}: no text content")

            results.append(ticket)

        log.info(f"Processed {total} tickets ({fetched_count} required individual fetch)")
        return results

    def _fetch_ticket_first_article(self, ticket_id, ticket_title=""):
        """
        Fetch articles from the ticket and find the first user (non-staff) message.
        Iterates through all articles, using is_staff_response() to filter.
        """
        result = {"body": "", "from": "", "subject": "", "date": "",
                  "user_body": "", "is_user_message": False, "staff_filtered": False}

        # Step 1: Load ticket zoom → find all ArticleIDs
        url = f"{self.base_url}?Action=AgentTicketZoom;TicketID={ticket_id}"
        resp = self._get(url)
        soup = BeautifulSoup(resp.text, "html.parser")

        article_ids = self._find_all_article_ids(soup)
        if not article_ids:
            return result

        # Step 2: Extract text from each article, find first non-staff message
        articles_extracted = []
        for article_id in article_ids:
            body, meta = self._extract_article_content(ticket_id, article_id)
            if _is_valid_text(body):
                articles_extracted.append({"body": body, "meta": meta, "article_id": article_id})

        if not articles_extracted:
            # No text articles found — try ZoomExpand and title fallback
            body = self._try_zoom_expand(ticket_id, article_ids[0])
            if _is_valid_text(body):
                meta = {"from": "", "subject": "", "date": ""}
                articles_extracted.append({"body": body, "meta": meta, "article_id": article_ids[0]})

        if not articles_extracted:
            # Fallback to ticket title
            if ticket_title and len(ticket_title) > 10:
                clean_title = re.sub(r"^SUMA BOT\s*-\s*SIFERE\s*-\s*\d+\s*-\s*", "", ticket_title).strip()
                if clean_title and len(clean_title) > 10:
                    log.info(f"    Using ticket title as fallback: {clean_title[:60]}...")
                    return {"body": clean_title, "from": "", "subject": "", "date": "",
                            "user_body": clean_title, "is_user_message": True, "staff_filtered": False}
            log.warning(f"    Ticket {ticket_id}: only binary content, no text extractable")
            return result

        # First article is always kept as first_article_body (backward compat)
        first = articles_extracted[0]
        result.update({
            "body": first["body"],
            "from": first["meta"].get("from", ""),
            "subject": first["meta"].get("subject", ""),
            "date": first["meta"].get("date", ""),
        })

        # Find first non-staff article
        staff_filtered = False
        for art in articles_extracted:
            if not is_staff_response(art["body"]):
                result["user_body"] = art["body"]
                result["is_user_message"] = True
                if art["article_id"] != articles_extracted[0]["article_id"]:
                    staff_filtered = True
                result["staff_filtered"] = staff_filtered
                return result
            staff_filtered = True

        # All articles are staff responses — use first as fallback
        log.info(f"    All {len(articles_extracted)} articles detected as staff, using first as fallback")
        result["user_body"] = first["body"]
        result["is_user_message"] = False
        result["staff_filtered"] = True
        return result

    def _extract_article_content(self, ticket_id, article_id):
        """Extract text body and meta from a single article. Returns (body, meta)."""
        url = f"{self.base_url}?Action=AgentTicketZoom;TicketID={ticket_id};ArticleID={article_id}"
        resp = self._get(url)
        soup = BeautifulSoup(resp.text, "html.parser")
        meta = self._extract_article_meta(soup)

        # Try inline ArticleBody (plain text emails)
        body = self._extract_inline_body(soup)
        if _is_valid_text(body):
            return body, meta

        # Check if there's an iframe (HTML emails)
        has_iframe = bool(
            soup.find("iframe", id=f"Iframe{article_id}") or
            (soup.find("div", class_="ArticleMailContent") or BeautifulSoup("", "html.parser")).find("iframe")
        )

        if has_iframe:
            for file_id in [1, 2, 3]:
                body = self._fetch_html_view(ticket_id, article_id, file_id)
                if _is_valid_text(body):
                    return body, meta

        # Try direct attachment downloads
        for file_id in [1, 2, 3]:
            body = self._fetch_attachment_text(ticket_id, article_id, file_id)
            if _is_valid_text(body):
                return body, meta

        # Try AgentTicketPlain (raw email source)
        body = self._fetch_plain_article(ticket_id, article_id)
        if _is_valid_text(body):
            return body, meta

        return "", meta

    def _fetch_html_view(self, ticket_id, article_id, file_id):
        """Fetch HTML email body via OTRS HTMLView endpoint."""
        url = (f"{self.base_url}?Action=AgentTicketAttachment;"
               f"Subaction=HTMLView;TicketID={ticket_id};"
               f"ArticleID={article_id};FileID={file_id}")
        try:
            resp = self._get_text_or_none(url)
            if resp is None:
                return ""
            if len(resp.text) > 50:
                soup = BeautifulSoup(resp.text, "html.parser")
                return self._clean_html_to_text(soup.find("body") or soup)
        except Exception:
            pass
        return ""

    def _fetch_attachment_text(self, ticket_id, article_id, file_id):
        """Download attachment and return text content if it's text."""
        url = (f"{self.base_url}?Action=AgentTicketAttachment;"
               f"TicketID={ticket_id};ArticleID={article_id};FileID={file_id}")
        try:
            resp = self._get_text_or_none(url)
            if resp is None:
                return ""
            ct = resp.headers.get("Content-Type", "").lower()
            if "text/html" in ct:
                soup = BeautifulSoup(resp.text, "html.parser")
                return self._clean_html_to_text(soup.find("body") or soup)
            elif "text/plain" in ct:
                return resp.text.strip()
        except Exception:
            pass
        return ""

    def _fetch_plain_article(self, ticket_id, article_id):
        """Fetch raw email via AgentTicketPlain."""
        url = (f"{self.base_url}?Action=AgentTicketPlain;"
               f"TicketID={ticket_id};ArticleID={article_id}")
        try:
            resp = self._get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            pre = soup.find("pre")
            if pre:
                raw = pre.text.strip()
                if len(raw) > 50:
                    return self._extract_body_from_raw_email(raw)
        except Exception:
            pass
        return ""

    def _try_zoom_expand(self, ticket_id, target_article_id):
        """Load ticket with all articles expanded, find first text body."""
        url = f"{self.base_url}?Action=AgentTicketZoom;TicketID={ticket_id};ZoomExpand=1"
        try:
            resp = self._get(url)
            soup = BeautifulSoup(resp.text, "html.parser")

            # Check inline bodies
            for div in soup.find_all("div", class_="ArticleBody"):
                text = self._clean_html_to_text(div)
                if _is_valid_text(text):
                    return text

            # Check iframes — try HTMLView for the target article
            for iframe in soup.find_all("iframe", id=re.compile(r"Iframe\d+")):
                m = re.search(r"Iframe(\d+)", iframe.get("id", ""))
                if m:
                    aid = m.group(1)
                    for fid in [1, 2]:
                        body = self._fetch_html_view(ticket_id, aid, fid)
                        if _is_valid_text(body):
                            return body
        except Exception:
            pass
        return ""

    # ══════════════════════════════════════════════════════════════
    #  Staff Article Extraction (for incognito analysis layer)
    # ══════════════════════════════════════════════════════════════

    def fetch_staff_articles(self, tickets):
        """For each ticket, fetch the ZoomExpand page once and extract:
        - agent_responses: concatenated HTML-body text of all agent-* articles
        - closed_at: ISO timestamp if state contains "cerrado", else None
        - state_detail: ticket state string
        """
        total = len(tickets)
        log.info(f"Fetching staff articles + close dates for {total} tickets...")
        fast_path = 0
        agent_path = 0
        with_match = 0
        for i, ticket in enumerate(tickets, 1):
            tid = ticket["ticket_id"]
            tn = ticket.get("ticket_number") or tid
            try:
                agent_text, closed_at, state, agent_count = self._fetch_staff_for_ticket(tid)
                ticket["agent_responses"] = agent_text
                ticket["closed_at"] = closed_at
                ticket["state_detail"] = state
                if agent_count == 0:
                    fast_path += 1
                else:
                    agent_path += 1
                    if agent_text:
                        with_match += 1
                # Log less verbose for speed
                if i % 50 == 0 or agent_text:
                    log.info(
                        f"  [{i}/{total}] {tn}: {len(agent_text)}ch staff "
                        f"(rows={agent_count}), state={state or '?'}, closed={closed_at or 'open'}"
                    )
            except Exception as e:
                log.warning(f"  [{i}/{total}] {tn}: staff fetch failed: {e}")
                ticket["agent_responses"] = ""
                ticket["closed_at"] = None
                ticket["state_detail"] = None
        log.info(f"Staff pass done: fast_path={fast_path}, agent_path={agent_path}, with_text={with_match}")
        return tickets

    def _fetch_staff_for_ticket(self, ticket_id):
        """Load ZoomExpand=1 and extract (agent_text, closed_at, state, agent_row_count).

        Strategy:
        1. Parse all <tr id="RowN">. Agent articles have class starting with 'agent-'.
        2. For each agent row, probe HTMLView FileID=1..3 until one returns text/html with real content.
        3. Close date is inferred: if state contains 'cerrado', use the MAX row Created time.
        """
        url = f"{self.base_url}?Action=AgentTicketZoom;TicketID={ticket_id};ZoomExpand=1"
        resp = self._get(url)
        soup = BeautifulSoup(resp.text, "html.parser")

        state = self._extract_ticket_state(soup)

        rows = self._parse_article_rows(soup)
        agent_rows = [r for r in rows if any(c.startswith("agent-") for c in r["classes"])]

        # Close date: MAX of all row Created timestamps if state says "cerrado"
        closed_at = None
        if state and "cerrado" in state.lower() and rows:
            iso_dates = [r["iso_created"] for r in rows if r["iso_created"]]
            if iso_dates:
                closed_at = max(iso_dates)

        # Fast path: no agent articles, return early
        if not agent_rows:
            return "", closed_at, state, 0

        # Fetch body for each agent article
        staff_texts = []
        for r in agent_rows:
            body = self._fetch_article_html_body(ticket_id, r["aid"])
            if body and _is_valid_text(body) and len(body) > 30:
                staff_texts.append(body)

        return "\n\n---\n\n".join(staff_texts), closed_at, state, len(agent_rows)

    def _parse_article_rows(self, soup):
        """Parse <tr id="RowN"> article rows. Returns list of
        {aid, classes, iso_created, from_text}.
        """
        rows = []
        for row in soup.find_all("tr", id=re.compile(r"^Row\d+$")):
            classes = row.get("class", []) or []
            aid_input = row.find("input", class_="ArticleID")
            aid = aid_input.get("value") if aid_input else None
            if not aid:
                continue
            created_td = row.find("td", class_="Created")
            iso_created = ""
            if created_td:
                sort_input = created_td.find("input", class_="SortData")
                if sort_input:
                    iso_created = sort_input.get("value", "")
            from_td = row.find("td", class_="From")
            from_text = ""
            if from_td:
                div = from_td.find("div")
                if div:
                    from_text = div.get("title", "") or div.get_text(strip=True)
            rows.append({
                "aid": aid,
                "classes": classes,
                "iso_created": iso_created,
                "from_text": from_text,
            })
        return rows

    def _fetch_article_html_body(self, ticket_id, article_id):
        """Probe FileIDs 1-3 on HTMLView, return first real HTML body as text."""
        for fid in [1, 2, 3]:
            url = (f"{self.base_url}?Action=AgentTicketAttachment;"
                   f"Subaction=HTMLView;TicketID={ticket_id};"
                   f"ArticleID={article_id};FileID={fid}")
            try:
                resp = self._get_text_or_none(url)
            except requests.exceptions.HTTPError:
                # 500 means no more attachments — stop probing
                break
            except Exception:
                continue
            if resp is None:
                continue
            ct = resp.headers.get("Content-Type", "").lower()
            if "text/html" not in ct:
                continue
            if len(resp.text) < 400:  # tiny responses are OTRS shell, not email body
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            body = soup.find("body") or soup
            text = self._clean_html_to_text(body)
            if _is_valid_text(text) and len(text) > 30:
                return text
        return ""

    def _extract_ticket_state(self, soup):
        """Extract state from the ticket info sidebar.
        OTRS 3.3.x renders it as <label>Estado:</label><p class="Value" title="...">value</p>
        """
        for label in soup.find_all("label"):
            label_text = label.get_text(strip=True).lower().rstrip(":")
            if label_text not in ("estado", "state"):
                continue
            val = label.find_next_sibling(["p", "div", "span"])
            if not val:
                continue
            val_text = (val.get("title", "") or val.get_text(strip=True)).strip()
            if val_text and val_text != "-":
                return val_text
        return None

    # ── Helpers ──

    def _find_first_article_id(self, soup):
        row1 = soup.find("tr", id="Row1")
        if row1:
            aid = row1.find("input", class_="ArticleID")
            if aid and aid.get("value"):
                return aid["value"]
        link1 = soup.find("input", {"name": "Link1", "class": "ArticleInfo"})
        if link1:
            m = re.search(r"ArticleID=(\d+)", link1.get("value", ""))
            if m:
                return m.group(1)
        aid = soup.find("input", class_="ArticleID")
        return aid["value"] if aid and aid.get("value") else None

    def _find_all_article_ids(self, soup):
        """Find all article IDs from the ticket zoom page."""
        article_ids = []
        # Method 1: Look for Row1, Row2, etc.
        for row in soup.find_all("tr", id=re.compile(r"Row\d+")):
            aid = row.find("input", class_="ArticleID")
            if aid and aid.get("value") and aid["value"] not in article_ids:
                article_ids.append(aid["value"])
        # Method 2: Look for ArticleInfo inputs
        if not article_ids:
            for inp in soup.find_all("input", class_="ArticleInfo"):
                m = re.search(r"ArticleID=(\d+)", inp.get("value", ""))
                if m and m.group(1) not in article_ids:
                    article_ids.append(m.group(1))
        # Method 3: Fallback to any ArticleID input
        if not article_ids:
            for aid in soup.find_all("input", class_="ArticleID"):
                if aid.get("value") and aid["value"] not in article_ids:
                    article_ids.append(aid["value"])
        return article_ids

    def _extract_inline_body(self, soup):
        div = soup.find("div", class_="ArticleBody")
        if div:
            return self._clean_html_to_text(div)
        return ""

    def _extract_article_meta(self, soup):
        meta = {"from": "", "subject": "", "date": ""}
        header = soup.find("div", class_="ArticleMailHeader")
        if header:
            for label_text, key in [("De:", "from"), ("Asunto:", "subject")]:
                label = header.find("label", string=re.compile(label_text))
                if label:
                    val = label.find_next_sibling("p", class_="Value")
                    if val:
                        meta[key] = val.get("title", "") or val.text.strip()
        headers = soup.find_all("div", class_="LightRow Header")
        if headers:
            dd = headers[0].find("div", class_="AdditionalInformation")
            if dd:
                m = re.search(r"Creado:\s*(.+?)(?:\s*$|\n)", dd.text.strip())
                if m:
                    meta["date"] = m.group(1).strip()
        return meta

    def _extract_body_from_raw_email(self, raw):
        parts = re.split(r"\n\s*\n", raw, maxsplit=1)
        if len(parts) < 2:
            return raw.strip()
        body = parts[1].strip()
        if "Content-Type:" in body:
            chunks = re.split(r"--[\w=.-]+", body)
            for chunk in chunks:
                if "Content-Type: text/plain" in chunk:
                    sub = re.split(r"\n\s*\n", chunk, maxsplit=1)
                    if len(sub) > 1 and _is_valid_text(sub[1].strip()):
                        return sub[1].strip()
            for chunk in chunks:
                if "Content-Type: text/html" in chunk:
                    sub = re.split(r"\n\s*\n", chunk, maxsplit=1)
                    if len(sub) > 1:
                        soup = BeautifulSoup(sub[1], "html.parser")
                        text = self._clean_html_to_text(soup)
                        if _is_valid_text(text):
                            return text
        if _is_valid_text(body):
            return body
        return ""

    def _clean_html_to_text(self, element):
        if element is None:
            return ""
        for tag in element.find_all(["script", "style", "head"]):
            tag.decompose()
        for cf in element.find_all(["span", "a"], class_="__cf_email__"):
            decoded = self._decode_cf_email(cf.get("data-cfemail", ""))
            if decoded:
                cf.replace_with(decoded)
        for br in element.find_all("br"):
            br.replace_with("\n")
        for p in element.find_all("p"):
            p.insert_after("\n")
        text = element.get_text(separator=" ", strip=False)
        text = unescape(text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        return text.strip()

    @staticmethod
    def _decode_cf_email(encoded):
        if not encoded or len(encoded) < 4:
            return ""
        try:
            b = bytes.fromhex(encoded)
            return "".join(chr(c ^ b[0]) for c in b[1:])
        except (ValueError, IndexError):
            return "[email]"

    def close(self):
        try:
            if self._challenge_token:
                self._get(f"{self.base_url}?Action=Logout;ChallengeToken={self._challenge_token}")
        except Exception:
            pass
        self.session.close()
        log.info("Session closed.")
