"""
Topic Classifier
================
Rule-based thematic classification for OTRS tickets.
Each ticket receives a topic label based on keyword matching.
"""

import re
import logging
import unicodedata
from collections import Counter

log = logging.getLogger(__name__)

# ── Topic taxonomy (ordered by priority: most specific first) ──
# "Error de sistema" is last because it's cross-cutting.

TOPIC_TAXONOMY = [
    {
        "id": "ddjj_mensual",
        "name": "DDJJ Mensual",
        "color": "#0984e3",
        "keywords": [
            "ddjj mensual", "declaración mensual", "declaracion mensual",
            "cm03", "cm 03", "período mensual", "periodo mensual",
            "ddjj del mes", "ddjj de enero", "ddjj de febrero",
            "ddjj de marzo", "ddjj de abril", "ddjj de mayo",
            "ddjj de junio", "ddjj de julio", "ddjj de agosto",
            "ddjj de septiembre", "ddjj de octubre", "ddjj de noviembre",
            "ddjj de diciembre",
            "declaracion jurada mensual", "declaración jurada mensual",
            "presentar la ddjj", "presentar la declaracion",
            "presentar la declaración", "ddjj de convenio",
            "declaracion jurada de convenio", "declaración jurada de convenio",
            "dj mensual", "dj de convenio", "dj del mes",
            "generar la ddjj", "generar la declaracion", "generar la declaración",
            "ddjj mensuales", "declaraciones juradas mensuales",
        ],
    },
    {
        "id": "ddjj_anual",
        "name": "DDJJ Anual / CM05",
        "color": "#6c5ce7",
        "keywords": [
            "anual", "cm05", "cm 05", "resumen anual",
            "coeficiente unificado", "coeficientes",
            "determinación del impuesto anual", "determinacion del impuesto anual",
            "cierre de ejercicio",
            "coeficientes unificados", "nuevos coeficientes",
        ],
    },
    {
        "id": "jurisdiccion",
        "name": "Jurisdicción / Actividad / Alícuota",
        "color": "#00b894",
        "keywords": [
            "jurisdicción", "jurisdiccion", "jurisdicciones",
            "actividad por jurisd", "alícuota", "alicuota", "alicuotas",
            "no aparece la actividad", "no se despliega",
            "tratamiento fiscal", "código de actividad", "codigo de actividad",
            "actividades", "convenio multilateral",
        ],
    },
    {
        "id": "pagos",
        "name": "Pagos / VEP / Deuda",
        "color": "#fdcb6e",
        "keywords": [
            "pago", "vep", "imputar", "acreditar", "saldo", "deuda",
            "intereses", "monto", "volante de pago",
            "pago duplicado", "pago no registrado",
            "volante electrónico", "volante electronico",
        ],
    },
    {
        "id": "alta_baja",
        "name": "Alta / Baja / Inscripción",
        "color": "#e17055",
        "keywords": [
            "dar de baja", "dar de alta", "baja retroactiva",
            "inscripción", "inscripcion", "cambio de régimen", "cambio de regimen",
            "monotributo", "salir de convenio", "régimen simplificado",
            "regimen simplificado",
            "darse de baja", "darse de alta",
        ],
    },
    {
        "id": "retenciones",
        "name": "Retenciones / Percepciones / Padrón",
        "color": "#00cec9",
        "keywords": [
            "retención", "retencion", "retenciones",
            "percepción", "percepcion", "percepciones",
            "sircreb", "sircar", "padrón", "padron",
            "agente de retención", "agente de retencion",
            "agente de percepción", "agente de percepcion",
        ],
    },
    {
        "id": "acceso",
        "name": "Problemas de acceso",
        "color": "#d63031",
        "keywords": [
            "no puedo ingresar", "no me deja entrar", "acceso",
            "ingresar al sistema", "contraseña", "contrasena",
            "clave fiscal", "usuario y clave",
            "pantalla en blanco", "navegador",
            "modo incógnito", "modo incognito",
            "cache", "caché",
        ],
    },
    {
        "id": "error_sistema",
        "name": "Error de sistema / Performance",
        "color": "#ff7675",
        "keywords": [
            "error", "falla", "no funciona", "lento", "demora",
            "caído", "caido", "sin funcionar", "no carga", "no responde",
            "timeout", "se cuelga", "muy lento", "super lento",
            "no anda", "sistema caído", "sistema caido",
        ],
    },
    {
        "id": "problemas_esporadicos",
        "name": "Problemas esporádicos / vencimientos",
        "color": "#a29bfe",
        "keywords": [
            "vencimiento", "vencimientos", "vence hoy", "vence mañana",
            "fecha de vencimiento", "se venció", "se vencio",
            "no pude terminar", "llevo días", "llevo dias",
            "hace días", "hace dias", "desde hace",
            "sigue sin funcionar", "sigue sin poder",
            "intermitente", "a veces funciona", "a veces anda",
            "importar", "archivo txt", "archivo excel",
            "planilla", "formato archivo",
            "importación", "importacion",
        ],
    },
    {
        "id": "consultas_generales",
        "name": "Consultas Generales",
        "color": "#74b9ff",
        "keywords": [
            "consulta", "consultar", "consulto",
            "quisiera saber", "quería saber", "queria saber",
            "me podrían informar", "me podrian informar",
            "cómo debo", "como debo", "cómo se debe", "como se debe",
            "cómo hago", "como hago", "qué debo", "que debo",
            "pasos a seguir", "me podrían indicar", "me podrian indicar",
            "necesito saber", "quisiera consultar",
            "me comunico para", "me dirijo a ustedes",
        ],
    },
]

OTROS_TOPIC = {
    "id": "otros",
    "name": "Otros",
    "color": "#b2bec3",
}


def _normalize(text):
    """Lowercase + strip accents."""
    text = text.lower()
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _extract_user_text(ticket):
    """Extract user text for topic classification.
    For SUMA BOT tickets, extract message from title + body.
    """
    title = ticket.get("title", "") or ""
    body = ticket.get("user_message_body", "") or ticket.get("first_article_body", "") or ""

    # For SUMA BOT tickets, extract user message from title
    suma_match = re.match(
        r"SUMA\s+BOT\s*-\s*\w+\s*-\s*\d+\s*-\s*(.*)",
        title, re.IGNORECASE,
    )
    if suma_match:
        user_msg_from_title = suma_match.group(1).strip()
        clean_body = re.sub(
            r"Datos del contribuyente:.*?Correo de contacto:\s*\S+\s*",
            "", body, flags=re.DOTALL | re.IGNORECASE,
        ).strip()
        return (user_msg_from_title + " " + clean_body).strip()

    return (title + " " + body).strip()


class TopicClassifier:

    def __init__(self):
        self.taxonomy = TOPIC_TAXONOMY
        self.otros = OTROS_TOPIC

    def classify_tickets(self, tickets):
        """Classify all tickets by topic (including Indeterminados)."""
        for ticket in tickets:
            user_text = _extract_user_text(ticket)
            topics = self._classify_by_rules(user_text)

            if topics:
                ticket["topics"] = [t["name"] for t in topics]
                ticket["primary_topic"] = topics[0]["name"]
                ticket["primary_topic_id"] = topics[0]["id"]
                ticket["primary_topic_color"] = topics[0]["color"]
            else:
                # Reclassify "Otros" by intent
                intent = ticket.get("intent", "INDETERMINADO")
                if intent == "CONSULTA":
                    fallback = self._topic_by_id("consultas_generales")
                elif intent == "RECLAMO":
                    fallback = self._topic_by_id("problemas_esporadicos")
                else:
                    fallback = None

                if fallback:
                    ticket["topics"] = [fallback["name"]]
                    ticket["primary_topic"] = fallback["name"]
                    ticket["primary_topic_id"] = fallback["id"]
                    ticket["primary_topic_color"] = fallback["color"]
                else:
                    ticket["topics"] = ["Otros"]
                    ticket["primary_topic"] = "Otros"
                    ticket["primary_topic_id"] = "otros"
                    ticket["primary_topic_color"] = self.otros["color"]

        # Log summary
        topic_counts = Counter(t.get("primary_topic", "N/A") for t in tickets)
        log.info("Topic classification summary:")
        for topic, count in topic_counts.most_common():
            log.info("  %s: %d", topic, count)

        return tickets

    def _topic_by_id(self, topic_id):
        """Find a topic definition by its id."""
        for t in self.taxonomy:
            if t["id"] == topic_id:
                return t
        return None

    def _classify_by_rules(self, text):
        """Keyword-based topic matching. Returns list of matched topics."""
        text_lower = text.lower()
        text_norm = _normalize(text)
        matched = []

        for topic in self.taxonomy:
            for kw in topic["keywords"]:
                kw_norm = _normalize(kw)
                if kw_norm in text_norm or kw in text_lower:
                    matched.append(topic)
                    break

        return matched

    def get_topic_summary(self, tickets):
        """Generate summary statistics by topic."""
        topic_stats = {}
        total = len(tickets)

        for t in tickets:
            intent = t.get("intent", "INDETERMINADO")
            primary = t.get("primary_topic", "Otros")

            if primary not in topic_stats:
                topic_stats[primary] = {"total": 0, "consulta": 0, "reclamo": 0, "indeterminado": 0}
            topic_stats[primary]["total"] += 1
            if intent == "CONSULTA":
                topic_stats[primary]["consulta"] += 1
            elif intent == "RECLAMO":
                topic_stats[primary]["reclamo"] += 1
            else:
                topic_stats[primary]["indeterminado"] += 1

        # Build ordered list: taxonomy topics first, then "Otros"
        summary = []
        for topic_def in self.taxonomy:
            name = topic_def["name"]
            if name in topic_stats:
                stats = topic_stats[name]
                summary.append({
                    "name": name,
                    "id": topic_def["id"],
                    "color": topic_def["color"],
                    "total": stats["total"],
                    "consulta": stats["consulta"],
                    "reclamo": stats["reclamo"],
                    "indeterminado": stats["indeterminado"],
                    "pct": round(stats["total"] / total * 100, 1) if total else 0,
                })

        # Add "Otros" entry
        if "Otros" in topic_stats:
            stats = topic_stats["Otros"]
            summary.append({
                "name": "Otros",
                "id": "otros",
                "color": self.otros["color"],
                "total": stats["total"],
                "consulta": stats["consulta"],
                "reclamo": stats["reclamo"],
                "indeterminado": stats["indeterminado"],
                "pct": round(stats["total"] / total * 100, 1) if total else 0,
            })

        return {
            "topics": summary,
            "total_classified": total,
        }
