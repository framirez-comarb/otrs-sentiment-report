"""
OTRS Web Scraper
================
Handles authentication, search, and ticket content extraction from OTRS 3.3.x
via web scraping (no API access required).
"""

import re
import time
import logging
from datetime import datetime
from urllib.parse import urljoin, urlencode, parse_qs, urlparse
from html import unescape

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

# Be polite with the server
REQUEST_DELAY = 1.5  # seconds between requests


class OTRSScraper:
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.verify = True  # Set to False if SSL cert issues
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
        })
        self._session_id = None

    def login(self) -> bool:
        """
        Authenticate with OTRS. Handles two scenarios:
        1. HTTP Basic Auth at the Apache level
        2. OTRS form-based login
        Returns True if successful.
        """
        log.info(f"Logging into OTRS at {self.base_url}...")

        # Attempt 1: HTTP Basic Auth (as shown in the browser dialog)
        self.session.auth = (self.username, self.password)

        try:
            resp = self.session.get(self.base_url, timeout=30, allow_redirects=True)
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            if resp.status_code == 401:
                log.error("HTTP Basic Auth failed. Check credentials.")
                return False
            raise

        # Check if we landed on the OTRS dashboard (already authenticated)
        if "Action=AgentDashboard" in resp.url or "AgentDashboard" in resp.text:
            log.info("Authenticated via HTTP Basic Auth → OTRS Dashboard reached.")
            self._extract_session_id(resp)
            return True

        # Check if OTRS shows its own login form (need form-based login too)
        soup = BeautifulSoup(resp.text, "html.parser")
        login_form = soup.find("form", {"id": "Login"}) or soup.find(
            "input", {"name": "Action", "value": "Login"}
        )

        if login_form:
            log.info("OTRS form login detected. Submitting credentials...")
            return self._form_login(resp)

        # Check if we're somehow already on a valid OTRS page
        if "Action=" in resp.url or "index.pl" in resp.url:
            log.info("Appears to be authenticated. Proceeding.")
            self._extract_session_id(resp)
            return True

        log.error(f"Unexpected response. URL: {resp.url}, Status: {resp.status_code}")
        log.debug(f"Response snippet: {resp.text[:500]}")
        return False

    def _form_login(self, initial_resp: requests.Response) -> bool:
        """Handle OTRS form-based login."""
        soup = BeautifulSoup(initial_resp.text, "html.parser")

        # Find the login form action URL
        form = soup.find("form", {"id": "Login"})
        if not form:
            form = soup.find("form")

        action_url = self.base_url

        # Build login payload
        login_data = {
            "Action": "Login",
            "RequestedURL": "",
            "Lang": "es",
            "TimeOffset": "180",  # UTC-3 Argentina
            "User": self.username,
            "Password": self.password,
        }

        # Also grab any hidden fields
        if form:
            for hidden in form.find_all("input", {"type": "hidden"}):
                name = hidden.get("name")
                value = hidden.get("value", "")
                if name and name not in login_data:
                    login_data[name] = value

        resp = self.session.post(action_url, data=login_data, timeout=30, allow_redirects=True)

        if "Action=AgentDashboard" in resp.url or "AgentDashboard" in resp.text:
            log.info("Form login successful.")
            self._extract_session_id(resp)
            return True

        if "Login failed" in resp.text or "LoginFailed" in resp.text:
            log.error("OTRS form login failed. Invalid credentials.")
            return False

        # Might have redirected somewhere valid
        self._extract_session_id(resp)
        return "index.pl" in resp.url

    def _extract_session_id(self, resp: requests.Response):
        """Extract the OTRS session ID from URL or cookies."""
        # From URL parameter
        parsed = urlparse(resp.url)
        qs = parse_qs(parsed.query)
        if "SessionID" in qs:
            self._session_id = qs["SessionID"][0]
        # Also check cookies
        for cookie in self.session.cookies:
            if "Session" in cookie.name or "OTRS" in cookie.name:
                self._session_id = cookie.value
                break

    def _build_url(self, **params) -> str:
        """Build an OTRS URL with the given parameters."""
        url = self.base_url + "?" + urlencode(params, doseq=True)
        return url

    def _get(self, url: str) -> requests.Response:
        """Make a GET request with rate limiting."""
        time.sleep(REQUEST_DELAY)
        resp = self.session.get(url, timeout=60, allow_redirects=True)
        resp.raise_for_status()
        return resp

    def _post(self, url: str, data: dict) -> requests.Response:
        """Make a POST request with rate limiting."""
        time.sleep(REQUEST_DELAY)
        resp = self.session.post(url, data=data, timeout=60, allow_redirects=True)
        resp.raise_for_status()
        return resp

    def search_tickets(
        self,
        fulltext: str,
        queues: list[str],
        date_from: str,
        date_to: str,
    ) -> list[dict]:
        """
        Search for tickets matching the given criteria.
        Returns a list of dicts with ticket_id, ticket_number, title, etc.
        """
        log.info("Fetching search form to discover queue IDs...")

        # First, load the search form to get queue IDs
        search_form_url = self._build_url(Action="AgentTicketSearch")
        resp = self._get(search_form_url)
        soup = BeautifulSoup(resp.text, "html.parser")

        # Find queue select and map names to IDs
        queue_select = soup.find("select", {"name": "QueueIDs"}) or soup.find(
            "select", {"id": "QueueIDs"}
        )

        queue_id_map = {}
        if queue_select:
            for option in queue_select.find_all("option"):
                qid = option.get("value", "")
                qname = option.text.strip().lstrip("\xa0").strip()
                # Clean OTRS indentation (uses &nbsp; or spaces for hierarchy)
                clean_name = re.sub(r"^[\s\xa0|\\-]+", "", qname).strip()
                if qid and clean_name:
                    queue_id_map[clean_name] = qid
                    # Also store with parent path stripped
                    if "::" in clean_name:
                        short_name = clean_name.split("::")[-1].strip()
                        queue_id_map[short_name] = qid

        log.info(f"Found {len(queue_id_map)} queues in OTRS.")
        log.debug(f"Queue map: {queue_id_map}")

        # Map requested queue names to IDs
        selected_queue_ids = []
        for q in queues:
            q_clean = q.strip()
            if q_clean in queue_id_map:
                selected_queue_ids.append(queue_id_map[q_clean])
                log.info(f"  Queue '{q_clean}' → ID {queue_id_map[q_clean]}")
            else:
                # Fuzzy match
                matched = False
                for name, qid in queue_id_map.items():
                    if q_clean.lower() in name.lower() or name.lower() in q_clean.lower():
                        selected_queue_ids.append(qid)
                        log.info(f"  Queue '{q_clean}' ~ '{name}' → ID {qid}")
                        matched = True
                        break
                if not matched:
                    log.warning(f"  Queue '{q_clean}' not found in OTRS. Skipping.")

        if not selected_queue_ids:
            log.warning("No valid queue IDs found. Searching without queue filter.")

        # Parse dates
        df = datetime.strptime(date_from, "%Y-%m-%d")
        dt = datetime.strptime(date_to, "%Y-%m-%d")

        # Build search request
        search_params = {
            "Action": "AgentTicketSearch",
            "Subaction": "Search",
            "Fulltext": fulltext,
            "TicketCreateTimeNewerDate": f"{df.day:02d}/{df.month:02d}/{df.year}",
            "TicketCreateTimeOlderDate": f"{dt.day:02d}/{dt.month:02d}/{dt.year}",
            "ResultForm": "Normal",
            "QueueIDs": selected_queue_ids,
        }

        # Also try the OTRS 3.3 date format (individual fields)
        search_data = {
            "Action": "AgentTicketSearch",
            "Subaction": "Search",
            "Fulltext": fulltext,
            "QueueIDs": selected_queue_ids,
            "TicketCreateTimeStartDay": str(df.day),
            "TicketCreateTimeStartMonth": str(df.month),
            "TicketCreateTimeStartYear": str(df.year),
            "TicketCreateTimeStopDay": str(dt.day),
            "TicketCreateTimeStopMonth": str(dt.month),
            "TicketCreateTimeStopYear": str(dt.year),
            "TicketCreateTimePointStart": "Last",
            "ResultForm": "Normal",
        }

        log.info("Executing search...")
        resp = self._post(self.base_url, data=search_data)

        # Parse search results
        tickets = self._parse_search_results(resp)

        # Handle pagination — OTRS 3.3 shows 50 results per page by default
        page = 1
        while True:
            # Check for "next page" link
            soup = BeautifulSoup(resp.text, "html.parser")
            next_link = soup.find("a", string=re.compile(r"(Siguiente|Next|>>)"))
            if not next_link:
                # Also try numbered page links
                page_links = soup.find_all("a", {"class": re.compile(r"page|Page")})
                next_page = None
                for pl in page_links:
                    href = pl.get("href", "")
                    if f"StartHit=" in href:
                        try:
                            hit = int(re.search(r"StartHit=(\d+)", href).group(1))
                            if hit > page * 50:
                                next_page = pl
                                break
                        except (AttributeError, ValueError):
                            pass
                if not next_page:
                    break
                next_link = next_page

            href = next_link.get("href", "")
            if not href:
                break

            page += 1
            log.info(f"Fetching page {page}...")
            if href.startswith("http"):
                next_url = href
            else:
                next_url = urljoin(self.base_url, href)

            resp = self._get(next_url)
            more_tickets = self._parse_search_results(resp)
            if not more_tickets:
                break
            tickets.extend(more_tickets)

        log.info(f"Total tickets found: {len(tickets)}")
        return tickets

    def _parse_search_results(self, resp: requests.Response) -> list[dict]:
        """Parse the ticket search results page and extract ticket info."""
        tickets = []
        soup = BeautifulSoup(resp.text, "html.parser")

        # OTRS 3.3 renders results in a table with class "Overview" or "TableSmall"
        table = soup.find("table", {"class": re.compile(r"Overview|TableSmall|DataTable")})
        if not table:
            # Try finding ticket links directly
            ticket_links = soup.find_all("a", href=re.compile(r"Action=AgentTicketZoom"))
            for link in ticket_links:
                href = link.get("href", "")
                ticket_id_match = re.search(r"TicketID=(\d+)", href)
                if ticket_id_match:
                    ticket_id = ticket_id_match.group(1)
                    tickets.append({
                        "ticket_id": ticket_id,
                        "ticket_number": link.text.strip(),
                        "title": "",
                        "url": urljoin(self.base_url, href),
                    })
            return tickets

        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            # Find the ticket link
            link = row.find("a", href=re.compile(r"Action=AgentTicketZoom"))
            if not link:
                continue

            href = link.get("href", "")
            ticket_id_match = re.search(r"TicketID=(\d+)", href)
            if not ticket_id_match:
                continue

            ticket_id = ticket_id_match.group(1)
            ticket_number = link.text.strip()

            # Try to get the title from the row
            title = ""
            title_cell = row.find("td", {"class": re.compile(r"Title|Subject")})
            if title_cell:
                title = title_cell.text.strip()
            else:
                # Title is often in the last or second-to-last cell
                for cell in cells:
                    text = cell.text.strip()
                    if len(text) > 20 and text != ticket_number:
                        title = text
                        break

            # Try to get the queue
            queue = ""
            queue_cell = row.find("td", {"class": re.compile(r"Queue")})
            if queue_cell:
                queue = queue_cell.text.strip()

            # Try to get creation date
            created = ""
            date_cell = row.find("td", {"class": re.compile(r"Age|Created|Time")})
            if date_cell:
                created = date_cell.text.strip()

            tickets.append({
                "ticket_id": ticket_id,
                "ticket_number": ticket_number,
                "title": title,
                "queue": queue,
                "created": created,
                "url": urljoin(self.base_url, href),
            })

        return tickets

    def fetch_first_articles(self, tickets: list[dict]) -> list[dict]:
        """
        For each ticket, fetch the detail page and extract the first article
        (the original email/message).
        """
        results = []
        total = len(tickets)

        for i, ticket in enumerate(tickets, 1):
            log.info(f"  [{i}/{total}] Ticket {ticket.get('ticket_number', ticket['ticket_id'])}...")

            try:
                content = self._fetch_ticket_first_article(ticket["ticket_id"])
                if content:
                    ticket["first_article_body"] = content["body"]
                    ticket["first_article_from"] = content.get("from", "")
                    ticket["first_article_subject"] = content.get("subject", "")
                    ticket["first_article_date"] = content.get("date", "")
                    results.append(ticket)
                else:
                    log.warning(f"    No article content found for ticket {ticket['ticket_id']}")
                    ticket["first_article_body"] = ""
                    results.append(ticket)
            except Exception as e:
                log.error(f"    Error fetching ticket {ticket['ticket_id']}: {e}")
                ticket["first_article_body"] = ""
                results.append(ticket)

        return results

    def _fetch_ticket_first_article(self, ticket_id: str) -> dict | None:
        """Fetch the first article of a specific ticket."""
        url = self._build_url(Action="AgentTicketZoom", TicketID=ticket_id)
        resp = self._get(url)
        soup = BeautifulSoup(resp.text, "html.parser")

        # OTRS 3.3 shows articles in the ticket zoom view
        # The first article is typically the first one in the list

        # Method 1: Find article bodies directly
        # In OTRS 3.3, article content may be in iframes or inline
        article_bodies = soup.find_all(
            "div", {"class": re.compile(r"ArticleBody|ArticleMailContent|MessageBody")}
        )

        if article_bodies:
            first_body = article_bodies[0]
            body_text = self._clean_html_to_text(first_body)

            # Try to get metadata from the article header
            meta = self._extract_article_meta(soup, 0)
            return {
                "body": body_text,
                "from": meta.get("from", ""),
                "subject": meta.get("subject", ""),
                "date": meta.get("date", ""),
            }

        # Method 2: Articles might be loaded via AJAX — fetch the first article directly
        # In OTRS 3.3, article content can be fetched via:
        # Action=AgentTicketArticleContent;TicketID=X;ArticleID=Y
        article_links = soup.find_all(
            "a", href=re.compile(r"Action=AgentTicket(Zoom|Article).*ArticleID=")
        )

        if not article_links:
            # Try finding article IDs in the page
            article_ids = re.findall(r"ArticleID[=:][\s]*['\"]?(\d+)", resp.text)
            if article_ids:
                first_article_id = article_ids[0]
                return self._fetch_article_content(ticket_id, first_article_id)
            return None

        # Get the first article link
        first_link = article_links[0]
        href = first_link.get("href", "")
        article_id_match = re.search(r"ArticleID=(\d+)", href)

        if article_id_match:
            article_id = article_id_match.group(1)
            return self._fetch_article_content(ticket_id, article_id)

        return None

    def _fetch_article_content(self, ticket_id: str, article_id: str) -> dict:
        """Fetch a specific article's content."""
        # Try the plain text view first
        url = self._build_url(
            Action="AgentTicketPlain",
            TicketID=ticket_id,
            ArticleID=article_id,
        )
        try:
            resp = self._get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            plain_content = soup.find("pre") or soup.find(
                "div", {"class": re.compile(r"Plain|Content")}
            )
            if plain_content:
                text = plain_content.text.strip()
                if len(text) > 20:
                    return {"body": text, "from": "", "subject": "", "date": ""}
        except Exception:
            pass

        # Fallback: try the article zoom view
        url = self._build_url(
            Action="AgentTicketZoom",
            Subaction="ArticleUpdate",
            TicketID=ticket_id,
            ArticleID=article_id,
        )
        try:
            resp = self._get(url)

            # Response might be JSON with HTML content
            try:
                data = resp.json()
                if isinstance(data, dict) and "Data" in data:
                    html_content = data["Data"]
                    soup = BeautifulSoup(html_content, "html.parser")
                    return {
                        "body": self._clean_html_to_text(soup),
                        "from": "",
                        "subject": "",
                        "date": "",
                    }
            except (ValueError, KeyError):
                pass

            # Plain HTML response
            soup = BeautifulSoup(resp.text, "html.parser")
            body_div = soup.find(
                "div", {"class": re.compile(r"ArticleBody|MessageBody|ArticleContent")}
            )
            if body_div:
                return {
                    "body": self._clean_html_to_text(body_div),
                    "from": "",
                    "subject": "",
                    "date": "",
                }

            # Last resort: get all text
            text = soup.get_text(separator="\n", strip=True)
            if len(text) > 50:
                return {"body": text[:5000], "from": "", "subject": "", "date": ""}
        except Exception as e:
            log.debug(f"Error fetching article {article_id}: {e}")

        return {"body": "", "from": "", "subject": "", "date": ""}

    def _extract_article_meta(self, soup: BeautifulSoup, index: int) -> dict:
        """Extract metadata (from, subject, date) of an article."""
        meta = {}

        # Look for article header info
        headers = soup.find_all(
            "div", {"class": re.compile(r"ArticleHeader|MessageHeader")}
        )
        if index < len(headers):
            header = headers[index]

            from_elem = header.find(string=re.compile(r"(De|From):"))
            if from_elem:
                parent = from_elem.parent
                meta["from"] = parent.text.replace("De:", "").replace("From:", "").strip()

            subject_elem = header.find(string=re.compile(r"(Asunto|Subject):"))
            if subject_elem:
                parent = subject_elem.parent
                meta["subject"] = (
                    parent.text.replace("Asunto:", "").replace("Subject:", "").strip()
                )

            date_elem = header.find(string=re.compile(r"(Fecha|Date):"))
            if date_elem:
                parent = date_elem.parent
                meta["date"] = (
                    parent.text.replace("Fecha:", "").replace("Date:", "").strip()
                )

        return meta

    def _clean_html_to_text(self, element) -> str:
        """Convert an HTML element to clean plain text."""
        if element is None:
            return ""

        # Remove script and style elements
        for tag in element.find_all(["script", "style"]):
            tag.decompose()

        # Get text
        text = element.get_text(separator="\n", strip=True)

        # Clean up
        text = unescape(text)
        # Remove excessive whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)

        return text.strip()

    def close(self):
        """Close the session."""
        try:
            # Try to logout cleanly
            self._get(self._build_url(Action="Logout"))
        except Exception:
            pass
        self.session.close()
