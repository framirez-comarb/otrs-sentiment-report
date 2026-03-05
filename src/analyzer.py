"""
Sentiment Analyzer
==================
Performs sentiment analysis on ticket text using pysentimiento (Spanish BERT),
generates word clouds with bigrams/trigrams, and computes timeline data.
"""

import re
import base64
import logging
from io import BytesIO
from collections import Counter
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from wordcloud import WordCloud

log = logging.getLogger(__name__)

STOPWORDS_ES = set((
    # ── Spanish stopwords ──
    "a al algo algunas algunos ante antes como con contra cual cuando de del desde "
    "donde durante e el ella ellas ellos en entre era eras erais eran eres es esa esas "
    "ese eso esos esta estaba estaban estabas estado estados estamos estando estar "
    "estas este esto estos estoy estuvo fue fuera fueran fueras fueron fuese fuesen "
    "fui fuimos ha habido habiendo habra habria han has hasta hay haya hayan he hemos "
    "hube hubiera hubieran hubieras hubieron hubo la las le les lo los me mi mis mucho "
    "muchos muy mas nada ni no nos nosotros nuestra nuestras nuestro nuestros otra "
    "otras otro otros para pero poco por que quien quienes sea sean ser sera seria si "
    "sido siendo sin sino sobre somos son soy su sus tambien tanto te tenemos tenga "
    "tengo ti tiene tienen tienes toda todas todo todos tu tus tuvo un una uno unos "
    "usted ustedes ya yo cada vez asi aqui ahi cual cuales cuyo cuya cuyos cuyas "
    "ese esa esos esas aquel aquella aquellos aquellas mismo misma mismos mismas "
    "tal tales tan luego pues porque aunque mientras ademas despues aun asi "
    # ── Greetings / courtesy ──
    "hola buenas buenos estimado estimada saludos cordialmente atentamente gracias "
    "estimados favor consulta consultar adjunto adjunta dias tardes noches muchas "
    "buen dia buenos dias buenas tardes buenas noches "
    # ── Email / web junk ──
    "mailto http https www com gob html org net php asp aspx "
    "enviar enviado mail correo email mensaje asunto "
    # ── Domain-specific exclusions ──
    "comarb sifere ddjj "
    "contribuyente contribuyentes del dato datos cuit cuits contacto "
    # ── Deloitte and related ──
    "deloitte dttl deloite "
    # ── Common English words (from HTML emails, signatures, footers) ──
    "the and for are but not you all any can had her was one our out "
    "day get has him his how its let may new now old see way who boy "
    "did few got her him his how its let may new now old see time very "
    "when come made like long look many only over such take than them "
    "will about also back been call came come each find from give have "
    "here just know last long make more most name need next only over "
    "part plan read said same show side some tell text that then they "
    "this time turn upon used want well went what when with word work "
    "year your from with will have this that been more some what which "
    "there their would could should after other first into just where "
    "before being those still while found between under again never "
    "most only through might must each does before where after every "
    "member firm global network refer entity entities legal rights "
    "reserved please note above below click here visit website "
    "copyright confidential disclaimer intended recipient information "
    "image images file files document attached attachment "
    "regards sincerely best kind dear sent received subject "
    # ── English: Deloitte / Tohmatsu / consulting footer junk ──
    "touche tohmatsu limited group related refers separate "
    "provide services clients audit advisory consulting tax "
    "independent independently operate operates operating "
    "practice practices practitioner practitioners "
    "certain respective respectively "
    "learn more terms conditions apply applicable "
    "regulated regulated associated association "
    "tmf verein swiss registered office "
    # ── Technical / keyboard / file terms ──
    "ctrl shift alt tab enter delete backspace insert home end "
    "png jpg jpeg gif bmp svg pdf doc docx xls xlsx csv txt rtf zip "
    "exe dll sys bat cmd xml json yaml css "
    "windows linux mac android ios chrome firefox safari edge opera "
    "web app http https ftp smtp imap pop ssl tls dns url uri api "
    "cid src href img div span class style font size color width height "
    "content type charset utf encoding base "
    # ── Other noise ──
    "image png image image jpg image gif "
    "presiona ctrl "
).split())

# Excluded n-gram phrases (lowercased)
EXCLUDED_NGRAMS = {
    # ── Domain-specific ──
    "datos del contribuyente", "datos del", "del contribuyente",
    "correo de contacto", "correo contacto", "de contacto",
    # ── Common Spanish courtesy phrases ──
    "muchas gracias", "buenos dias", "buenas tardes", "buenas noches",
    "buen dia", "desde ya muchas", "ya muchas gracias",
    "desde ya", "por favor", "le saluda", "nos comunicamos",
    "quedo atento", "quedo atenta", "queda atento", "queda atenta",
    "saludos cordiales", "muchas gracias por",
    "atentamente", "un saludo", "le informamos",
    "estimado contribuyente", "estimada contribuyente",
    # ── Domain noise ──
    "archivo adjunto", "adjunto archivo",
    # ── Names ──
    "federico fernandez","federico","fernandez",
    # ── Deloitte / Tohmatsu (any n-gram with poison words also caught by code) ──
    "member firm", "deloitte member", "deloitte firm",
    "global network", "member firm deloitte",
    "touche tohmatsu", "tohmatsu limited", "touche tohmatsu limited",
    "provide services", "services clients", "provide services clients",
    "services clients please", "not provide services",
}

# Words that should be excluded from ANY n-gram they appear in
NGRAM_POISON_WORDS = {"deloitte", "dttl", "deloite", "member", "firm", "image", "png",
                      "jpg", "gif", "ctrl", "shift", "cid", "src", "href",
                      "touche", "tohmatsu", "limited", "services", "clients",
                      "provide", "separate", "refers", "related", "tmf",
                      "verein", "swiss", "audit", "advisory"}


def _load_sentiment_model():
    try:
        from pysentimiento import create_analyzer
        analyzer = create_analyzer(task="sentiment", lang="es")
        log.info("Loaded pysentimiento sentiment model.")
        return analyzer, "pysentimiento"
    except ImportError:
        log.warning("pysentimiento not available.")
    try:
        from transformers import pipeline
        analyzer = pipeline(
            "sentiment-analysis",
            model="nlptown/bert-base-multilingual-uncased-sentiment",
            truncation=True, max_length=512,
        )
        log.info("Loaded multilingual sentiment model.")
        return analyzer, "transformers"
    except Exception as e:
        log.warning("Transformers failed: %s. Using rule-based fallback." % e)
        return None, "fallback"


class SentimentAnalyzer:
    def __init__(self):
        self.model, self.model_type = _load_sentiment_model()

    def analyze_tickets(self, tickets):
        total = len(tickets)
        for i, ticket in enumerate(tickets, 1):
            text = ticket.get("first_article_body", "")
            if not text or len(text.strip()) < 10:
                ticket["sentiment"] = "NEU"
                ticket["sentiment_label"] = "Neutro"
                ticket["sentiment_score"] = 0.5
                log.info("  [%d/%d] Empty/short -> Neutro", i, total)
                continue
            sentiment = self._analyze_text(text[:1500])
            ticket["sentiment"] = sentiment["label"]
            ticket["sentiment_label"] = sentiment["label_es"]
            ticket["sentiment_score"] = sentiment["score"]
            log.info("  [%d/%d] %s (%.2f)", i, total,
                     sentiment["label_es"], sentiment["score"])
        return tickets

    def _analyze_text(self, text):
        if self.model_type == "pysentimiento":
            result = self.model.predict(text)
            label = result.output
            probas = result.probas
            label_map = {"POS": "Positivo", "NEG": "Negativo", "NEU": "Neutro"}
            return {
                "label": label,
                "label_es": label_map.get(label, label),
                "score": max(probas.values()),
                "probas": probas,
            }
        elif self.model_type == "transformers":
            result = self.model(text[:512])[0]
            stars = int(result["label"].split()[0])
            if stars <= 2:
                label, label_es = "NEG", "Negativo"
            elif stars == 3:
                label, label_es = "NEU", "Neutro"
            else:
                label, label_es = "POS", "Positivo"
            return {"label": label, "label_es": label_es, "score": result["score"]}
        else:
            return self._rule_based_sentiment(text)

    def _rule_based_sentiment(self, text):
        tl = text.lower()
        pos = ["gracias", "agradezco", "excelente", "perfecto", "bien",
               "funciona", "resuelto", "solucionado", "correcto", "ok",
               "bueno", "genial", "satisfecho"]
        neg = ["error", "problema", "falla", "no funciona", "imposible",
               "urgente", "grave", "mal", "horrible", "pesimo", "queja",
               "reclamo", "no puedo", "no se puede", "incorrecto",
               "equivocado", "demora", "lento", "nunca"]
        pc = sum(1 for w in pos if w in tl)
        nc = sum(1 for w in neg if w in tl)
        if nc > pc:
            return {"label": "NEG", "label_es": "Negativo", "score": 0.6}
        elif pc > nc:
            return {"label": "POS", "label_es": "Positivo", "score": 0.6}
        else:
            return {"label": "NEU", "label_es": "Neutro", "score": 0.5}

    def get_summary(self, tickets):
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

    # ══════════════════════════════════════════════════════════════
    #  Word Cloud with bigrams/trigrams
    # ══════════════════════════════════════════════════════════════

    def generate_wordcloud(self, tickets):
        """Generate word cloud with unigrams + bigrams + trigrams.
        Deduplicates: words absorbed by frequent n-grams are demoted.
        Returns dict: {"image_b64": str, "top_bigrams": list, "top_trigrams": list}
        """
        all_texts = [
            t.get("first_article_body", "")
            for t in tickets if t.get("first_article_body")
        ]
        if not all_texts:
            return {"image_b64": "", "top_bigrams": [], "top_trigrams": []}

        unigram_freq = Counter()
        bigram_freq = Counter()
        trigram_freq = Counter()

        for raw_text in all_texts:
            words = self._tokenize_spanish(raw_text)

            # Unigrams
            for w in words:
                if w not in STOPWORDS_ES:
                    unigram_freq[w] += 1

            # Bigrams
            for i in range(len(words) - 1):
                w1, w2 = words[i], words[i + 1]
                if w1 in NGRAM_POISON_WORDS or w2 in NGRAM_POISON_WORDS:
                    continue
                bigram = w1 + " " + w2
                if self._is_excluded_ngram(bigram):
                    continue
                if w1 not in STOPWORDS_ES and w2 not in STOPWORDS_ES:
                    bigram_freq[bigram] += 1

            # Trigrams
            for i in range(len(words) - 2):
                w1, w2, w3 = words[i], words[i + 1], words[i + 2]
                if w1 in NGRAM_POISON_WORDS or w2 in NGRAM_POISON_WORDS or w3 in NGRAM_POISON_WORDS:
                    continue
                trigram = w1 + " " + w2 + " " + w3
                if self._is_excluded_ngram(trigram):
                    continue
                meaningful = sum(
                    1 for w in [w1, w2, w3] if w not in STOPWORDS_ES
                )
                if meaningful >= 2:
                    trigram_freq[trigram] += 1

        # Filter: keep only freq >= 2
        unigram_freq = Counter({k: v for k, v in unigram_freq.items() if v >= 2})
        bigram_freq = Counter({k: v for k, v in bigram_freq.items() if v >= 2})
        trigram_freq = Counter({k: v for k, v in trigram_freq.items() if v >= 2})

        # ── Deduplication: demote unigrams absorbed by frequent n-grams ──
        # If a word appears in a bigram/trigram that has >= 75% of the word's
        # unigram count, remove the word from unigrams (the n-gram represents
        # it better as a concept).
        words_in_ngrams = Counter()
        for ngram, count in list(bigram_freq.items()) + list(trigram_freq.items()):
            for w in ngram.split():
                if w not in STOPWORDS_ES:
                    words_in_ngrams[w] += count

        demoted = set()
        for word, ngram_count in words_in_ngrams.items():
            uni_count = unigram_freq.get(word, 0)
            if uni_count > 0 and ngram_count >= uni_count * 0.75:
                demoted.add(word)

        for word in demoted:
            del unigram_freq[word]

        if demoted:
            log.info("Demoted %d unigrams absorbed by n-grams: %s",
                     len(demoted), ", ".join(sorted(demoted)[:15]))

        # ── Build combined frequency for word cloud ──
        combined = Counter()
        combined.update(unigram_freq)
        combined.update(bigram_freq)
        combined.update(trigram_freq)

        if not combined:
            return {"image_b64": "", "top_bigrams": [], "top_trigrams": []}

        top_terms = ", ".join(
            "%s(%d)" % (k, v) for k, v in combined.most_common(10)
        )
        log.info("Word cloud: %d terms (%d uni, %d bi, %d tri). Top: %s",
                 len(combined), len(unigram_freq), len(bigram_freq),
                 len(trigram_freq), top_terms)

        # ── Generate image ──
        try:
            wc = WordCloud(
                width=1200, height=600,
                background_color="#1a1a2e", colormap="cool",
                max_words=150, min_font_size=10, max_font_size=120,
                prefer_horizontal=0.7, margin=20,
            )
            wc.generate_from_frequencies(combined)

            fig, ax = plt.subplots(figsize=(14, 7))
            ax.imshow(wc, interpolation="bilinear")
            ax.axis("off")
            fig.patch.set_facecolor("#1a1a2e")
            plt.tight_layout(pad=0)

            buf = BytesIO()
            fig.savefig(
                buf, format="png", dpi=150, bbox_inches="tight",
                facecolor="#1a1a2e", edgecolor="none",
            )
            plt.close(fig)
            buf.seek(0)
            b64 = base64.b64encode(buf.read()).decode("utf-8")
            log.info("Word cloud generated (%d KB).", len(b64) // 1024)

        except Exception as e:
            log.error("Error generating word cloud: %s", e)
            b64 = ""

        top_bigrams = [
            {"term": k, "count": v} for k, v in bigram_freq.most_common(10)
        ]
        top_trigrams = [
            {"term": k, "count": v} for k, v in trigram_freq.most_common(10)
        ]

        return {"image_b64": b64, "top_bigrams": top_bigrams, "top_trigrams": top_trigrams}

    @staticmethod
    def _normalize_accent(text):
        """Strip accents for comparison: dias == dias, presentacion == presentacion."""
        import unicodedata
        nfkd = unicodedata.normalize("NFKD", text)
        return "".join(c for c in nfkd if not unicodedata.combining(c))

    def _is_excluded_ngram(self, ngram):
        """Check if an n-gram matches EXCLUDED_NGRAMS (accent-insensitive)."""
        if ngram in EXCLUDED_NGRAMS:
            return True
        normalized = self._normalize_accent(ngram)
        if normalized in EXCLUDED_NGRAMS:
            return True
        # Also check the normalized version against normalized exclusions
        if not hasattr(self, "_normalized_excluded"):
            self._normalized_excluded = {
                self._normalize_accent(x) for x in EXCLUDED_NGRAMS
            }
        return normalized in self._normalized_excluded

    def _tokenize_spanish(self, text):
        """Tokenize text into lowercase Spanish words (>2 chars, only letters)."""
        text = re.sub(r"http\S+", "", text)
        text = re.sub(r"[\w\.-]+@[\w\.-]+", "", text)
        text = text.lower()
        # Match sequences of Latin letters including accented Spanish chars
        tokens = re.findall(r"[a-z\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1\u00fc]+", text)
        return [t for t in tokens if len(t) > 2]

    # ══════════════════════════════════════════════════════════════
    #  Timeline data (tickets per day / per month)
    # ══════════════════════════════════════════════════════════════

    def get_timeline_data(self, tickets):
        """Aggregate ticket counts by day and month."""
        day_counter = Counter()
        month_counter = Counter()

        for t in tickets:
            date_str = t.get("created", "") or t.get("first_article_date", "")
            parsed = self._parse_date(date_str)
            if parsed:
                day_counter[parsed.strftime("%Y-%m-%d")] += 1
                month_counter[parsed.strftime("%Y-%m")] += 1

        by_day = [{"date": k, "count": v} for k, v in sorted(day_counter.items())]
        by_month = [{"month": k, "count": v} for k, v in sorted(month_counter.items())]

        log.info("Timeline: %d days, %d months", len(by_day), len(by_month))
        return {"by_day": by_day, "by_month": by_month}

    @staticmethod
    def _parse_date(date_str):
        """Try to parse various date formats from OTRS."""
        if not date_str:
            return None
        date_str = date_str.strip()

        # Format: "26/02/2026 - 08:20" or "26/02/2026"
        m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", date_str)
        if m:
            try:
                return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            except ValueError:
                pass

        # Format: "2026-02-26 08:20:00"
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", date_str)
        if m:
            try:
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass

        return None
