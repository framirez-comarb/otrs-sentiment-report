"""
Report Generator
================
Generates a polished HTML report with sentiment analysis results,
charts, and word cloud visualization.
"""

import logging
from datetime import datetime

log = logging.getLogger(__name__)

# ── Colors for sentiment ──
SENTIMENT_COLORS = {
    "POS": "#10b981",
    "NEG": "#ef4444",
    "NEU": "#6b7280",
}

SENTIMENT_ICONS = {
    "POS": "&#x1F7E2;",  # green circle
    "NEG": "&#x1F534;",  # red circle
    "NEU": "&#x26AA;",  # white circle
}


class ReportGenerator:
    def generate(
        self,
        tickets: list[dict],
        sentiment_summary: dict,
        wordcloud_b64: str,
        search_params: dict,
        generated_at: datetime,
    ) -> str:
        """Generate the full HTML report."""
        ticket_rows = self._build_ticket_rows(tickets)
        chart_data = self._build_chart_data(sentiment_summary)

        html = REPORT_TEMPLATE.format(
            generated_at=generated_at.strftime("%d/%m/%Y %H:%M"),
            fulltext=search_params.get("fulltext", ""),
            queues=", ".join(search_params.get("queues", [])),
            date_from=search_params.get("date_from", ""),
            date_to=search_params.get("date_to", ""),
            total=sentiment_summary.get("total", 0),
            positive=sentiment_summary.get("positive", 0),
            negative=sentiment_summary.get("negative", 0),
            neutral=sentiment_summary.get("neutral", 0),
            positive_pct=sentiment_summary.get("positive_pct", 0),
            negative_pct=sentiment_summary.get("negative_pct", 0),
            neutral_pct=sentiment_summary.get("neutral_pct", 0),
            wordcloud_b64=wordcloud_b64,
            ticket_rows=ticket_rows,
            chart_positive=sentiment_summary.get("positive", 0),
            chart_negative=sentiment_summary.get("negative", 0),
            chart_neutral=sentiment_summary.get("neutral", 0),
        )

        return html

    def _build_ticket_rows(self, tickets: list[dict]) -> str:
        rows = []
        for t in tickets:
            sentiment = t.get("sentiment", "NEU")
            color = SENTIMENT_COLORS.get(sentiment, "#6b7280")
            icon = SENTIMENT_ICONS.get(sentiment, "")
            label = t.get("sentiment_label", "Neutro")
            score = t.get("sentiment_score", 0)

            # Truncate body for preview
            body = t.get("first_article_body", "")
            preview = body[:200].replace("\n", " ").strip()
            if len(body) > 200:
                preview += "..."

            # Escape HTML
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

            row = f"""
            <tr class="ticket-row" data-sentiment="{sentiment}">
                <td class="cell-ticket">
                    <span class="ticket-number">{t.get('ticket_number', t.get('ticket_id', ''))}</span>
                </td>
                <td class="cell-title">{title}</td>
                <td class="cell-sentiment">
                    <span class="badge" style="--badge-color: {color}">
                        {icon} {label}
                    </span>
                </td>
                <td class="cell-score">
                    <div class="score-bar">
                        <div class="score-fill" style="width: {score*100:.0f}%; background: {color}"></div>
                    </div>
                    <span class="score-value">{score:.0%}</span>
                </td>
                <td class="cell-preview">{preview}</td>
            </tr>"""
            rows.append(row)
        return "\n".join(rows)

    def _build_chart_data(self, summary: dict) -> dict:
        return {
            "positive": summary.get("positive", 0),
            "negative": summary.get("negative", 0),
            "neutral": summary.get("neutral", 0),
        }


# ── HTML Template ──
REPORT_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Análisis de Sentimiento — Tickets OTRS</title>
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
    --accent-green: #10b981;
    --accent-red: #ef4444;
    --accent-gray: #6b7280;
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
    background: linear-gradient(90deg, var(--accent-blue), var(--accent-green));
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
  .stat-card.positive .stat-value {{ color: var(--accent-green); }}
  .stat-card.negative .stat-value {{ color: var(--accent-red); }}
  .stat-card.neutral .stat-value {{ color: var(--accent-gray); }}

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
    width: 80px;
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

  .tickets-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9rem;
  }}

  .tickets-table thead {{
    background: var(--bg-primary);
  }}

  .tickets-table th {{
    padding: 0.8rem 1rem;
    text-align: left;
    font-weight: 500;
    color: var(--text-muted);
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    white-space: nowrap;
  }}

  .tickets-table td {{
    padding: 0.7rem 1rem;
    border-top: 1px solid var(--border);
    vertical-align: top;
  }}

  .ticket-row:hover {{
    background: var(--bg-card-hover);
  }}

  .ticket-number {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.8rem;
    color: var(--accent-blue);
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
    .tickets-table {{ display: block; overflow-x: auto; }}
    .cell-preview {{ display: none; }}
  }}
</style>
</head>
<body>

<div class="container">

  <!-- Header -->
  <header class="header">
    <h1>Análisis de Sentimiento — OTRS</h1>
    <p class="subtitle">Reporte automático generado el {generated_at}</p>
    <div class="meta-bar">
      <span class="meta-item">Búsqueda: <strong>{fulltext}</strong></span>
      <span class="meta-item">Colas: <strong>{queues}</strong></span>
      <span class="meta-item">Período: <strong>{date_from} → {date_to}</strong></span>
    </div>
  </header>

  <!-- Stats -->
  <div class="stats-grid">
    <div class="stat-card total">
      <div class="stat-value">{total}</div>
      <div class="stat-label">Total tickets</div>
    </div>
    <div class="stat-card positive">
      <div class="stat-value">{positive}</div>
      <div class="stat-label">Positivos</div>
      <div class="stat-pct">{positive_pct}%</div>
    </div>
    <div class="stat-card negative">
      <div class="stat-value">{negative}</div>
      <div class="stat-label">Negativos</div>
      <div class="stat-pct">{negative_pct}%</div>
    </div>
    <div class="stat-card neutral">
      <div class="stat-value">{neutral}</div>
      <div class="stat-label">Neutros</div>
      <div class="stat-pct">{neutral_pct}%</div>
    </div>
  </div>

  <!-- Chart -->
  <div class="section">
    <h2 class="section-title">Distribución de Sentimiento</h2>
    <div class="chart-container">

      <div class="donut-chart">
        <svg viewBox="0 0 220 220" width="220" height="220">
          <circle cx="110" cy="110" r="90" fill="none" stroke="var(--bg-primary)" stroke-width="24"/>
          <circle id="arc-pos" cx="110" cy="110" r="90" fill="none"
            stroke="var(--accent-green)" stroke-width="24"
            stroke-dasharray="0 565.5"
            stroke-linecap="round"/>
          <circle id="arc-neg" cx="110" cy="110" r="90" fill="none"
            stroke="var(--accent-red)" stroke-width="24"
            stroke-dasharray="0 565.5"
            stroke-linecap="round"/>
          <circle id="arc-neu" cx="110" cy="110" r="90" fill="none"
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
          <span class="bar-label">Positivo</span>
          <div class="bar-track">
            <div class="bar-fill" style="width: {positive_pct}%; background: var(--accent-green);">
              {positive} ({positive_pct}%)
            </div>
          </div>
        </div>
        <div class="bar-row">
          <span class="bar-label">Negativo</span>
          <div class="bar-track">
            <div class="bar-fill" style="width: {negative_pct}%; background: var(--accent-red);">
              {negative} ({negative_pct}%)
            </div>
          </div>
        </div>
        <div class="bar-row">
          <span class="bar-label">Neutro</span>
          <div class="bar-track">
            <div class="bar-fill" style="width: {neutral_pct}%; background: var(--accent-gray);">
              {neutral} ({neutral_pct}%)
            </div>
          </div>
        </div>
      </div>

      <div class="chart-legend">
        <div class="legend-item">
          <div class="legend-dot" style="background: var(--accent-green)"></div>
          <span class="legend-label">Positivo</span>
          <span class="legend-value">{positive}</span>
        </div>
        <div class="legend-item">
          <div class="legend-dot" style="background: var(--accent-red)"></div>
          <span class="legend-label">Negativo</span>
          <span class="legend-value">{negative}</span>
        </div>
        <div class="legend-item">
          <div class="legend-dot" style="background: var(--accent-gray)"></div>
          <span class="legend-label">Neutro</span>
          <span class="legend-value">{neutral}</span>
        </div>
      </div>

    </div>
  </div>

  <!-- Word Cloud -->
  <div class="section">
    <h2 class="section-title">Nube de Palabras</h2>
    <div class="wordcloud-container">
      <img src="data:image/png;base64,{wordcloud_b64}" alt="Nube de palabras">
    </div>
  </div>

  <!-- Tickets Table -->
  <div class="section">
    <h2 class="section-title">Detalle por Ticket</h2>
    <div class="table-container">
      <div class="table-controls">
        <button class="filter-btn active" onclick="filterTickets('ALL')">Todos</button>
        <button class="filter-btn" onclick="filterTickets('POS')">&#x1F7E2; Positivos</button>
        <button class="filter-btn" onclick="filterTickets('NEG')">&#x1F534; Negativos</button>
        <button class="filter-btn" onclick="filterTickets('NEU')">&#x26AA; Neutros</button>
      </div>
      <table class="tickets-table">
        <thead>
          <tr>
            <th>Ticket #</th>
            <th>Título</th>
            <th>Sentimiento</th>
            <th>Confianza</th>
            <th>Extracto</th>
          </tr>
        </thead>
        <tbody id="tickets-body">
          {ticket_rows}
        </tbody>
      </table>
    </div>
  </div>

  <footer class="footer">
    Generado automáticamente el {generated_at} &mdash;
    Análisis de sentimiento con <a href="https://github.com/pysentimiento/pysentimiento">pysentimiento</a>
  </footer>

</div>

<script>
// ── Donut chart animation ──
(function() {{
  const total = {total} || 1;
  const pos = {chart_positive};
  const neg = {chart_negative};
  const neu = {chart_neutral};
  const C = 2 * Math.PI * 90; // circumference

  const posLen = (pos / total) * C;
  const negLen = (neg / total) * C;
  const neuLen = (neu / total) * C;

  const arcPos = document.getElementById('arc-pos');
  const arcNeg = document.getElementById('arc-neg');
  const arcNeu = document.getElementById('arc-neu');

  if (arcPos) {{
    arcPos.setAttribute('stroke-dasharray', posLen + ' ' + C);
    arcPos.setAttribute('stroke-dashoffset', '0');

    arcNeg.setAttribute('stroke-dasharray', negLen + ' ' + C);
    arcNeg.setAttribute('stroke-dashoffset', -posLen);

    arcNeu.setAttribute('stroke-dasharray', neuLen + ' ' + C);
    arcNeu.setAttribute('stroke-dashoffset', -(posLen + negLen));
  }}
}})();

// ── Filter tickets ──
function filterTickets(sentiment) {{
  const rows = document.querySelectorAll('.ticket-row');
  const btns = document.querySelectorAll('.filter-btn');

  btns.forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');

  rows.forEach(row => {{
    if (sentiment === 'ALL' || row.dataset.sentiment === sentiment) {{
      row.style.display = '';
    }} else {{
      row.style.display = 'none';
    }}
  }});
}}
</script>

</body>
</html>"""
