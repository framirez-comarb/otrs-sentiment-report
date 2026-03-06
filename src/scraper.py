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

REQUEST_DELAY = 1.0

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

        search_data = [
            ("Action", "AgentTicketSearch"), ("Subaction", "Search"),
            ("EmptySearch", ""),
            ("ShownAttributes", "LabelFulltext,LabelQueueIDs,LabelTicketCreateTimeSlot"),
            ("Fulltext", fulltext), ("TimeSearchType", "TimeSlot"),
            ("TicketCreateTimeStartDay", str(df.day)),
            ("TicketCreateTimeStartMonth", str(df.month)),
            ("TicketCreateTimeStartYear", str(df.year)),
            ("TicketCreateTimeStopDay", str(dt.day)),
            ("TicketCreateTimeStopMonth", str(dt.month)),
            ("TicketCreateTimeStopYear", str(dt.year)),
            ("ResultForm", "Normal"),
        ]
        for qid in selected_queue_ids:
            search_data.append(("QueueIDs", qid))
        if self._challenge_token:
            search_data.append(("ChallengeToken", self._challenge_token))

        log.info(f"Searching: fulltext='{fulltext}', queues={selected_queue_ids}, "
                 f"dates={date_from}→{date_to}")

        resp = self._post(self.base_url, data=search_data)
        tickets = self._parse_search_results(resp)
        log.info(f"Page 1: {len(tickets)} tickets")

        page = 1
        while True:
            soup = BeautifulSoup(resp.text, "html.parser")
            next_url = self._find_next_page(soup, page)
            if not next_url:
                break
            page += 1
            resp = self._get(next_url)
            more = self._parse_search_results(resp)
            if not more:
                break
            tickets.extend(more)
            log.info(f"Page {page}: +{len(more)} (total: {len(tickets)})")

        log.info(f"Total tickets: {len(tickets)}")
        return tickets

    def _find_next_page(self, soup, current_page):
        links = soup.find_all("a", href=re.compile(r"StartHit="))
        if not links:
            return None
        for link in sorted(links, key=lambda l: int(re.search(r"StartHit=(\d+)", l["href"]).group(1))):
            hit = int(re.search(r"StartHit=(\d+)", link["href"]).group(1))
            if hit > current_page * 35:
                href = link["href"]
                return href if href.startswith("http") else urljoin(self.base_url, href)
        return None

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

            queue, created = "", ""
            ql = item.find("label", string=re.compile(r"Cola"))
            if ql:
                qd = ql.find_next_sibling("div")
                if qd:
                    queue = qd.get("title", "") or qd.text.strip()
            cl = item.find("label", string=re.compile(r"Creado"))
            if cl and cl.next_sibling:
                created = str(cl.next_sibling).strip()

            tickets.append({
                "ticket_id": tid, "ticket_number": tn, "title": title,
                "queue": queue, "created": created,
                "url": urljoin(self.base_url, href) if href else "",
            })
        return tickets

    # ══════════════════════════════════════════════════════════════
    #  Article Extraction
    # ══════════════════════════════════════════════════════════════

    def fetch_first_articles(self, tickets):
        results = []
        total = len(tickets)
        for i, ticket in enumerate(tickets, 1):
            tn = ticket.get("ticket_number") or ticket["ticket_id"]
            log.info(f"  [{i}/{total}] Ticket {tn}...")
            try:
                content = self._fetch_ticket_first_article(ticket["ticket_id"], ticket.get("title", ""))
                ticket.update({
                    "first_article_body": content.get("body", ""),
                    "first_article_from": content.get("from", ""),
                    "first_article_subject": content.get("subject", ""),
                    "first_article_date": content.get("date", ""),
                    "user_message_body": content.get("user_body", "") or content.get("body", ""),
                    "is_user_message": content.get("is_user_message", True),
                    "staff_filtered": content.get("staff_filtered", False),
                })
                body = ticket["user_message_body"]
                if body:
                    preview = body[:80].replace("\n", " ")
                    suffix = " [staff filtered]" if ticket["staff_filtered"] else ""
                    log.info(f"    OK ({len(body)} chars){suffix}: {preview}...")
                else:
                    log.warning(f"    No text content for ticket {ticket['ticket_id']}")
            except Exception as e:
                log.error(f"    Error: {e}")
                ticket["first_article_body"] = ""
                ticket["user_message_body"] = ""
                ticket["is_user_message"] = False
                ticket["staff_filtered"] = False
            results.append(ticket)
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
