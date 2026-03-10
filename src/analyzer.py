"""
Intent Classifier
=================
Classifies ticket text by intent (Consulta/Duda vs Reclamo/Error)
using keyword/pattern matching, generates word clouds with bigrams/trigrams,
and computes timeline data.
"""

import re
import base64
import logging
import unicodedata
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
    # ── SUM footer signature (Atte. SUM - Sistema Unificado de Mesa de Ayuda) ──
    "atte sum unificado "
    # ── Email threading noise ──
    "responder "
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
    # ── Geographic / ISP / brand noise ──
    "catalinas emeequis fibertel avasmax avasmx "
    # ── Common Spanish verb conjugations (reduce verb noise in word cloud) ──
    # poder
    "puedo puede pueden podemos pudo podria podrian pudimos pudieron "
    # tener
    "tengo tiene tienen tenemos tenia teniamos tuvo tuvimos tuvieron tendra tendras tendre tendria "
    # hacer
    "hago hace hacen hacemos hizo hicimos hicieron haria "
    # querer
    "quiero quiere quieren queremos queria querian quiso quisiera "
    # necesitar
    "necesito necesita necesitan necesitamos necesitaba "
    # solicitar
    "solicito solicita solicitan solicitamos solicite solicito solicitamos "
    # realizar
    "realizo realiza realizan realizamos realice realizo "
    # ingresar
    "ingreso ingresa ingresan ingrese "
    # acceder
    "accedo accede acceden accedi "
    # verificar
    "verifico verifica verifican verifique "
    # completar
    "completo completa completan complete "
    # generar
    "genero genera generan genere "
    # presentar
    "presento presenta presentan presente "
    # actualizar
    "actualizo actualiza actualizan actualice "
    # descargar
    "descargo descarga descargan descargue "
    # cargar
    "cargo carga cargan cargue "
    # encontrar
    "encuentro encuentra encuentran encontre encontramos "
    # dar
    "doy dio damos dieron daba daban dare daria "
    # ver
    "veo vemos vio vieron veia veian vere veria "
    # saber
    "sabe saben sabia sabian supo supimos supieron "
    # salir
    "salgo sale salen sali salimos salieron "
    # seguir
    "sigo sigue siguen segui seguimos siguieron "
    # poner
    "pongo pone ponen puso pusimos pusieron pondre "
    # venir
    "vengo viene vienen vino vinimos vinieron "
    # llevar
    "llevo lleva llevan lleve llevamos llevaron "
    # decir
    "digo dice dicen dijo dijimos dijeron diria "
    # ir
    "voy van iba iban fue fuimos fui "
    # pasar
    "paso pasa pasan pase pasamos pasaron pasaba "
    # llegar
    "llego llega llegan llegue llegamos llegaron "
    # tratar
    "trato trata tratan trate tratamos trataron "
    # buscar
    "busco busca buscan busque buscamos buscaron "
    # escribir
    "escribo escribe escriben escribi escribimos escribieron "
    # pedir
    "pido pide piden pedi pedimos pidieron "
    # recibir
    "recibo recibe reciben recibi recibimos recibieron "
    # esperar
    "espero espera esperan espere esperamos esperaron "
    # indicar
    "indico indica indican indique indicamos indicaron "
    # resolver
    "resuelvo resuelve resuelven resolvi resolvimos resolvieron "
    # abrir
    "abro abre abren abri abrimos abrieron "
    # cerrar
    "cierro cierra cierran cerre cerramos cerraron "
    # cambiar
    "cambio cambia cambian cambie cambiamos cambiaron "
    # mostrar
    "muestro muestra muestran mostre mostramos mostraron "
    # aparecer
    "aparece aparecen apareci aparecimos aparecieron "
    # permitir
    "permito permite permiten permiti permitimos permitieron "
    # intentar
    "intento intenta intentan intente intentamos intentaron "
    # obtener
    "obtengo obtiene obtienen obtuve obtuvimos obtuvieron "
    # enviar (extra forms)
    "envio envia envian envie enviamos enviaron "
    # comunicar
    "comunico comunica comunican comunique comunicamos "
    # registrar
    "registro registra registran registre registramos "
    # configurar
    "configuro configura configuran configure configuramos "
    # adjuntar
    "adjunto adjunta adjuntan adjunte adjuntamos "
    # agregar
    "agrego agrega agregan agregue agregamos "
    # eliminar
    "elimino elimina eliminan elimine eliminamos "
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
    # ── SUM signature fragments (Atte. SUM - Sistema Unificado de Mesa de Ayuda - Comisión Arbitral) ──
    "sistema unificado", "unificado mesa", "mesa ayuda", "ayuda comision",
    "comision arbitral del",
    "sistema unificado mesa", "unificado mesa ayuda", "mesa ayuda comision",
    "ayuda comision arbitral", "arbitral del convenio",
    # ── Email threading ──
    "responder todos", "todos responder", "responder todos responder",
    # ── Names / places ──
    "federico fernandez","federico","fernandez",
    "della paolera", "della", "paolera",
    # ── Geographic / ISP noise ──
    "caba argentina", "piso barrio",
    "avasmx slo int", "slo int fibertel", "int fibertel com",
    # ── Courtesy / closing phrases ──
    "dia hoy", "día hoy",
    "aguardo sus comentarios", "quedamos atentos sus",
    "unidad gestion tributaria", "unidad gestión tributaria",
    # ── Trigramas promovidos a bigramas (se excluye el trigrama para que el bigrama no sea demotado) ──
    "las declaraciones juradas",
    "del mes enero",
    "del convenio multilateral",
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
                      "verein", "swiss", "audit", "advisory",
                      "della", "paolera",
                      "cono", "sur", "catalinas",
                      "emeequis", "fibertel", "avasmax", "avasmx", "slo", "int", "com"}

# English-only words: words that are English but not Spanish.
# Any n-gram containing one of these words will be discarded.
# Words that exist in both languages (e.g. "no", "a", "me") are intentionally excluded.
ENGLISH_ONLY_WORDS = set((
    # ── Common English function/content words ──
    "about above after again against all along already also although always among "
    "another any apart away back because been before behind below between both "
    "came close come does doing done down during each even every everything "
    "few further give goes going got had has have here him his how "
    "into just keep knew know later less like little look make might "
    "most much must need never off often once only other our out own "
    "past put rather right same see seem she should since some something "
    "soon still such take than that the their them then there these they "
    "this those through time too two under until upon use used very "
    "was way well were what when where which while who why will with "
    "would you your "
    # ── System / email / tech jargon ──
    "system host server network postmaster mailer daemon noreply bounce "
    "inbox outbox draft spam phishing query request response status "
    "account access login password install configure setup connect disconnect "
    "enable disable allow deny block filter scan debug log restart reload "
    "upgrade version "
    # ── Email footer / bounce / error messages ──
    "sorry inform please thank send receive forward reply subject "
    "attachment include problem further assistance undeliverable "
    "destination address relay accepted unable delivery delivered failed failure "
    "refused rejected returned bounce permanent temporary "
    "message messages report reports "
    # ── Proper nouns / brands / languages used as English identifiers ──
    "marketplace spanish latin english french german italian portuguese "
    "della paolera "
    # ── Legal / corporate / Deloitte footers ──
    "rights reserved copyright confidential disclaimer intended recipient "
    "regards sincerely best kind dear sent received "
    "certain respective respectively learn terms conditions apply applicable "
    "registered office group independent independently operate operates operating "
    "practice practices practitioner practitioners global network entity entities "
    "legal consulting tax "
    # ── File / encoding / URLs ──
    "jpeg bmp svg doc docx xls xlsx csv txt rtf zip exe dll sys "
    "bat cmd xml json yaml css ftp smtp imap pop ssl tls dns url "
    "uri api div span class style font size color width height content "
    "type charset utf encoding "
    # ── OS / browsers ──
    "windows linux mac android ios chrome firefox safari edge opera "
    # ── Keyboard ──
    "alt enter delete backspace insert "
).split())

# ══════════════════════════════════════════════════════════════
#  Intent classification keywords/patterns
# ══════════════════════════════════════════════════════════════

# Multi-word patterns get higher weight (2) vs single words (1)
CONSULTA_PATTERNS = [
    # Multi-word (weight 2)
    "como hago", "es posible", "quisiera saber", "me podrían indicar",
    "me podrian indicar", "necesito saber", "ayuda con",
    "me gustaría saber", "me gustaria saber", "qué debo", "que debo",
    "pasos para",
    # Single-word (weight 1)
    "cómo", "como", "dónde", "donde", "cuándo", "cuando", "puedo",
    "consulta", "duda", "información", "informacion",
    "orientación", "orientacion", "procedimiento", "requisitos",
    "instrucciones",
]

RECLAMO_PATTERNS = [
    # Multi-word (weight 2)
    "no funciona", "no puedo", "no me deja", "se cayó", "se cayo",
    "no anda", "no carga", "tira error", "pantalla en blanco",
    "no responde", "se cuelga", "devuelve error", "sistema caído",
    "sistema caido", "no se puede",
    # Single-word (weight 1)
    "error", "falla", "problema", "reclamo", "queja", "urgente",
    "imposible", "bug", "incorrecto", "mal",
]

# ── Staff response detection patterns ──
STAFF_PATTERNS = [
    # Imperativos con voseo
    "probá", "verificá", "ingresá", "revisá", "intentá", "descargá",
    "accedé", "seleccioná", "completá", "adjuntá", "enviá", "confirmá",
    "aguardá", "comunicate",
    # Frases de soporte
    "le informamos", "le comunicamos", "procedemos a",
    "queda a disposición", "queda a disposicion",
    "fue derivado", "se resolvió", "se resolvio",
    "hemos verificado", "según lo conversado", "segun lo conversado",
    "tal como se indicó", "tal como se indico",
    "por favor realice", "deberá", "debera",
    "sugerimos", "recomendamos",
    # Cierres formales
    "saludos cordiales", "atte.", "atentamente",
    "quedamos a su disposición", "quedamos a su disposicion",
    "no dude en contactarnos",
]

STAFF_THRESHOLD = 2  # Minimum pattern matches to classify as staff


def _normalize_text(text):
    """Lowercase and strip accents for matching."""
    text = text.lower()
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def is_staff_response(text):
    """Detect if a text is a staff/support response based on linguistic patterns."""
    if not text or len(text.strip()) < 10:
        return False
    text_lower = text.lower()
    text_normalized = _normalize_text(text)
    matches = 0
    for pattern in STAFF_PATTERNS:
        pattern_normalized = _normalize_text(pattern)
        if pattern_normalized in text_normalized or pattern in text_lower:
            matches += 1
            if matches >= STAFF_THRESHOLD:
                return True
    return False


class IntentClassifier:
    def analyze_tickets(self, tickets):
        total = len(tickets)
        for i, ticket in enumerate(tickets, 1):
            text = ticket.get("user_message_body", "") or ticket.get("first_article_body", "")
            if not text or len(text.strip()) < 10:
                ticket["intent"] = "INDETERMINADO"
                ticket["intent_label"] = "Indeterminado"
                ticket["confidence"] = 0.0
                log.info("  [%d/%d] Empty/short -> Indeterminado", i, total)
                continue
            result = self._classify_intent(text)
            ticket["intent"] = result["intent"]
            ticket["intent_label"] = result["intent_label"]
            ticket["confidence"] = result["confidence"]
            log.info("  [%d/%d] %s (%.2f)", i, total,
                     result["intent_label"], result["confidence"])
        return tickets

    def _classify_intent(self, text):
        text_lower = text.lower()
        text_normalized = _normalize_text(text)

        consulta_score = 0
        reclamo_score = 0
        consulta_matches = 0
        reclamo_matches = 0

        # Check for question marks (strong consulta signal)
        if "?" in text:
            consulta_score += 2
            consulta_matches += 1

        for pattern in CONSULTA_PATTERNS:
            pattern_norm = _normalize_text(pattern)
            if pattern_norm in text_normalized or pattern in text_lower:
                weight = 2 if " " in pattern else 1
                consulta_score += weight
                consulta_matches += 1

        for pattern in RECLAMO_PATTERNS:
            pattern_norm = _normalize_text(pattern)
            if pattern_norm in text_normalized or pattern in text_lower:
                weight = 2 if " " in pattern else 1
                reclamo_score += weight
                reclamo_matches += 1

        total_matches = consulta_matches + reclamo_matches

        if total_matches == 0:
            return {"intent": "INDETERMINADO", "intent_label": "Indeterminado", "confidence": 0.0}

        if consulta_score > reclamo_score:
            confidence = consulta_score / (consulta_score + reclamo_score)
            return {"intent": "CONSULTA", "intent_label": "Consulta/Duda", "confidence": round(confidence, 2)}
        elif reclamo_score > consulta_score:
            confidence = reclamo_score / (consulta_score + reclamo_score)
            return {"intent": "RECLAMO", "intent_label": "Reclamo/Error", "confidence": round(confidence, 2)}
        else:
            # Tie — indeterminate
            return {"intent": "INDETERMINADO", "intent_label": "Indeterminado", "confidence": 0.5}

    def get_summary(self, tickets):
        total = len(tickets)
        if total == 0:
            return {"total": 0, "consulta": 0, "reclamo": 0, "indeterminado": 0}
        counts = Counter(t.get("intent", "INDETERMINADO") for t in tickets)
        return {
            "total": total,
            "consulta": counts.get("CONSULTA", 0),
            "reclamo": counts.get("RECLAMO", 0),
            "indeterminado": counts.get("INDETERMINADO", 0),
            "consulta_pct": round(counts.get("CONSULTA", 0) / total * 100, 1),
            "reclamo_pct": round(counts.get("RECLAMO", 0) / total * 100, 1),
            "indeterminado_pct": round(counts.get("INDETERMINADO", 0) / total * 100, 1),
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
            t.get("user_message_body", "") or t.get("first_article_body", "")
            for t in tickets if t.get("user_message_body") or t.get("first_article_body")
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
                if w not in STOPWORDS_ES and w not in ENGLISH_ONLY_WORDS:
                    unigram_freq[w] += 1

            # Bigrams
            for i in range(len(words) - 1):
                w1, w2 = words[i], words[i + 1]
                if w1 in NGRAM_POISON_WORDS or w2 in NGRAM_POISON_WORDS:
                    continue
                if self._contains_english_word([w1, w2]):
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
                if self._contains_english_word([w1, w2, w3]):
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

        # ── Deduplication: demote bigrams absorbed by frequent trigrams ──
        bigrams_in_trigrams = Counter()
        for trigram, count in trigram_freq.items():
            words = trigram.split()
            for i in range(len(words) - 1):
                bi = words[i] + " " + words[i + 1]
                if bi in bigram_freq:
                    bigrams_in_trigrams[bi] += count

        demoted_bigrams = set()
        for bigram, tri_count in bigrams_in_trigrams.items():
            bi_count = bigram_freq.get(bigram, 0)
            if bi_count > 0 and tri_count >= bi_count * 0.75:
                demoted_bigrams.add(bigram)

        for bigram in demoted_bigrams:
            del bigram_freq[bigram]

        if demoted_bigrams:
            log.info("Demoted %d bigrams absorbed by trigrams: %s",
                     len(demoted_bigrams), ", ".join(sorted(demoted_bigrams)[:15]))

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
    def _contains_english_word(words):
        """Return True if any word in the list is an English-only word."""
        return any(w in ENGLISH_ONLY_WORDS for w in words)

    @staticmethod
    def _normalize_accent(text):
        """Strip accents for comparison."""
        nfkd = unicodedata.normalize("NFKD", text)
        return "".join(c for c in nfkd if not unicodedata.combining(c))

    def _is_excluded_ngram(self, ngram):
        """Check if an n-gram matches EXCLUDED_NGRAMS (accent-insensitive)."""
        if ngram in EXCLUDED_NGRAMS:
            return True
        normalized = self._normalize_accent(ngram)
        if normalized in EXCLUDED_NGRAMS:
            return True
        if not hasattr(self, "_normalized_excluded"):
            self._normalized_excluded = {
                self._normalize_accent(x) for x in EXCLUDED_NGRAMS
            }
        return normalized in self._normalized_excluded

    def _tokenize_spanish(self, text):
        """Tokenize text into lowercase Spanish words (>2 chars, only letters)."""
        text = re.sub(r"http\S+", "", text)
        text = re.sub(r"[\w\.-]+@[\w\.-]+", "", text)
        # Strip boilerplate footer signature (e.g. "Atte. SUM Sistema Unificado...")
        text = re.sub(r"\batte\.?\s*sum\b.*", "", text, flags=re.IGNORECASE | re.DOTALL)
        # Strip email threading noise (e.g. "Responder | Responder todos | Reenviar")
        text = re.sub(r"\bresponder\s+todos\b.*", "", text, flags=re.IGNORECASE | re.DOTALL)
        # Strip environmental disclaimer boilerplate
        text = re.sub(r"\bantes de imprimir\b.*?\bambiente\b", "", text, flags=re.IGNORECASE | re.DOTALL)
        text = text.lower()
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
