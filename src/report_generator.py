"""
Report Generator
================
Generates a polished HTML report with intent classification results,
charts, and word cloud visualization.
"""

import logging
from datetime import datetime

from src.analyzer import IntentClassifier, format_duration

log = logging.getLogger(__name__)

# ── Colors for intent ──
INTENT_COLORS = {
    "CONSULTA": "#00b894",
    "RECLAMO": "#e17055",
    "INDETERMINADO": "#636e72",
}

INTENT_ICONS = {
    "CONSULTA": "&#x2753;",      # question mark
    "RECLAMO": "&#x26A0;",       # warning sign
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
        topic_summary: dict = None,
        incognito_tickets: list = None,
        incognito_kpis: dict = None,
        incognito_timeline: dict = None,
        incognito_resolution: dict = None,
        baseline_resolution: dict = None,
    ) -> str:
        """Generate the full HTML report."""
        ticket_rows = self._build_ticket_rows(tickets)
        timeline_charts = self._build_timeline_charts(timeline_data or {})
        ngram_lists = self._build_ngram_lists(top_bigrams or [], top_trigrams or [])
        topic_section = self._build_topic_section(topic_summary or {})

        # Build topic filter buttons for ticket table
        topic_filters = self._build_topic_filter_buttons(topic_summary or {})

        # Incognito tab content
        incognito_kpi_cards = self._build_incognito_kpis(
            incognito_kpis or {}, intent_summary.get("total", 0)
        )
        incognito_resolution_block = self._build_incognito_resolution(
            incognito_resolution or {}, baseline_resolution or {}
        )
        incognito_timeline_chart = self._build_incognito_timeline_chart(
            incognito_timeline or {}
        )
        incognito_ticket_rows = self._build_incognito_ticket_rows(
            incognito_tickets or []
        )
        incognito_count = (incognito_kpis or {}).get("total", 0)

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
            topic_section=topic_section,
            topic_filters=topic_filters,
            incognito_count=incognito_count,
            incognito_tab_badge=f" ({incognito_count})" if incognito_count else "",
            incognito_kpi_cards=incognito_kpi_cards,
            incognito_resolution_block=incognito_resolution_block,
            incognito_timeline_chart=incognito_timeline_chart,
            incognito_ticket_rows=incognito_ticket_rows,
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

            # Topic badge
            topic_badge = ""
            primary_topic = t.get("primary_topic", "")
            topic_color = t.get("primary_topic_color", "#b2bec3")
            topic_id = t.get("primary_topic_id", "")
            if primary_topic and primary_topic != "N/A":
                topic_name_escaped = (
                    primary_topic.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                topic_badge = f' <span class="badge topic-badge" style="--badge-color: {topic_color}">{topic_name_escaped}</span>'

            row = f"""
            <div class="ticket-card" data-intent="{intent}" data-topic="{topic_id}">
                <div class="ticket-header" onclick="toggleBody('body-{idx}', this)">
                    <div class="ticket-meta-row">
                        <span class="ticket-number">{ticket_number}</span>
                        <span class="badge" style="--badge-color: {color}">{icon} {label}</span>{topic_badge}{staff_badge}
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

        def stacked_bars(entries, label_fn, max_val):
            bars = ""
            # `entries` already comes sorted DESC (newest first) from
            # IntentClassifier.get_timeline_data. Render in that same order so
            # the chart displays most recent → oldest top-down (matches the
            # user's "ordena de manera descendente" request).
            for entry in entries:
                total = entry.get("total", 0)
                pct_total = total / max_val * 100
                c = entry.get("consulta", 0)
                r = entry.get("reclamo", 0)
                ind = entry.get("indeterminado", 0)
                # Widths proportional to each category within the total bar width
                pct_c = (c / total * pct_total) if total else 0
                pct_r = (r / total * pct_total) if total else 0
                pct_i = (ind / total * pct_total) if total else 0
                bars += (
                    '<div class="timeline-bar-wrap">'
                    '<span class="timeline-label">%s</span>'
                    '<div class="timeline-bar">'
                    '<div class="timeline-bar-fill stacked-consulta" style="width:%.1f%%"></div>'
                    '<div class="timeline-bar-fill stacked-reclamo" style="width:%.1f%%"></div>'
                    '<div class="timeline-bar-fill stacked-indeterminado" style="width:%.1f%%"></div>'
                    '</div>'
                    '<span class="timeline-count">%d</span>'
                    '</div>' % (label_fn(entry), pct_c, pct_r, pct_i, total)
                )
            return bars

        max_day = max((d.get("total", 0) for d in by_day), default=1)
        day_bars = stacked_bars(by_day, lambda d: d["date"][5:], max_day)

        month_names = {"01":"Ene","02":"Feb","03":"Mar","04":"Abr","05":"May",
                       "06":"Jun","07":"Jul","08":"Ago","09":"Sep","10":"Oct",
                       "11":"Nov","12":"Dic"}
        max_month = max((m.get("total", 0) for m in by_month), default=1)
        month_bars = stacked_bars(
            by_month,
            lambda m: "%s %s" % (month_names.get(m["month"].split("-")[1], m["month"].split("-")[1]),
                                 m["month"].split("-")[0]),
            max_month,
        )

        return (
            '<div class="timeline-charts">'
            '<div class="timeline-chart">'
            '<h3 class="timeline-title">Tickets por D\u00eda</h3>'
            '<div class="stacked-legend">'
            '<span class="stacked-legend-item"><span class="stacked-dot" style="background:var(--accent-teal)"></span>Consulta</span>'
            '<span class="stacked-legend-item"><span class="stacked-dot" style="background:var(--accent-orange)"></span>Reclamo</span>'
            '<span class="stacked-legend-item"><span class="stacked-dot" style="background:var(--accent-gray)"></span>Indeterminado</span>'
            '</div>'
            '<div class="timeline-bars">%s</div></div>'
            '<div class="timeline-chart">'
            '<h3 class="timeline-title">Tickets por Mes</h3>'
            '<div class="stacked-legend">'
            '<span class="stacked-legend-item"><span class="stacked-dot" style="background:var(--accent-teal)"></span>Consulta</span>'
            '<span class="stacked-legend-item"><span class="stacked-dot" style="background:var(--accent-orange)"></span>Reclamo</span>'
            '<span class="stacked-legend-item"><span class="stacked-dot" style="background:var(--accent-gray)"></span>Indeterminado</span>'
            '</div>'
            '<div class="timeline-bars">%s</div></div>'
            '</div>' % (day_bars, month_bars)
        )

    def _build_topic_filter_buttons(self, topic_summary):
        """Build topic filter buttons for the ticket table."""
        topics = topic_summary.get("topics", [])
        if not topics:
            return ""
        buttons = []
        for t in topics:
            tid = t["id"]
            name = t["name"]
            if name.startswith("Otros:"):
                tid = "otros"
                name_short = "Otros"
            else:
                name_short = name.split("/")[0].strip()
            # Avoid duplicate "otros" buttons
            btn_html = (
                '<button class="filter-btn topic-filter-btn" '
                f'onclick="filterByTopic(\'{tid}\')">{name_short}</button>'
            )
            buttons.append(btn_html)

        # Deduplicate
        seen = set()
        unique = []
        for b in buttons:
            if b not in seen:
                seen.add(b)
                unique.append(b)

        return (
            '<span class="filter-separator">|</span>'
            '<button class="filter-btn topic-filter-btn active" '
            'onclick="filterByTopic(\'ALL\')">Todos los temas</button>'
            + "".join(unique)
        )

    def _build_topic_section(self, topic_summary):
        """Build the thematic classification section HTML."""
        topics = topic_summary.get("topics", [])
        total_classified = topic_summary.get("total_classified", 0)

        if not topics:
            return ""

        # Sort by total descending for the bar chart
        sorted_topics = sorted(topics, key=lambda x: -x["total"])
        max_total = sorted_topics[0]["total"] if sorted_topics else 1

        # ── Horizontal stacked bar chart ──
        bars_html = ""
        for t in sorted_topics:
            pct_total = t["total"] / max_total * 100
            pct_c = (t["consulta"] / t["total"] * pct_total) if t["total"] else 0
            pct_r = (t["reclamo"] / t["total"] * pct_total) if t["total"] else 0
            pct_i = (t["indeterminado"] / t["total"] * pct_total) if t["total"] else 0
            name = t["name"]
            if len(name) > 45:
                name = name[:42] + "..."
            bars_html += (
                '<div class="topic-bar-wrap">'
                '<span class="topic-bar-label">%s</span>'
                '<div class="topic-bar">'
                '<div class="topic-bar-fill" style="width:%.1f%%;background:var(--accent-teal)"></div>'
                '<div class="topic-bar-fill" style="width:%.1f%%;background:var(--accent-orange)"></div>'
                '<div class="topic-bar-fill" style="width:%.1f%%;background:var(--accent-gray)"></div>'
                '</div>'
                '<span class="topic-bar-count">%d</span>'
                '</div>' % (name, pct_c, pct_r, pct_i, t["total"])
            )

        # ── Summary table ──
        table_rows = ""
        for t in sorted_topics:
            pct = t.get("pct", 0)
            table_rows += (
                '<tr>'
                '<td><span class="topic-dot" style="background:%s"></span>%s</td>'
                '<td class="num">%d</td>'
                '<td class="num">%d</td>'
                '<td class="num">%d</td>'
                '<td class="num">%d</td>'
                '<td class="num">%.1f%%</td>'
                '</tr>' % (t["color"], t["name"], t["total"], t["consulta"], t["reclamo"], t["indeterminado"], pct)
            )

        # ── Donut chart for topics ──
        donut_arcs = ""
        circumference = 2 * 3.14159265 * 90
        offset = 0
        for t in sorted_topics:
            if t["total"] == 0:
                continue
            arc_len = (t["total"] / total_classified) * circumference if total_classified else 0
            donut_arcs += (
                '<circle cx="110" cy="110" r="90" fill="none" '
                'stroke="%s" stroke-width="24" '
                'stroke-dasharray="%.1f %.1f" '
                'stroke-dashoffset="%.1f"/>'
                % (t["color"], arc_len, circumference, -offset)
            )
            offset += arc_len

        return (
            # \u2500\u2500 Section 1: Donut + Table (clasificaci\u00f3n tem\u00e1tica) \u2500\u2500
            '<div class="section">'
            '<h2 class="section-title">Clasificaci\u00f3n Tem\u00e1tica</h2>'
            '<div class="topic-overview">'
            '<div class="donut-chart">'
            '<svg viewBox="0 0 220 220" width="220" height="220" style="transform:rotate(-90deg)">'
            '<circle cx="110" cy="110" r="90" fill="none" stroke="var(--bg-primary)" stroke-width="24"/>'
            '%s'
            '</svg>'
            '<div class="donut-center">'
            '<div class="big-num">%d</div>'
            '<div class="label">clasificados</div>'
            '</div></div>'
            '<div class="topic-table-container">'
            '<table class="topic-table">'
            '<thead><tr>'
            '<th>Tema</th><th>Total</th><th>Consultas</th><th>Reclamos</th><th>Indeterminados</th><th>%% del total</th>'
            '</tr></thead>'
            '<tbody>%s</tbody>'
            '</table></div>'
            '</div>'  # close topic-overview
            '</div>'  # close section 1
            # \u2500\u2500 Section 2: Bar chart (Distribuci\u00f3n Consulta/Reclamo por tema) \u2500\u2500
            '<div class="section">'
            '<h2 class="section-title">Distribuci\u00f3n por Tema (Consulta vs Reclamo)</h2>'
            '<div class="topic-bars-box">'
            '<div class="stacked-legend">'
            '<span class="stacked-legend-item"><span class="stacked-dot" style="background:var(--accent-teal)"></span>Consulta</span>'
            '<span class="stacked-legend-item"><span class="stacked-dot" style="background:var(--accent-orange)"></span>Reclamo</span>'
            '<span class="stacked-legend-item"><span class="stacked-dot" style="background:var(--accent-gray)"></span>Indeterminado</span>'
            '</div>'
            '%s'
            '</div>'
            '</div>'  # close section 2
            % (donut_arcs, total_classified, table_rows, bars_html)
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

    # ══════════════════════════════════════════════════════════════
    #  Incognito tab builders
    # ══════════════════════════════════════════════════════════════

    def _build_incognito_kpis(self, kpis, total_tickets):
        """4 KPI cards: total, % of all, avg per day, top queue."""
        total = kpis.get("total", 0)
        pct = kpis.get("pct_of_total", 0.0)
        avg = kpis.get("avg_per_day", 0.0)
        top_queue = kpis.get("top_queue", "—") or "—"
        top_queue_count = kpis.get("top_queue_count", 0)

        # Escape queue string
        top_queue_html = (
            top_queue.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )

        return (
            '<div class="stats-grid">'
            f'<div class="stat-card total"><div class="stat-value">{total}</div>'
            f'<div class="stat-label">Tickets con sugerencia</div></div>'
            f'<div class="stat-card consulta"><div class="stat-value">{pct}%</div>'
            f'<div class="stat-label">Del total analizado</div>'
            f'<div class="stat-pct">{total}/{total_tickets}</div></div>'
            f'<div class="stat-card reclamo"><div class="stat-value">{avg}</div>'
            f'<div class="stat-label">Promedio / día</div></div>'
            f'<div class="stat-card indeterminado"><div class="stat-value" style="font-size:1.3rem;line-height:1.4;">{top_queue_html}</div>'
            f'<div class="stat-label">Cola con más casos</div>'
            f'<div class="stat-pct">{top_queue_count} tickets</div></div>'
            '</div>'
        )

    def _build_incognito_resolution(self, inc_stats, baseline_stats):
        """Block showing median/mean/percentil-90."""
        count_used = inc_stats.get("count_used", 0)
        total = inc_stats.get("total", 0)

        if count_used == 0:
            return (
                '<div class="resolution-block">'
                '<p class="resolution-empty">No hay tickets cerrados todavía '
                'en este subconjunto — el tiempo de resolución se podrá calcular '
                'cuando el equipo los cierre.</p>'
                '</div>'
            )

        median_str = format_duration(inc_stats.get("median_s"))
        mean_str = format_duration(inc_stats.get("mean_s"))
        p90_str = format_duration(inc_stats.get("p90_s"))

        return (
            '<div class="resolution-block">'
            '<div class="resolution-stats">'
            f'<div class="resolution-stat"><span class="resolution-label">Mediana</span>'
            f'<span class="resolution-value">{median_str}</span></div>'
            f'<div class="resolution-stat"><span class="resolution-label">Promedio</span>'
            f'<span class="resolution-value">{mean_str}</span></div>'
            f'<div class="resolution-stat"><span class="resolution-label">Percentil 90</span>'
            f'<span class="resolution-value">{p90_str}</span></div>'
            '</div>'
            f'<p class="resolution-note">Basado en {count_used}/{total} tickets cerrados.</p>'
            '</div>'
        )

    def _build_incognito_timeline_chart(self, timeline_data):
        """Monthly (left) + daily (right) timeline charts side-by-side in a single
        .timeline-charts grid (so they share one PDF page)."""
        by_day = timeline_data.get("by_day", [])
        by_month = timeline_data.get("by_month", [])

        if not by_day and not by_month:
            return (
                '<div class="timeline-chart">'
                '<p class="resolution-empty">Sin tickets para graficar.</p>'
                '</div>'
            )

        month_names = {
            "01": "Ene", "02": "Feb", "03": "Mar", "04": "Abr",
            "05": "May", "06": "Jun", "07": "Jul", "08": "Ago",
            "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dic",
        }

        max_month = max((m["count"] for m in by_month), default=1)
        month_bars = ""
        for m in by_month:
            pct = m["count"] / max_month * 100
            parts = m["month"].split("-")
            label = "%s %s" % (month_names.get(parts[1], parts[1]), parts[0])
            month_bars += (
                '<div class="timeline-bar-wrap">'
                '<span class="timeline-label">%s</span>'
                '<div class="timeline-bar">'
                '<div class="timeline-bar-fill incognito-fill" style="width:%.0f%%"></div>'
                '</div>'
                '<span class="timeline-count">%d</span>'
                '</div>' % (label, pct, m["count"])
            )

        max_day = max((d["count"] for d in by_day), default=1)
        day_bars = ""
        for d in by_day:
            pct = d["count"] / max_day * 100
            short_date = d["date"][5:]
            day_bars += (
                '<div class="timeline-bar-wrap">'
                '<span class="timeline-label">%s</span>'
                '<div class="timeline-bar">'
                '<div class="timeline-bar-fill incognito-fill" style="width:%.0f%%"></div>'
                '</div>'
                '<span class="timeline-count">%d</span>'
                '</div>' % (short_date, pct, d["count"])
            )

        return (
            '<div class="timeline-charts">'
            '<div class="timeline-chart">'
            '<h3 class="timeline-title">Por mes</h3>'
            '<div class="timeline-bars">%s</div>'
            '</div>'
            '<div class="timeline-chart">'
            '<h3 class="timeline-title">Por día</h3>'
            '<div class="timeline-bars">%s</div>'
            '</div>'
            '</div>'
            % (month_bars, day_bars)
        )

    def _build_incognito_ticket_rows(self, tickets):
        """Ticket cards for incognito tab — shows excerpt of agent response."""
        if not tickets:
            return (
                '<div class="empty-state">'
                '<p>No se encontraron tickets en los que el agente haya sugerido '
                'modo incógnito / navegación privada en el período analizado.</p>'
                '</div>'
            )

        rows = []
        for idx, t in enumerate(tickets):
            intent = t.get("intent", "INDETERMINADO")
            color = INTENT_COLORS.get(intent, "#636e72")
            icon = INTENT_ICONS.get(intent, "")
            label = t.get("intent_label", "Indeterminado")

            excerpt = t.get("incognito_excerpt", "") or ""
            excerpt_html = (
                excerpt.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            )

            # Highlight the matching patterns in the excerpt
            for term in ("modo incógnito", "modo incognito",
                         "navegación privada", "navegacion privada",
                         "ventana privada", "incógnito", "incognito",
                         "InPrivate", "in private", "modo invitado"):
                # case-insensitive single replacement via regex would be cleaner,
                # but keep it simple with manual case variations
                for variant in (term, term.capitalize(), term.upper()):
                    if variant in excerpt_html:
                        excerpt_html = excerpt_html.replace(
                            variant, f'<mark class="inc-match">{variant}</mark>'
                        )

            agent_full = t.get("agent_responses", "") or ""
            agent_full_html = (
                agent_full.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("\n", "<br>")
            )

            title = (
                t.get("title", "")
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            ticket_number = t.get("ticket_number", t.get("ticket_id", ""))
            queue = (
                t.get("queue", "")
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            created = t.get("created", "")

            closed_at = t.get("closed_at")
            resolution_badge = ""
            if closed_at:
                c = IntentClassifier._parse_datetime(created)
                cl = IntentClassifier._parse_datetime(closed_at)
                if c and cl and cl > c:
                    dur = format_duration((cl - c).total_seconds())
                    resolution_badge = (
                        f' <span class="badge resolution-badge">Resuelto en {dur}</span>'
                    )
                else:
                    resolution_badge = ' <span class="badge resolution-badge">Cerrado</span>'

            row = f"""
            <div class="ticket-card incognito-card">
                <div class="ticket-header" onclick="toggleBody('inc-body-{idx}', this)">
                    <div class="ticket-meta-row">
                        <span class="ticket-number">{ticket_number}</span>
                        <span class="badge" style="--badge-color: {color}">{icon} {label}</span>{resolution_badge}
                        <span class="ticket-queue">{queue}</span>
                        <span class="ticket-date">{created}</span>
                        <span class="expand-icon">&#x25BC;</span>
                    </div>
                    <div class="ticket-title">{title}</div>
                    <div class="ticket-preview inc-excerpt">&#x1F4AC; {excerpt_html}</div>
                </div>
                <div class="ticket-body" id="inc-body-{idx}">
                    <div class="ticket-from"><strong>Respuesta completa del agente:</strong></div>
                    <div class="ticket-body-text">{agent_full_html}</div>
                </div>
            </div>"""
            rows.append(row)
        return "\n".join(rows)


# ── HTML Template ──
REPORT_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Clasificaci\u00f3n de Tickets por Intenci\u00f3n — OTRS</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,wght@0,400;0,500;0,700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/html2pdf.js@0.10.2/dist/html2pdf.bundle.min.js"></script>
<!-- html2pdf bundles html2canvas+jsPDF internally pero no los re-exporta; los cargamos
     standalone para usarlos directo desde generarPDF() (captura por sección). -->
<script src="https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/jspdf@2.5.1/dist/jspdf.umd.min.js"></script>
<style>
  /* Tema CLARO (default) */
  :root {{
    --bg-primary: #f5f6fa;
    --bg-secondary: #ffffff;
    --bg-card: #ffffff;
    --bg-card-hover: #f0f2f7;
    --text-primary: #1a1d27;
    --text-secondary: #4b5563;
    --text-muted: #6b7280;
    --accent-teal: #0d9f6e;
    --accent-orange: #d97706;
    --accent-gray: #6b7280;
    --accent-blue: #4f6ef0;
    --border: #dfe3ec;
    --radius: 12px;
    --color-scheme: light;
    --header-grad-from: #1a1d27;
    --header-grad-to: #4f6ef0;
    --inc-match-bg: rgba(124, 58, 237, 0.18);
    --inc-match-fg: #6d28d9;
  }}

  /* Tema OSCURO */
  [data-theme="dark"] {{
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
    --color-scheme: dark;
    --header-grad-from: #e2e8f0;
    --header-grad-to: #94a3b8;
    --inc-match-bg: rgba(168, 85, 247, 0.25);
    --inc-match-fg: #d8b4fe;
  }}

  html {{ color-scheme: var(--color-scheme); }}

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

  /* ── Header actions (theme toggle + PDF) ── */
  .header-actions {{
    position: absolute;
    top: 1rem;
    right: 0;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    align-items: flex-end;
    z-index: 10;
  }}
  .theme-toggle {{
    background: var(--bg-card);
    color: var(--text-primary);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 0.5rem 0.9rem;
    cursor: pointer;
    font-family: inherit;
    font-size: 0.85rem;
    font-weight: 500;
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    transition: background 0.2s, color 0.2s, border-color 0.2s;
    white-space: nowrap;
  }}
  .theme-toggle:hover {{
    color: var(--accent-blue);
    border-color: var(--accent-blue);
  }}
  .theme-toggle .theme-icon {{ font-size: 1rem; }}
  @media (max-width: 768px) {{
    .header-actions {{ position: static; flex-direction: row; justify-content: center; margin-bottom: 1rem; }}
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
    background: linear-gradient(135deg, var(--header-grad-from), var(--header-grad-to));
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
    width: 280px;
    height: 280px;
    flex-shrink: 0;
  }}

  .donut-chart svg {{
    width: 280px;
    height: 280px;
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
    width: 170px;
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
    display: flex;
  }}

  .timeline-bar-fill {{
    height: 100%;
    transition: width 0.6s ease;
    min-width: 0;
  }}
  .timeline-bar-fill.stacked-consulta {{ background: var(--accent-teal); }}
  .timeline-bar-fill.stacked-reclamo {{ background: var(--accent-orange); }}
  .timeline-bar-fill.stacked-indeterminado {{ background: var(--accent-gray); }}
  .timeline-bar-fill:first-child {{ border-radius: 4px 0 0 4px; }}
  .timeline-bar-fill:last-child {{ border-radius: 0 4px 4px 0; }}
  .timeline-bar-fill:only-child {{ border-radius: 4px; }}

  .stacked-legend {{
    display: flex; gap: 16px; margin-bottom: 8px; font-size: 0.75rem;
    color: var(--text-secondary);
  }}
  .stacked-legend-item {{ display: flex; align-items: center; gap: 4px; }}
  .stacked-dot {{
    width: 10px; height: 10px; border-radius: 50%; display: inline-block;
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

  /* ── Topic Section ── */
  .topic-overview {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 2rem;
    display: grid;
    grid-template-columns: 280px 1fr;
    align-items: center;
    gap: 2rem;
    margin-bottom: 1.5rem;
  }}

  .topic-overview .topic-table-container {{
    margin-bottom: 0;
    border: none;
    border-radius: 0;
    overflow: auto;
  }}

  @media (max-width: 900px) {{
    .topic-overview {{
      grid-template-columns: 1fr;
      justify-items: center;
    }}
  }}

  .topic-bars-box {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 2rem;
  }}

  .topic-bar-wrap {{
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin-bottom: 0.45rem;
  }}

  .topic-bar-label {{
    font-size: 0.82rem;
    color: var(--text-secondary);
    width: 280px;
    text-align: right;
    flex-shrink: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}

  .topic-bar {{
    flex: 1;
    min-width: 120px;
    height: 24px;
    background: var(--bg-primary);
    border-radius: 4px;
    overflow: hidden;
    display: flex;
  }}

  .topic-bar-fill {{
    height: 100%;
    min-width: 0;
    transition: width 0.6s ease;
  }}

  .topic-bar-fill:first-child {{ border-radius: 4px 0 0 4px; }}
  .topic-bar-fill:last-child {{ border-radius: 0 4px 4px 0; }}
  .topic-bar-fill:only-child {{ border-radius: 4px; }}

  .topic-bar-count {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.82rem;
    color: var(--text-secondary);
    width: 32px;
    flex-shrink: 0;
  }}

  .topic-table-container {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
    margin-bottom: 1.5rem;
  }}

  .topic-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
  }}

  .topic-table th {{
    background: var(--bg-secondary);
    color: var(--text-secondary);
    padding: 0.7rem 1rem;
    text-align: left;
    font-weight: 500;
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    border-bottom: 1px solid var(--border);
  }}

  .topic-table td {{
    padding: 0.6rem 1rem;
    border-bottom: 1px solid var(--border);
    color: var(--text-primary);
  }}

  .topic-table td.num {{
    font-family: 'JetBrains Mono', monospace;
    text-align: center;
    color: var(--text-secondary);
  }}

  .topic-table tr:hover {{
    background: var(--bg-card-hover);
  }}

  .topic-dot {{
    display: inline-block;
    width: 14px;
    height: 14px;
    border-radius: 4px;
    margin-right: 10px;
    vertical-align: middle;
  }}

  .topic-badge {{
    font-size: 0.7rem;
    padding: 0.15rem 0.5rem;
  }}

  .filter-separator {{
    color: var(--text-muted);
    margin: 0 0.3rem;
    display: inline-flex;
    align-items: center;
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

  /* ── Tabs ── */
  .tabs {{
    display: flex;
    gap: 0.5rem;
    border-bottom: 1px solid var(--border);
    margin: 1.5rem 0 0;
    flex-wrap: wrap;
  }}

  .tab {{
    font-family: 'DM Sans', sans-serif;
    font-size: 0.95rem;
    font-weight: 500;
    padding: 0.7rem 1.3rem;
    border: 1px solid transparent;
    border-bottom: none;
    border-radius: 8px 8px 0 0;
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
    transition: all 0.2s;
    margin-bottom: -1px;
  }}

  .tab:hover {{
    color: var(--text-secondary);
    background: var(--bg-card);
  }}

  .tab.active {{
    color: var(--text-primary);
    background: var(--bg-card);
    border-color: var(--border);
    border-bottom-color: var(--bg-card);
  }}

  .tab-panel {{
    display: none;
    animation: fadeIn 0.4s ease both;
  }}

  .tab-panel.active {{
    display: block;
  }}

  /* ── Incognito tab ── */
  .incognito-intro {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.2rem 1.5rem;
    margin: 1.5rem 0 0.5rem;
    font-size: 0.9rem;
    color: var(--text-secondary);
    line-height: 1.5;
  }}

  .incognito-intro strong {{
    color: var(--text-primary);
  }}

  .timeline-bar-fill.incognito-fill {{
    background: linear-gradient(90deg, #a855f7, #6366f1);
  }}

  .resolution-block {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.5rem;
    margin-bottom: 1rem;
  }}

  .resolution-title {{
    font-size: 1rem;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 1rem;
  }}

  .resolution-stats {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1rem;
    margin-bottom: 0.8rem;
  }}

  @media (max-width: 600px) {{
    .resolution-stats {{ grid-template-columns: 1fr; }}
  }}

  .resolution-stat {{
    background: var(--bg-primary);
    border-radius: 8px;
    padding: 0.9rem 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
  }}

  .resolution-label {{
    font-size: 0.72rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }}

  .resolution-value {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 1.4rem;
    font-weight: 700;
    color: #a855f7;
  }}

  .resolution-note {{
    font-size: 0.8rem;
    color: var(--text-muted);
  }}

  .resolution-baseline {{
    font-size: 0.85rem;
    color: var(--text-secondary);
    margin-top: 0.5rem;
    padding-top: 0.8rem;
    border-top: 1px solid var(--border);
  }}

  .resolution-empty {{
    font-size: 0.85rem;
    color: var(--text-muted);
    font-style: italic;
  }}

  .inc-excerpt {{
    color: var(--text-secondary) !important;
    font-size: 0.85rem !important;
  }}

  mark.inc-match {{
    background: var(--inc-match-bg);
    color: var(--inc-match-fg);
    padding: 0.05rem 0.3rem;
    border-radius: 3px;
    font-weight: 600;
  }}

  .resolution-badge {{
    --badge-color: #a855f7;
    font-size: 0.7rem;
    padding: 0.15rem 0.5rem;
  }}

  .empty-state {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 2rem;
    text-align: center;
    color: var(--text-muted);
    font-size: 0.9rem;
  }}
</style>
</head>
<body>

<div class="container">

  <!-- Header -->
  <header class="header">
    <div class="header-actions">
      <button id="pdf-download" class="theme-toggle" type="button" aria-label="Descargar PDF" title="Descargar PDF (KPIs y gráficos)">
        <span class="theme-icon">&#x1F4C4;</span> Descargar PDF
      </button>
      <button id="theme-toggle" class="theme-toggle" type="button" aria-label="Cambiar tema" title="Cambiar tema"></button>
    </div>
    <h1>Clasificaci\u00f3n de Tickets por Intenci\u00f3n — OTRS</h1>
    <p class="subtitle">Reporte autom\u00e1tico generado el {generated_at}</p>
    <div class="meta-bar">
      <span class="meta-item">B\u00fasqueda: <strong>{fulltext}</strong></span>
      <span class="meta-item">Colas: <strong>{queues}</strong></span>
      <span class="meta-item">Per\u00edodo: <strong>{date_from} \u2192 {date_to}</strong></span>
    </div>
  </header>

  <!-- Tabs nav -->
  <div class="tabs" role="tablist">
    <button class="tab active" data-tab="general" onclick="switchTab(event, 'general')">&#x1F4CA; An\u00e1lisis General</button>
    <button class="tab" data-tab="incognito" onclick="switchTab(event, 'incognito')">&#x1F575;&#xFE0F; Modo Inc\u00f3gnito{incognito_tab_badge}</button>
  </div>

  <!-- Tab panel: General -->
  <div id="tab-general" class="tab-panel active">

  <!-- Stats -->
  <div class="stats-grid">
    <div class="stat-card total">
      <div class="stat-value">{total}</div>
      <div class="stat-label">Total analizados</div>
      <div class="stat-pct">total</div>
    </div>
    <div class="stat-card consulta">
      <div class="stat-value">{consulta}</div>
      <div class="stat-label">Consulta / Duda / Solicitud</div>
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
          <span class="bar-label">Consulta/Duda/Solicitud</span>
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
          <span class="legend-label">Consulta/Duda/Solicitud</span>
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

  <!-- Topic Classification -->
  {topic_section}

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
  </div>

  <!-- N-gram lists (separate section so it gets its own page in PDF) -->
  <div class="section">
    <h2 class="section-title">Términos más Frecuentes</h2>
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
        {topic_filters}
        <button class="filter-btn" onclick="expandAll('general', true)" style="margin-left: auto;">Expandir todos</button>
        <button class="filter-btn" onclick="expandAll('general', false)">Colapsar todos</button>
      </div>
      <div id="tickets-body">
        {ticket_rows}
      </div>
    </div>
  </div>

  </div><!-- /tab-general -->

  <!-- Tab panel: Incognito -->
  <div id="tab-incognito" class="tab-panel">

    <!-- KPIs + Tiempo de resoluci\u00f3n unidos en una misma section para PDF -->
    <div class="section">
      <h2 class="section-title" id="pdf-modo-incognito-title">Modo Inc\u00f3gnito</h2>
      {incognito_kpi_cards}
      <h2 class="section-title" style="margin-top:1.5rem">Tiempo de resoluci\u00f3n</h2>
      {incognito_resolution_block}
    </div>

    <div class="section">
      <h2 class="section-title">Tickets por d\u00eda</h2>
      {incognito_timeline_chart}
    </div>

    <div class="section">
      <h2 class="section-title">Listado de tickets ({incognito_count})</h2>
      <div class="table-container">
        <div class="table-controls">
          <button class="filter-btn" onclick="expandAll('incognito', true)" style="margin-left: auto;">Expandir todos</button>
          <button class="filter-btn" onclick="expandAll('incognito', false)">Colapsar todos</button>
        </div>
        <div id="incognito-tickets-body">
          {incognito_ticket_rows}
        </div>
      </div>
    </div>

  </div><!-- /tab-incognito -->

  <footer class="footer">
    Generado autom\u00e1ticamente el {generated_at} &mdash;
    Clasificaci\u00f3n por intenci\u00f3n basada en patrones de keywords
  </footer>

</div>

<script>
// ── Donut chart animation (named so the theme toggle can re-trigger it) ──
window.__redrawDonut = function() {{
  const total = {total} || 1;
  const consulta = {chart_consulta};
  const reclamo = {chart_reclamo};
  const indeterminado = {chart_indeterminado};
  const C = 2 * Math.PI * 90; // circumference

  const consultaLen     = (consulta     / total) * C;
  const reclamoLen      = (reclamo      / total) * C;
  const indeterminadoLen= (indeterminado/ total) * C;

  const arcConsulta      = document.getElementById('arc-consulta');
  const arcReclamo       = document.getElementById('arc-reclamo');
  const arcIndeterminado = document.getElementById('arc-indeterminado');

  if (arcConsulta) {{
    arcConsulta.setAttribute('stroke-dasharray', consultaLen + ' ' + C);
    arcConsulta.setAttribute('stroke-dashoffset', '0');

    arcReclamo.setAttribute('stroke-dasharray', reclamoLen + ' ' + C);
    arcReclamo.setAttribute('stroke-dashoffset', -consultaLen);

    arcIndeterminado.setAttribute('stroke-dasharray', indeterminadoLen + ' ' + C);
    arcIndeterminado.setAttribute('stroke-dashoffset', -(consultaLen + reclamoLen));
  }}
}};
window.__redrawDonut();

// ── Tab switching ──
function switchTab(ev, name) {{
  document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  if (ev && ev.currentTarget) ev.currentTarget.classList.add('active');
  const panel = document.getElementById('tab-' + name);
  if (panel) panel.classList.add('active');
}}

// ── Filter state (general tab) ──
let currentIntentFilter = 'ALL';
let currentTopicFilter = 'ALL';

function applyFilters() {{
  // Scope to the general tab so the incognito tab's cards are never affected.
  const scope = document.getElementById('tab-general');
  if (!scope) return;
  const cards = scope.querySelectorAll('.ticket-card');
  cards.forEach(card => {{
    const intentMatch = currentIntentFilter === 'ALL' || card.dataset.intent === currentIntentFilter;
    const topicMatch = currentTopicFilter === 'ALL' || card.dataset.topic === currentTopicFilter;
    card.style.display = (intentMatch && topicMatch) ? '' : 'none';
  }});
}}

// ── Filter by intent ──
function filterTickets(intent) {{
  currentIntentFilter = intent;
  // Update intent button states (scoped to general tab)
  const scope = document.getElementById('tab-general');
  if (scope) {{
    scope.querySelectorAll('.filter-btn:not(.topic-filter-btn)').forEach(b => {{
      if (b.textContent.includes('Expandir') || b.textContent.includes('Colapsar')) return;
      b.classList.remove('active');
    }});
  }}
  event.target.classList.add('active');
  applyFilters();
}}

// ── Filter by topic ──
function filterByTopic(topicId) {{
  currentTopicFilter = topicId;
  document.querySelectorAll('.topic-filter-btn').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
  applyFilters();
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

function expandAll(tabName, expand) {{
  const scope = document.getElementById('tab-' + tabName);
  if (!scope) return;
  scope.querySelectorAll('.ticket-body').forEach(b => {{
    if (expand) b.classList.add('visible');
    else b.classList.remove('visible');
  }});
  scope.querySelectorAll('.ticket-header').forEach(h => {{
    if (expand) h.classList.add('expanded');
    else h.classList.remove('expanded');
  }});
}}

/* ── TOGGLE DE TEMA (claro / oscuro) ── */
const THEME_KEY = 'otrs_report_theme';
const themeBtn = document.getElementById('theme-toggle');

function applyTheme(theme) {{
  const t = (theme === 'dark') ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', t);
  if (themeBtn) {{
    themeBtn.innerHTML = (t === 'dark')
      ? '<span class="theme-icon">☀️</span> Modo claro'
      : '<span class="theme-icon">🌙</span> Modo oscuro';
    themeBtn.title = (t === 'dark') ? 'Cambiar a tema claro' : 'Cambiar a tema oscuro';
  }}
  try {{ localStorage.setItem(THEME_KEY, t); }} catch (_) {{}}
  // Re-trigger donut animation so colors take effect (its arcs read CSS vars on render)
  if (typeof window.__redrawDonut === 'function') window.__redrawDonut();
}}

let savedTheme = 'light';
try {{ savedTheme = localStorage.getItem(THEME_KEY) || 'light'; }} catch (_) {{}}
applyTheme(savedTheme);

if (themeBtn) {{
  themeBtn.addEventListener('click', () => {{
    const current = document.documentElement.getAttribute('data-theme') || 'light';
    applyTheme(current === 'dark' ? 'light' : 'dark');
  }});
}}

/* ── DESCARGA DE PDF (html2canvas + jsPDF directo) ──
   Approach: forzar tema claro, mostrar todas las pestañas, ocultar UI no
   relevante, capturar cada .section como una imagen independiente y armar el
   PDF con jsPDF, una sección por página A4-landscape centrada. Evita el
   slicing de canvas de html2pdf que produce whitespace al borde de página. */
const pdfBtn = document.getElementById('pdf-download');
if (pdfBtn) {{
  pdfBtn.addEventListener('click', () => {{
    if (typeof html2canvas === 'undefined' || (typeof window.jspdf === 'undefined' && typeof window.jsPDF === 'undefined')) {{
      alert('html2canvas / jsPDF no cargaron. Revisá tu conexión a internet.');
      return;
    }}
    generarPDF();
  }});
}}

async function generarPDF() {{
  const labelOriginal = pdfBtn.innerHTML;
  pdfBtn.disabled = true;
  pdfBtn.innerHTML = '<span class="theme-icon">⏳</span> Generando…';

  // Overlay
  const overlay = document.createElement('div');
  overlay.style.cssText = (
    'position:fixed; inset:0; background:rgba(15,17,23,0.85); ' +
    'z-index:99999; display:flex; align-items:center; justify-content:center; ' +
    'color:white; font-family:DM Sans,sans-serif; font-size:1.1rem;'
  );
  overlay.innerHTML = '<div style="text-align:center"><div style="font-size:2rem;margin-bottom:.5rem">📄</div>Generando PDF…</div>';
  document.body.appendChild(overlay);

  // Forzar tema claro
  const prevTheme = document.documentElement.getAttribute('data-theme') || 'light';
  if (prevTheme !== 'light') document.documentElement.setAttribute('data-theme', 'light');

  const restore = [];

  // 1. Container a 1000px
  const container = document.querySelector('.container');
  if (container) {{
    const o = {{ maxWidth: container.style.maxWidth, width: container.style.width, padding: container.style.padding, margin: container.style.margin }};
    restore.push(() => {{ Object.assign(container.style, o); }});
    container.style.maxWidth = '1000px';
    container.style.width = '1000px';
    container.style.padding = '0';
    container.style.margin = '0';
  }}
  const obp = document.body.style.padding;
  restore.push(() => {{ document.body.style.padding = obp; }});
  document.body.style.padding = '0';

  // 2. CSS injection: page-break rules + compact tables
  const pdfStyle = document.createElement('style');
  pdfStyle.id = 'pdf-page-break-rules';
  pdfStyle.textContent = (
    // Disable animations/transitions: html2canvas catches mid-fadeIn and content looks washed out
    '*, *::before, *::after {{ animation: none !important; animation-delay: 0s !important; animation-duration: 0s !important; transition: none !important; opacity: 1 !important; }}' +
    // Disable the donut SVG rotation (-90deg) which html2canvas can't render correctly with stroke-dasharray
    '.donut-chart svg, .topic-overview svg {{ transform: none !important; }}' +
    // The h1 uses -webkit-background-clip: text; html2canvas renders it as a gradient banner. Flatten.
    '.header h1 {{ background: none !important; -webkit-text-fill-color: #1a1d27 !important; color: #1a1d27 !important; }}' +
    // Each section must not split across pages. We rely only on
    // page-break-inside: avoid; forcing page-break-before: always creates
    // ugly artifacts (title alone at page bottom) when content doesn't fit.
    '.section, .stats-grid {{ page-break-inside: avoid !important; break-inside: avoid !important; margin: 0 !important; }}' +
    // Force each .section onto its own page (except the first stats-grid that
    // shares page 1 with the header).
    '.section {{ page-break-before: always !important; break-before: page !important; }}' +
    // The very first .section (Distribución por Intención) sits on page 2;
    // explicitly avoid break before it would still put it on page 2 anyway.
    // Force each .section to take a full A4 landscape page so titles never end up
    // orphaned at the bottom of the previous page (html2pdf splits any section
    // taller than one page; making sections at least one page tall + page-break-before
    // = clean one-section-per-page layout regardless of inner content height).
    // Inner blocks: never split
    '.chart-container, .timeline-charts, .ngram-lists, .timeline-chart, .ngram-list, .resolution-block, .wordcloud-container {{ page-break-inside: avoid !important; break-inside: avoid !important; }}' +
    'tr, thead {{ page-break-inside: avoid !important; break-inside: avoid !important; }}' +
    '.stat-card, .timeline-bar-wrap, .ngram-item {{ break-inside: avoid !important; }}' +
    // Compact timeline charts (cap max-height so the section fits one page)
    '.timeline-bars {{ max-height: 600px !important; overflow: hidden !important; }}' +
    '.timeline-bar-wrap {{ height: 18px !important; }}' +
    '.timeline-bar {{ height: 14px !important; }}' +
    '.timeline-label, .timeline-count {{ font-size: 0.65rem !important; }}' +
    // Compact wordcloud (cap height + smaller ngram lists)
    '.wordcloud-container img {{ max-height: 320px !important; width: auto !important; max-width: 100% !important; height: auto !important; }}' +
    '.wordcloud-container {{ padding: 0.6rem !important; }}' +
    '.ngram-lists {{ gap: 0.8rem !important; margin-top: 0.6rem !important; }}' +
    '.ngram-list {{ padding: 0.6rem !important; }}' +
    '.ngram-title {{ font-size: 0.85rem !important; margin-bottom: 0.4rem !important; }}' +
    '.ngram-item {{ margin-bottom: 0.15rem !important; gap: 0.3rem !important; }}' +
    '.ngram-rank, .ngram-term, .ngram-count {{ font-size: 0.7rem !important; }}' +
    '.ngram-bar {{ height: 8px !important; }}' +
    // Compact topic section table + donut so all 3 sub-blocks fit one page
    '.topic-table {{ font-size: 0.7rem !important; }}' +
    '.topic-table td, .topic-table th {{ padding: 0.25rem 0.4rem !important; line-height: 1.2 !important; }}' +
    '.topic-overview {{ gap: 1rem !important; }}' +
    '.topic-overview .donut-chart {{ width: 140px !important; height: 140px !important; flex-shrink: 0 !important; }}' +
    '.topic-overview .donut-chart svg {{ width: 140px !important; height: 140px !important; }}' +
    '.topic-overview .donut-center .big-num {{ font-size: 1.3rem !important; }}' +
    '.topic-overview .donut-center .label {{ font-size: 0.65rem !important; }}' +
    // Force grid items to shrink (otherwise long labels expand cards beyond 1fr)
    '.stats-grid {{ grid-template-columns: repeat(4, 1fr) !important; gap: 0.7rem !important; }}' +
    '.stat-card {{ min-width: 0 !important; padding: 1rem !important; }}' +
    '.stat-card .stat-value {{ font-size: 1.9rem !important; }}' +
    '.stat-card .stat-label {{ font-size: 0.7rem !important; }}' +
    '.topic-overview {{ gap: 1rem !important; }}' +
    '.topic-bar-wrap {{ height: 18px !important; margin-bottom: 0.15rem !important; }}' +
    '.topic-bar {{ height: 14px !important; }}' +
    '.topic-bar-label {{ font-size: 0.7rem !important; }}' +
    // Smaller section padding
    '.section, .chart-container, .timeline-chart, .ngram-list, .resolution-block, .wordcloud-container {{ padding: 0.8rem !important; }}' +
    '.section-title {{ font-size: 1.05rem !important; padding-bottom: 0.3rem !important; margin-bottom: 0.6rem !important; }}' +
    // Reduce timeline-chart card padding so daily/monthly charts stick close to the top
    '.timeline-chart {{ padding: 0.4rem !important; }}' +
    '.timeline-chart .timeline-bars {{ padding-top: 0 !important; padding-bottom: 0 !important; }}' +
    // Tighten incognito KPI grid so KPIs+resolution share top of page
    '.tab-panel#tab-incognito .stats-grid {{ margin: 0 !important; }}' +
    // Page 8 hero title: bigger + centered (just below the main h1 size)
    '#pdf-modo-incognito-title {{ font-size: 1.8rem !important; text-align: center !important; border-bottom: none !important; padding-bottom: 0 !important; margin-bottom: 1.2rem !important; letter-spacing: -0.02em !important; }}'
  );
  document.head.appendChild(pdfStyle);
  restore.push(() => pdfStyle.remove());

  // 3. Mostrar AMBAS pestañas (general + incógnito) consecutivas
  document.querySelectorAll('.tab-panel').forEach(p => {{
    const o = p.style.display;
    restore.push(() => {{ p.style.display = o; }});
    p.style.display = 'block';
  }});

  // 4. Ocultar UI no relevante: tabs nav, filtros, listados densos, footer
  const hide = [
    '.tabs',
    '.table-controls',
    '#tickets-body',
    '#incognito-tickets-body',
    '#pdf-download',
    '#theme-toggle',
    '.container > footer', 'body > footer',
  ];
  hide.forEach(sel => document.querySelectorAll(sel).forEach(el => {{
    const o = el.style.display;
    restore.push(() => {{ el.style.display = o; }});
    el.style.display = 'none';
  }}));

  // 5. Remover completamente del DOM las sections con listados de tickets
  //    (display:none no alcanza: html2pdf igual respeta el page-break-before y
  //    crea una página blanca por cada section hidden).
  ['#tickets-body', '#incognito-tickets-body'].forEach(sel => {{
    const body = document.querySelector(sel);
    if (!body) return;
    const section = body.closest('.section');
    if (!section) return;
    const placeholder = document.createComment('hidden-section-pdf');
    section.parentNode.replaceChild(placeholder, section);
    restore.push(() => {{ placeholder.parentNode.replaceChild(section, placeholder); }});
  }});


  // 6a. Trim timeline-bars to the most recent N entries so each timeline card
  //     fits on one A4 landscape page. CSS max-height + overflow hidden doesn't
  //     help because html2canvas captures the full content.
  document.querySelectorAll('.timeline-bars').forEach(bars => {{
    const wraps = bars.querySelectorAll('.timeline-bar-wrap');
    const N = 22; // bump from 13: per-section capture scales the image to fit so we can fit more rows before the height becomes the limiting dimension
    if (wraps.length > N) {{
      const hide = wraps.length - N;
      // Bars are sorted DESC (newest first) so hide the OLDEST = end of list
      for (let i = wraps.length - hide; i < wraps.length; i++) {{
        const o = wraps[i].style.display;
        restore.push(() => {{ wraps[i].style.display = o; }});
        wraps[i].style.display = 'none';
      }}
    }}
  }});

  // 6b. Re-render donut con colores del tema actual (claro)
  await new Promise(r => setTimeout(r, 100));
  if (typeof window.__redrawDonut === 'function') window.__redrawDonut();

  // 7. Esperar que el browser layout-render
  await new Promise(r => setTimeout(r, 500));

  // Per-section capture: avoid html2pdf's canvas-slicing artifacts (orphan whitespace
  // at top/bottom of pages where sections don't fill the A4 area). Each .section is
  // captured as one image and centered on its own A4-landscape page.
  const tempWrappers = [];
  try {{
    const headerEl = document.querySelector('header.header');
    const firstStatsGrid = document.querySelector('#tab-general .stats-grid')
      || document.querySelector('.stats-grid');

    const createTempWrapper = (elements) => {{
      const wrapper = document.createElement('div');
      wrapper.style.cssText = (
        'position:absolute; left:-99999px; top:0; width:1000px; ' +
        'background:#ffffff; padding:0; margin:0;'
      );
      elements.forEach(el => {{ if (el) wrapper.appendChild(el.cloneNode(true)); }});
      document.body.appendChild(wrapper);
      tempWrappers.push(wrapper);
      return wrapper;
    }};

    const pageGroups = [];
    if (headerEl || firstStatsGrid) {{
      pageGroups.push({{ wrapper: createTempWrapper([headerEl, firstStatsGrid]) }});
    }}
    document.querySelectorAll('.section').forEach(s => {{ pageGroups.push({{ el: s }}); }});

    const jsPDFCtor = (window.jspdf && window.jspdf.jsPDF) || window.jsPDF;
    const pdf = new jsPDFCtor({{ unit: 'mm', format: 'a4', orientation: 'landscape' }});
    const pageW = 297, pageH = 210;
    const margin = 10;
    const usableW = pageW - 2 * margin; // 277mm
    const usableH = pageH - 2 * margin; // 190mm

    for (let i = 0; i < pageGroups.length; i++) {{
      const target = pageGroups[i].wrapper || pageGroups[i].el;
      const canvas = await html2canvas(target, {{
        scale: 2, useCORS: true, backgroundColor: '#ffffff',
        logging: false, scrollX: 0, scrollY: 0,
        windowWidth: 1000, width: 1000,
      }});
      const imgData = canvas.toDataURL('image/jpeg', 0.95);
      const imgRatio = canvas.width / canvas.height;
      let imgW_mm = usableW;
      let imgH_mm = imgW_mm / imgRatio;
      if (imgH_mm > usableH) {{
        imgH_mm = usableH;
        imgW_mm = imgH_mm * imgRatio;
      }}
      const x_mm = (pageW - imgW_mm) / 2;
      const y_mm = (pageH - imgH_mm) / 2;
      if (i > 0) pdf.addPage();
      pdf.addImage(imgData, 'JPEG', x_mm, y_mm, imgW_mm, imgH_mm);
    }}

    const fechaArchivo = new Date().toISOString().slice(0, 10);
    pdf.save('otrs_report_' + fechaArchivo + '.pdf');
  }} catch (err) {{
    console.error('Error al generar PDF', err);
    alert('Error al generar PDF: ' + (err && err.message ? err.message : err));
  }} finally {{
    tempWrappers.forEach(w => {{ try {{ w.remove(); }} catch (_) {{}} }});
    restore.reverse().forEach(fn => {{ try {{ fn(); }} catch (_) {{}} }});
    if (prevTheme !== 'light') document.documentElement.setAttribute('data-theme', prevTheme);
    if (typeof window.__redrawDonut === 'function') window.__redrawDonut();
    overlay.remove();
    pdfBtn.disabled = false;
    pdfBtn.innerHTML = labelOriginal;
  }}
}}

</script>

</body>
</html>"""
