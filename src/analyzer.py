"""
Sentiment Analyzer
==================
Performs sentiment analysis on ticket text using pysentimiento (Spanish BERT)
and generates word clouds.
"""

import re
import base64
import logging
from io import BytesIO
from collections import Counter

import matplotlib

matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
from wordcloud import WordCloud

log = logging.getLogger(__name__)

# Spanish stopwords (extended list for support ticket context)
STOPWORDS_ES = set("""
a al algo algunas algunos ante antes como con contra cual cuando de del desde
donde durante e el ella ellas ellos en entre era eras erais eran eres es esa esas
ese eso esos esta estaba estabais estaban estabas estad estada estadas estado estados
estamos estando estar estaremos estará estarán estarás estaré estaréis estaría
estaríais estaríamos estarían estarías estas este estemos esto estos estoy estuve
estuviera estuvierais estuvieran estuvieras estuvieron estuviese estuvieseis
estuviesen estuvieses estuvimos estuviste estuvisteis estuviéramos estuviésemos
estuvo está estábamos estáis están estás esté estéis estén estés fue fuera fuerais
fueran fueras fueron fuese fueseis fuesen fueses fui fuimos fuiste fuisteis
fuéramos fuésemos ha habida habidas habido habidos habiendo habremos habrá habrán
habrás habré habréis habría habríais habríamos habrían habrías habéis había habíais
habíamos habían habías han has hasta hay haya hayamos hayáis hayan hayas he hemos
hube hubiera hubierais hubieran hubieras hubieron hubiese hubieseis hubiesen
hubieses hubimos hubiste hubisteis hubiéramos hubiésemos hubo la las le les lo los
me mi mis mucho muchos muy más mí mía mías mío míos nada ni no nos nosotras
nosotros nuestra nuestras nuestro nuestros o os otra otras otro otros para pero poco
por que quien quienes qué se sea seamos sean seas sentid sentida sentidas sentido
sentidos ser seremos será serán serás seré seréis sería seríais seríamos serían
serías si sido siendo sin sino sobre sois somos son soy su sus suya suyas suyo suyos
también tanto te tendremos tendrá tendrán tendrás tendré tendréis tendría tendríais
tendríamos tendrían tendrías tened tenemos tenga tengamos tengáis tengan tengas tengo
tenida tenidas tenido tenidos teniendo ti tiene tienen tienes todo todos tu tus tuve
tuviera tuvierais tuvieran tuvieras tuvieron tuviese tuvieseis tuviesen tuvieses
tuvimos tuviste tuvisteis tuviéramos tuviésemos tuvo tuya tuyas tuyo tuyos tú un una
uno unos usted ustedes vosotras vosotros vuestra vuestras vuestro vuestros ya yo él
éramos
hola buenas buenos estimado estimada saludos cordialmente atentamente gracias
estimados días tardes noches favor consulta consultar adjunto adjunta
mailto http https www com gob html
enviar enviado mail correo email mensaje
comarb sifere ddjj
""".split())


def _load_sentiment_model():
    """Load the sentiment analysis model. Uses pysentimiento for Spanish."""
    try:
        from pysentimiento import create_analyzer
        analyzer = create_analyzer(task="sentiment", lang="es")
        log.info("Loaded pysentimiento sentiment model.")
        return analyzer, "pysentimiento"
    except ImportError:
        log.warning("pysentimiento not available. Falling back to transformers pipeline.")

    try:
        from transformers import pipeline
        analyzer = pipeline(
            "sentiment-analysis",
            model="nlptown/bert-base-multilingual-uncased-sentiment",
            truncation=True,
            max_length=512,
        )
        log.info("Loaded multilingual sentiment model.")
        return analyzer, "transformers"
    except Exception as e:
        log.warning(f"Transformers pipeline failed: {e}. Using rule-based fallback.")
        return None, "fallback"


class SentimentAnalyzer:
    def __init__(self):
        self.model, self.model_type = _load_sentiment_model()

    def analyze_tickets(self, tickets: list[dict]) -> list[dict]:
        """Analyze sentiment for each ticket's first article."""
        total = len(tickets)
        for i, ticket in enumerate(tickets, 1):
            text = ticket.get("first_article_body", "")
            if not text or len(text.strip()) < 10:
                ticket["sentiment"] = "NEU"
                ticket["sentiment_label"] = "Neutro"
                ticket["sentiment_score"] = 0.5
                log.info(f"  [{i}/{total}] Empty/short text → Neutro")
                continue

            # Truncate very long texts
            analysis_text = text[:1500]

            sentiment = self._analyze_text(analysis_text)
            ticket["sentiment"] = sentiment["label"]
            ticket["sentiment_label"] = sentiment["label_es"]
            ticket["sentiment_score"] = sentiment["score"]

            log.info(
                f"  [{i}/{total}] {sentiment['label_es']} "
                f"({sentiment['score']:.2f})"
            )

        return tickets

    def _analyze_text(self, text: str) -> dict:
        """Analyze a single text and return sentiment."""
        if self.model_type == "pysentimiento":
            result = self.model.predict(text)
            label = result.output  # POS, NEG, NEU
            probas = result.probas
            score = max(probas.values())

            label_map = {"POS": "Positivo", "NEG": "Negativo", "NEU": "Neutro"}
            return {
                "label": label,
                "label_es": label_map.get(label, label),
                "score": score,
                "probas": probas,
            }

        elif self.model_type == "transformers":
            result = self.model(text[:512])[0]
            # nlptown model returns 1-5 stars
            stars = int(result["label"].split()[0])
            if stars <= 2:
                label, label_es = "NEG", "Negativo"
            elif stars == 3:
                label, label_es = "NEU", "Neutro"
            else:
                label, label_es = "POS", "Positivo"
            return {
                "label": label,
                "label_es": label_es,
                "score": result["score"],
            }

        else:
            return self._rule_based_sentiment(text)

    def _rule_based_sentiment(self, text: str) -> dict:
        """Simple rule-based sentiment for fallback."""
        text_lower = text.lower()

        pos_words = [
            "gracias", "agradezco", "excelente", "perfecto", "bien",
            "funciona", "resuelto", "solucionado", "correcto", "ok",
            "bueno", "genial", "satisfecho",
        ]
        neg_words = [
            "error", "problema", "falla", "no funciona", "imposible",
            "urgente", "grave", "mal", "horrible", "pésimo", "queja",
            "reclamo", "no puedo", "no se puede", "incorrecto",
            "equivocado", "demora", "lento", "nunca",
        ]

        pos_count = sum(1 for w in pos_words if w in text_lower)
        neg_count = sum(1 for w in neg_words if w in text_lower)

        if neg_count > pos_count:
            return {"label": "NEG", "label_es": "Negativo", "score": 0.6}
        elif pos_count > neg_count:
            return {"label": "POS", "label_es": "Positivo", "score": 0.6}
        else:
            return {"label": "NEU", "label_es": "Neutro", "score": 0.5}

    def get_summary(self, tickets: list[dict]) -> dict:
        """Generate summary statistics."""
        total = len(tickets)
        if total == 0:
            return {"total": 0, "positive": 0, "negative": 0, "neutral": 0}

        counts = Counter(t.get("sentiment", "NEU") for t in tickets)

        return {
            "total": total,
            "positive": counts.get("POS", 0),
            "negative": counts.get("NEG", 0),
            "neutral": counts.get("NEU", 0),
            "positive_pct": round(counts.get("POS", 0) / total * 100, 1),
            "negative_pct": round(counts.get("NEG", 0) / total * 100, 1),
            "neutral_pct": round(counts.get("NEU", 0) / total * 100, 1),
        }

    def generate_wordcloud(self, tickets: list[dict]) -> str:
        """
        Generate a word cloud from all ticket texts.
        Returns a base64-encoded PNG image string.
        """
        # Combine all text
        all_text = " ".join(
            t.get("first_article_body", "") for t in tickets if t.get("first_article_body")
        )

        if not all_text.strip():
            return ""

        # Clean text
        all_text = re.sub(r"http\S+", "", all_text)
        all_text = re.sub(r"[\w\.-]+@[\w\.-]+", "", all_text)
        all_text = re.sub(r"[^\w\sáéíóúñü]", " ", all_text.lower())
        all_text = re.sub(r"\d+", "", all_text)
        all_text = re.sub(r"\s+", " ", all_text)

        # Generate word cloud
        try:
            wc = WordCloud(
                width=1200,
                height=600,
                background_color="#1a1a2e",
                colormap="cool",
                max_words=150,
                stopwords=STOPWORDS_ES,
                min_font_size=10,
                max_font_size=120,
                prefer_horizontal=0.7,
                collocations=False,
                margin=20,
            )
            wc.generate(all_text)

            # Convert to base64 PNG
            fig, ax = plt.subplots(figsize=(14, 7))
            ax.imshow(wc, interpolation="bilinear")
            ax.axis("off")
            fig.patch.set_facecolor("#1a1a2e")
            plt.tight_layout(pad=0)

            buf = BytesIO()
            fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                       facecolor="#1a1a2e", edgecolor="none")
            plt.close(fig)
            buf.seek(0)

            b64 = base64.b64encode(buf.read()).decode("utf-8")
            log.info(f"Word cloud generated ({len(b64) // 1024} KB).")
            return b64

        except Exception as e:
            log.error(f"Error generating word cloud: {e}")
            return ""
