"""
Report Generator
================
Generates a polished HTML report with intent classification results,
charts, and word cloud visualization.
"""

import logging
from datetime import datetime

log = logging.getLogger(__name__)

# ── Colors for intent ──
INTENT_COLORS = {
    "CONSULTA": "#00b894",
    "RECLAMO": "#e17055",
    "INDETERMINADO": "#636e72",
}

INTENT_ICONS = {
    "CONSULTA": "&#x2753;",     # question mark
    "RECLAMO": "&#x26A0;",      # warning sign
    "INDETERMINADO": "&#x2796;", # heavy minus
}


class ReportGenerator:
    def generate(
        self,
        tickets: list[dict],
        intent_summary: dict,
        wordcloud_b64: str,
        search_params: dict,
        generated_at: datetime,
        timeline_data: dict = None,
        top_bigrams: list = None,
        top_trigrams: list = None,
    ) -> str:
        """Generate the full HTML report."""
        ticket_rows = self._build_ticket_rows(tickets)
        timeline_charts = self._build_timeline_charts(timeline_data or {})
        ngram_lists = self._build_ngram_lists(top_bigrams or [], top_trigrams or [])

        html = REPORT_TEMPLATE.format(
            generated_at=generated_at.strftime("%d/%m/%Y %H:%M"),
            fulltext=search_params.get("fulltext", ""),
            queues=", ".join(search_params.get("queues", [])),
            date_from=search_params.get("date_from", ""),
            date_to=search_params.get("date_to", ""),
            total=intent_summary.get("total", 0),
            consulta=intent_summary.get("consulta", 0),
            reclamo=intent_summary.get("reclamo", 0),
            indeterminado=intent_summary.get("indeterminado", 0),
            consulta_pct=intent_summary.get("consulta_pct", 0),
            reclamo_pct=intent_summary.get("reclamo_pct", 0),
            indeterminado_pct=intent_summary.get("indeterminado_pct", 0),
            wordcloud_b64=wordcloud_b64,
            ticket_rows=ticket_rows,
            chart_consulta=intent_summary.get("consulta", 0),
            chart_reclamo=intent_summary.get("reclamo", 0),
            chart_indeterminado=intent_summary.get("indeterminado", 0),
            timeline_charts=timeline_charts,
            ngram_lists=ngram_lists,
        )

        return html

    def _build_ticket_rows(self, tickets: list[dict]) -> str:
        rows = []
        for idx, t in enumerate(tickets):
            intent = t.get("intent", "INDETERMINADO")
            color = INTENT_COLORS.get(intent, "#636e72")
            icon = INTENT_ICONS.get(intent, "")
            label = t.get("intent_label", "Indeterminado")
            confidence = t.get("confidence", 0)

            # Full body — escape HTML but preserve line breaks
            body = t.get("user_message_body", "") or t.get("first_article_body", "")
            body_html = (
                body.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("\n", "<br>")
            )

            # Short preview for the collapsed row
            preview = body[:150].replace("\n", " ").strip()
            if len(body) > 150:
                preview += "..."
            preview = (
                preview.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
            )

            title = (
                t.get("title", "")
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )

            ticket_number = t.get('ticket_number', t.get('ticket_id', ''))
            queue = (t.get("queue", "")
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            created = t.get("created", "")
            article_from = (t.get("first_article_from", "")
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )

            staff_badge = ""
            if t.get("staff_filtered"):
                staff_badge = ' <span class="badge staff-badge">Staff filtrado</span>'

            row = f"""
            <div class="ticket-card" data-intent="{intent}">
                <div class="ticket-header" onclick="toggleBody('body-{idx}', this)">
                    <div class="ticket-meta-row">
                        <span class="ticket-number">{ticket_number}</span>
                        <span class="badge" style="--badge-color: {color}">{icon} {label}</span>{staff_badge}
                        <div class="score-bar">
                            <div class="score-fill" style="width: {confidence*100:.0f}%; background: {color}"></div>
                        </div>
                        <span class="score-value">{confidence:.0%}</span>
                        <span class="ticket-queue">{queue}</span>
                        <span class="ticket-date">{created}</span>
                        <span class="expand-icon">&#x25BC;</span>
                    </div>
                    <div class="ticket-title">{title}</div>
                    <div class="ticket-preview">{preview}</div>
                </div>
                <div class="ticket-body" id="body-{idx}">
                    {f'<div class="ticket-from"><strong>De:</strong> {article_from}</div>' if article_from else ''}
                    <div class="ticket-body-text">{body_html}</div>
                </div>
            </div>"""
            rows.append(row)
        return "\n".join(rows)

    def _build_timeline_charts(self, timeline_data):
        by_day = timeline_data.get("by_day", [])
        by_month = timeline_data.get("by_month", [])
        if not by_day and not by_month:
            return ""

        max_day = max((d["count"] for d in by_day), default=1)
        day_bars = ""
        for d in by_day:
            pct = d["count"] / max_day * 100
            short_date = d["date"][5:]
            day_bars += (
                '<div class="timeline-bar-wrap">'
                '<span class="timeline-label">%s</span>'
                '<div class="timeline-bar">'
                '<div class="timeline-bar-fill" style="width:%.0f%%"></div>'
                '</div>'
                '<span class="timeline-count">%d</span>'
                '</div>' % (short_date, pct, d["count"])
            )

        max_month = max((m["count"] for m in by_month), default=1)
        month_names = {"01":"Ene","02":"Feb","03":"Mar","04":"Abr","05":"May",
                       "06":"Jun","07":"Jul","08":"Ago","09":"Sep","10":"Oct",
                       "11":"Nov","12":"Dic"}
        month_bars = ""
        for m in by_month:
            pct = m["count"] / max_month * 100
            parts = m["month"].split("-")
            label = "%s %s" % (month_names.get(parts[1], parts[1]), parts[0])
            month_bars += (
                '<div class="timeline-bar-wrap">'
                '<span class="timeline-label">%s</span>'
                '<div class="timeline-bar">'
                '<div class="timeline-bar-fill month-fill" style="width:%.0f%%"></div>'
                '</div>'
                '<span class="timeline-count">%d</span>'
                '</div>' % (label, pct, m["count"])
            )

        return (
            '<div class="timeline-charts">'
            '<div class="timeline-chart">'
            '<h3 class="timeline-title">Tickets por D\u00eda</h3>'
            '<div class="timeline-bars">%s</div></div>'
            '<div class="timeline-chart">'
            '<h3 class="timeline-title">Tickets por Mes</h3>'
            '<div class="timeline-bars">%s</div></div>'
            '</div>' % (day_bars, month_bars)
        )

    def _build_ngram_lists(self, top_bigrams, top_trigrams):
        if not top_bigrams and not top_trigrams:
            return ""

        def build_list(items, title):
            if not items:
                return ""
            max_count = items[0]["count"] if items else 1
            rows = ""
            for i, item in enumerate(items, 1):
                pct = item["count"] / max_count * 100
                rows += (
                    '<div class="ngram-item">'
                    '<span class="ngram-rank">%d.</span>'
                    '<span class="ngram-term">%s</span>'
                    '<div class="ngram-bar">'
                    '<div class="ngram-bar-fill" style="width:%.0f%%"></div>'
                    '</div>'
                    '<span class="ngram-count">%d</span>'
                    '</div>' % (i, item["term"], pct, item["count"])
                )
            return (
                '<div class="ngram-list">'
                '<h3 class="ngram-title">%s</h3>'
                '%s</div>' % (title, rows)
            )

        bigram_html = build_list(top_bigrams, "Top 10 Bigramas")
        trigram_html = build_list(top_trigrams, "Top 10 Trigramas")

        return '<div class="ngram-lists">%s%s</div>' % (bigram_html, trigram_html)


# ── HTML Template ──
REPORT_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Clasificaci\u00f3n de Tickets por Intenci\u00f3n — OTRS</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,wght@0,400;0,500;0,700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg-primary: #0f0f1a;
    --bg-secondary: #1a1a2e;
    --bg-card: #16213e;
    --bg-card-hover: #1a2744;
    --text-primary: #e2e8f0;
    --text-secondary: #94a3b8;
    --text-muted: #64748b;
    --accent-teal: #00b894;
    --accent-orange: #e17055;
    --accent-gray: #636e72;
    --accent-blue: #3b82f6;
    --border: #1e293b;
    --radius: 12px;
  }}

  * {{ margin: 0; padding: 0; box-sizing: border-box; }}

  body {{
    font-family: 'DM Sans', -apple-system, sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    line-height: 1.6;
    min-height: 100vh;
  }}

  .container {{
    max-width: 1400px;
    margin: 0 auto;
    padding: 2rem 1.5rem;
  }}

  /* ── Header ── */
  .header {{
    text-align: center;
    padding: 3rem 0 2rem;
    position: relative;
  }}

  .header::before {{
    content: '';
    position: absolute;
    top: 0; left: 50%;
    transform: translateX(-50%);
    width: 200px; height: 3px;
    background: linear-gradient(90deg, var(--accent-teal), var(--accent-orange));
    border-radius: 2px;
  }}

  .header h1 {{
    font-size: 2.2rem;
    font-weight: 700;
    letter-spacing: -0.03em;
    margin-bottom: 0.5rem;
    background: linear-gradient(135deg, #e2e8f0, #94a3b8);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }}

  .header .subtitle {{
    color: var(--text-muted);
    font-size: 0.95rem;
  }}

  .meta-bar {{
    display: flex;
    justify-content: center;
    gap: 2rem;
    margin-top: 1.5rem;
    flex-wrap: wrap;
  }}

  .meta-item {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.8rem;
    color: var(--text-muted);
    background: var(--bg-secondary);
    padding: 0.4rem 1rem;
    border-radius: 20px;
    border: 1px solid var(--border);
  }}

  .meta-item strong {{
    color: var(--text-secondary);
  }}

  /* ── Stats Cards ── */
  .stats-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1rem;
    margin: 2rem 0;
  }}

  @media (max-width: 768px) {{
    .stats-grid {{ grid-template-columns: repeat(2, 1fr); }}
  }}

  .stat-card {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.5rem;
    text-align: center;
    transition: transform 0.2s, border-color 0.2s;
  }}

  .stat-card:hover {{
    transform: translateY(-2px);
    border-color: var(--accent-blue);
  }}

  .stat-card .stat-value {{
    font-size: 2.5rem;
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
    line-height: 1.1;
  }}

  .stat-card .stat-label {{
    font-size: 0.85rem;
    color: var(--text-muted);
    margin-top: 0.3rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }}

  .stat-card .stat-pct {{
    font-size: 0.9rem;
    color: var(--text-secondary);
    margin-top: 0.2rem;
    font-family: 'JetBrains Mono', monospace;
  }}

  .stat-card.total .stat-value {{ color: var(--accent-blue); }}
  .stat-card.consulta .stat-value {{ color: var(--accent-teal); }}
  .stat-card.reclamo .stat-value {{ color: var(--accent-orange); }}
  .stat-card.indeterminado .stat-value {{ color: var(--accent-gray); }}

  /* ── Chart Section ── */
  .section {{
    margin: 2.5rem 0;
  }}

  .section-title {{
    font-size: 1.3rem;
    font-weight: 600;
    margin-bottom: 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--border);
    color: var(--text-primary);
  }}

  .chart-container {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 2rem;
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 3rem;
    flex-wrap: wrap;
  }}

  .donut-chart {{
    position: relative;
    width: 220px;
    height: 220px;
  }}

  .donut-chart svg {{
    transform: rotate(-90deg);
  }}

  .donut-center {{
    position: absolute;
    top: 50%; left: 50%;
    transform: translate(-50%, -50%);
    text-align: center;
  }}

  .donut-center .big-num {{
    font-size: 2.2rem;
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
    color: var(--text-primary);
  }}

  .donut-center .label {{
    font-size: 0.75rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }}

  .chart-legend {{
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }}

  .legend-item {{
    display: flex;
    align-items: center;
    gap: 0.8rem;
  }}

  .legend-dot {{
    width: 14px;
    height: 14px;
    border-radius: 4px;
    flex-shrink: 0;
  }}

  .legend-label {{
    font-size: 0.95rem;
    color: var(--text-secondary);
  }}

  .legend-value {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.9rem;
    color: var(--text-primary);
    margin-left: auto;
    padding-left: 1rem;
  }}

  /* ── Horizontal bar chart ── */
  .bar-chart {{
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
    min-width: 300px;
    flex: 1;
    max-width: 500px;
  }}

  .bar-row {{
    display: flex;
    align-items: center;
    gap: 1rem;
  }}

  .bar-label {{
    width: 110px;
    font-size: 0.85rem;
    color: var(--text-secondary);
    text-align: right;
  }}

  .bar-track {{
    flex: 1;
    height: 28px;
    background: var(--bg-primary);
    border-radius: 6px;
    overflow: hidden;
    position: relative;
  }}

  .bar-fill {{
    height: 100%;
    border-radius: 6px;
    transition: width 1s ease;
    display: flex;
    align-items: center;
    padding-left: 10px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem;
    color: white;
    font-weight: 500;
    min-width: fit-content;
  }}

  /* ── Word Cloud ── */
  .wordcloud-container {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1rem;
    text-align: center;
  }}

  .wordcloud-container img {{
    max-width: 100%;
    height: auto;
    border-radius: 8px;
  }}

  /* ── Table ── */
  .table-container {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
  }}

  .table-controls {{
    display: flex;
    gap: 0.5rem;
    padding: 1rem;
    border-bottom: 1px solid var(--border);
    flex-wrap: wrap;
  }}

  .filter-btn {{
    font-family: 'DM Sans', sans-serif;
    font-size: 0.85rem;
    padding: 0.4rem 1rem;
    border-radius: 20px;
    border: 1px solid var(--border);
    background: transparent;
    color: var(--text-secondary);
    cursor: pointer;
    transition: all 0.2s;
  }}

  .filter-btn:hover, .filter-btn.active {{
    background: var(--accent-blue);
    color: white;
    border-color: var(--accent-blue);
  }}

  .cell-title {{
    max-width: 250px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--text-secondary);
  }}

  .cell-preview {{
    max-width: 350px;
    font-size: 0.82rem;
    color: var(--text-muted);
    line-height: 1.4;
  }}

  /* ── Ticket Cards ── */
  .ticket-card {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    margin-bottom: 0.5rem;
    overflow: hidden;
    transition: border-color 0.2s;
  }}

  .ticket-card:hover {{
    border-color: var(--accent-blue);
  }}

  .ticket-header {{
    padding: 0.8rem 1rem;
    cursor: pointer;
    user-select: none;
  }}

  .ticket-meta-row {{
    display: flex;
    align-items: center;
    gap: 0.6rem;
    flex-wrap: wrap;
  }}

  .ticket-number {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.82rem;
    color: var(--accent-blue);
    font-weight: 500;
  }}

  .ticket-queue {{
    font-size: 0.78rem;
    color: var(--text-muted);
    background: var(--bg-primary);
    padding: 0.15rem 0.5rem;
    border-radius: 10px;
  }}

  .ticket-date {{
    font-size: 0.78rem;
    color: var(--text-muted);
    font-family: 'JetBrains Mono', monospace;
  }}

  .expand-icon {{
    margin-left: auto;
    font-size: 0.7rem;
    color: var(--text-muted);
    transition: transform 0.2s;
  }}

  .ticket-header.expanded .expand-icon {{
    transform: rotate(180deg);
  }}

  .ticket-title {{
    font-size: 0.9rem;
    color: var(--text-secondary);
    margin-top: 0.3rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}

  .ticket-preview {{
    font-size: 0.8rem;
    color: var(--text-muted);
    margin-top: 0.2rem;
    line-height: 1.3;
  }}

  .ticket-header.expanded .ticket-preview {{
    display: none;
  }}

  .ticket-body {{
    display: none;
    border-top: 1px solid var(--border);
    padding: 1rem 1.2rem;
    background: var(--bg-primary);
  }}

  .ticket-body.visible {{
    display: block;
  }}

  .ticket-from {{
    font-size: 0.82rem;
    color: var(--text-secondary);
    margin-bottom: 0.8rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--border);
  }}

  .ticket-body-text {{
    font-size: 0.85rem;
    color: var(--text-primary);
    line-height: 1.6;
    word-wrap: break-word;
    max-height: 600px;
    overflow-y: auto;
  }}

  .badge {{
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    font-size: 0.8rem;
    font-weight: 500;
    padding: 0.25rem 0.7rem;
    border-radius: 20px;
    background: color-mix(in srgb, var(--badge-color) 15%, transparent);
    color: var(--badge-color);
    white-space: nowrap;
  }}

  .staff-badge {{
    --badge-color: #fdcb6e;
    font-size: 0.7rem;
    padding: 0.15rem 0.5rem;
  }}

  .score-bar {{
    width: 60px;
    height: 6px;
    background: var(--bg-primary);
    border-radius: 3px;
    overflow: hidden;
    display: inline-block;
    vertical-align: middle;
    margin-right: 0.4rem;
  }}

  .score-fill {{
    height: 100%;
    border-radius: 3px;
  }}

  .score-value {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem;
    color: var(--text-muted);
  }}

  /* ── Timeline Charts ── */
  .timeline-charts {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1.5rem;
    margin-bottom: 1rem;
  }}

  @media (max-width: 900px) {{
    .timeline-charts {{ grid-template-columns: 1fr; }}
  }}

  .timeline-chart {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.2rem;
  }}

  .timeline-title {{
    font-size: 1rem;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 1rem;
  }}

  .timeline-bars {{
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    max-height: 400px;
    overflow-y: auto;
  }}

  .timeline-bar-wrap {{
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }}

  .timeline-label {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem;
    color: var(--text-muted);
    width: 58px;
    text-align: right;
    flex-shrink: 0;
  }}

  .timeline-bar {{
    flex: 1;
    height: 18px;
    background: var(--bg-primary);
    border-radius: 4px;
    overflow: hidden;
  }}

  .timeline-bar-fill {{
    height: 100%;
    background: var(--accent-blue);
    border-radius: 4px;
    transition: width 0.6s ease;
    min-width: 2px;
  }}

  .timeline-bar-fill.month-fill {{
    background: linear-gradient(90deg, var(--accent-teal), var(--accent-orange));
  }}

  .timeline-count {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem;
    color: var(--text-secondary);
    width: 26px;
    flex-shrink: 0;
  }}

  /* ── N-gram Lists ── */
  .ngram-lists {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1.5rem;
    margin-top: 1.5rem;
  }}

  @media (max-width: 900px) {{
    .ngram-lists {{ grid-template-columns: 1fr; }}
  }}

  .ngram-list {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.2rem;
  }}

  .ngram-title {{
    font-size: 1rem;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 1rem;
  }}

  .ngram-item {{
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.4rem;
  }}

  .ngram-rank {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem;
    color: var(--text-muted);
    width: 22px;
    text-align: right;
    flex-shrink: 0;
  }}

  .ngram-term {{
    font-size: 0.85rem;
    color: var(--text-primary);
    min-width: 120px;
    flex-shrink: 0;
  }}

  .ngram-bar {{
    flex: 1;
    height: 14px;
    background: var(--bg-primary);
    border-radius: 3px;
    overflow: hidden;
  }}

  .ngram-bar-fill {{
    height: 100%;
    background: linear-gradient(90deg, #6366f1, #8b5cf6);
    border-radius: 3px;
    min-width: 2px;
  }}

  .ngram-count {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem;
    color: var(--text-secondary);
    width: 26px;
    text-align: right;
    flex-shrink: 0;
  }}

  /* ── Footer ── */
  .footer {{
    text-align: center;
    padding: 3rem 0 2rem;
    color: var(--text-muted);
    font-size: 0.8rem;
  }}

  .footer a {{
    color: var(--accent-blue);
    text-decoration: none;
  }}

  /* ── Animations ── */
  @keyframes fadeIn {{
    from {{ opacity: 0; transform: translateY(10px); }}
    to {{ opacity: 1; transform: translateY(0); }}
  }}

  .section {{
    animation: fadeIn 0.6s ease both;
  }}

  .section:nth-child(2) {{ animation-delay: 0.1s; }}
  .section:nth-child(3) {{ animation-delay: 0.2s; }}
  .section:nth-child(4) {{ animation-delay: 0.3s; }}

  /* ── Responsive table ── */
  @media (max-width: 900px) {{
    .ticket-meta-row {{ gap: 0.4rem; }}
    .ticket-queue, .ticket-date {{ display: none; }}
  }}
</style>
</head>
<body>

<div class="container">

  <!-- Header -->
  <header class="header">
    <h1>Clasificaci\u00f3n de Tickets por Intenci\u00f3n — OTRS</h1>
    <p class="subtitle">Reporte autom\u00e1tico generado el {generated_at}</p>
    <div class="meta-bar">
      <span class="meta-item">B\u00fasqueda: <strong>{fulltext}</strong></span>
      <span class="meta-item">Colas: <strong>{queues}</strong></span>
      <span class="meta-item">Per\u00edodo: <strong>{date_from} \u2192 {date_to}</strong></span>
    </div>
  </header>

  <!-- Stats -->
  <div class="stats-grid">
    <div class="stat-card total">
      <div class="stat-value">{total}</div>
      <div class="stat-label">Total tickets</div>
    </div>
    <div class="stat-card consulta">
      <div class="stat-value">{consulta}</div>
      <div class="stat-label">Consulta / Duda</div>
      <div class="stat-pct">{consulta_pct}%</div>
    </div>
    <div class="stat-card reclamo">
      <div class="stat-value">{reclamo}</div>
      <div class="stat-label">Reclamo / Error</div>
      <div class="stat-pct">{reclamo_pct}%</div>
    </div>
    <div class="stat-card indeterminado">
      <div class="stat-value">{indeterminado}</div>
      <div class="stat-label">Indeterminado</div>
      <div class="stat-pct">{indeterminado_pct}%</div>
    </div>
  </div>

  <!-- Chart -->
  <div class="section">
    <h2 class="section-title">Distribuci\u00f3n por Intenci\u00f3n</h2>
    <div class="chart-container">

      <div class="donut-chart">
        <svg viewBox="0 0 220 220" width="220" height="220">
          <circle cx="110" cy="110" r="90" fill="none" stroke="var(--bg-primary)" stroke-width="24"/>
          <circle id="arc-consulta" cx="110" cy="110" r="90" fill="none"
            stroke="var(--accent-teal)" stroke-width="24"
            stroke-dasharray="0 565.5"
            stroke-linecap="round"/>
          <circle id="arc-reclamo" cx="110" cy="110" r="90" fill="none"
            stroke="var(--accent-orange)" stroke-width="24"
            stroke-dasharray="0 565.5"
            stroke-linecap="round"/>
          <circle id="arc-indeterminado" cx="110" cy="110" r="90" fill="none"
            stroke="var(--accent-gray)" stroke-width="24"
            stroke-dasharray="0 565.5"
            stroke-linecap="round"/>
        </svg>
        <div class="donut-center">
          <div class="big-num">{total}</div>
          <div class="label">tickets</div>
        </div>
      </div>

      <div class="bar-chart">
        <div class="bar-row">
          <span class="bar-label">Consulta/Duda</span>
          <div class="bar-track">
            <div class="bar-fill" style="width: {consulta_pct}%; background: var(--accent-teal);">
              {consulta} ({consulta_pct}%)
            </div>
          </div>
        </div>
        <div class="bar-row">
          <span class="bar-label">Reclamo/Error</span>
          <div class="bar-track">
            <div class="bar-fill" style="width: {reclamo_pct}%; background: var(--accent-orange);">
              {reclamo} ({reclamo_pct}%)
            </div>
          </div>
        </div>
        <div class="bar-row">
          <span class="bar-label">Indeterminado</span>
          <div class="bar-track">
            <div class="bar-fill" style="width: {indeterminado_pct}%; background: var(--accent-gray);">
              {indeterminado} ({indeterminado_pct}%)
            </div>
          </div>
        </div>
      </div>

      <div class="chart-legend">
        <div class="legend-item">
          <div class="legend-dot" style="background: var(--accent-teal)"></div>
          <span class="legend-label">Consulta/Duda</span>
          <span class="legend-value">{consulta}</span>
        </div>
        <div class="legend-item">
          <div class="legend-dot" style="background: var(--accent-orange)"></div>
          <span class="legend-label">Reclamo/Error</span>
          <span class="legend-value">{reclamo}</span>
        </div>
        <div class="legend-item">
          <div class="legend-dot" style="background: var(--accent-gray)"></div>
          <span class="legend-label">Indeterminado</span>
          <span class="legend-value">{indeterminado}</span>
        </div>
      </div>

    </div>
  </div>

  <!-- Timeline -->
  <div class="section">
    <h2 class="section-title">Volumen de Tickets</h2>
    {timeline_charts}
  </div>

  <!-- Word Cloud -->
  <div class="section">
    <h2 class="section-title">Nube de Palabras</h2>
    <div class="wordcloud-container">
      <img src="data:image/png;base64,{wordcloud_b64}" alt="Nube de palabras">
    </div>
    {ngram_lists}
  </div>

  <!-- Tickets Table -->
  <div class="section">
    <h2 class="section-title">Detalle por Ticket</h2>
    <div class="table-container">
      <div class="table-controls">
        <button class="filter-btn active" onclick="filterTickets('ALL')">Todos</button>
        <button class="filter-btn" onclick="filterTickets('CONSULTA')">&#x2753; Consultas</button>
        <button class="filter-btn" onclick="filterTickets('RECLAMO')">&#x26A0; Reclamos</button>
        <button class="filter-btn" onclick="filterTickets('INDETERMINADO')">&#x2796; Indeterminados</button>
        <button class="filter-btn" onclick="expandAll(true)" style="margin-left: auto;">Expandir todos</button>
        <button class="filter-btn" onclick="expandAll(false)">Colapsar todos</button>
      </div>
      <div id="tickets-body">
        {ticket_rows}
      </div>
    </div>
  </div>

  <footer class="footer">
    Generado autom\u00e1ticamente el {generated_at} &mdash;
    Clasificaci\u00f3n por intenci\u00f3n basada en patrones de keywords
  </footer>

</div>

<script>
// ── Donut chart animation ──
(function() {{
  const total = {total} || 1;
  const consulta = {chart_consulta};
  const reclamo = {chart_reclamo};
  const indeterminado = {chart_indeterminado};
  const C = 2 * Math.PI * 90; // circumference

  const consultaLen = (consulta / total) * C;
  const reclamoLen = (reclamo / total) * C;
  const indeterminadoLen = (indeterminado / total) * C;

  const arcConsulta = document.getElementById('arc-consulta');
  const arcReclamo = document.getElementById('arc-reclamo');
  const arcIndeterminado = document.getElementById('arc-indeterminado');

  if (arcConsulta) {{
    arcConsulta.setAttribute('stroke-dasharray', consultaLen + ' ' + C);
    arcConsulta.setAttribute('stroke-dashoffset', '0');

    arcReclamo.setAttribute('stroke-dasharray', reclamoLen + ' ' + C);
    arcReclamo.setAttribute('stroke-dashoffset', -consultaLen);

    arcIndeterminado.setAttribute('stroke-dasharray', indeterminadoLen + ' ' + C);
    arcIndeterminado.setAttribute('stroke-dashoffset', -(consultaLen + reclamoLen));
  }}
}})();

// ── Filter tickets ──
function filterTickets(intent) {{
  const cards = document.querySelectorAll('.ticket-card');
  const btns = document.querySelectorAll('.filter-btn');

  btns.forEach(b => {{
    if (b.textContent.includes('Expandir') || b.textContent.includes('Colapsar')) return;
    b.classList.remove('active');
  }});
  event.target.classList.add('active');

  cards.forEach(card => {{
    if (intent === 'ALL' || card.dataset.intent === intent) {{
      card.style.display = '';
    }} else {{
      card.style.display = 'none';
    }}
  }});
}}

function toggleBody(bodyId, headerEl) {{
  const body = document.getElementById(bodyId);
  if (body.classList.contains('visible')) {{
    body.classList.remove('visible');
    headerEl.classList.remove('expanded');
  }} else {{
    body.classList.add('visible');
    headerEl.classList.add('expanded');
  }}
}}

function expandAll(expand) {{
  document.querySelectorAll('.ticket-body').forEach(b => {{
    if (expand) b.classList.add('visible');
    else b.classList.remove('visible');
  }});
  document.querySelectorAll('.ticket-header').forEach(h => {{
    if (expand) h.classList.add('expanded');
    else h.classList.remove('expanded');
  }});
}}
</script>

</body>
</html>"""
