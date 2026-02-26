# OTRS Sentiment Analysis Report

Reporte automatizado de análisis de sentimiento sobre tickets del sistema OTRS de COMARB. Se ejecuta diariamente a las 12:00 (hora Argentina) mediante GitHub Actions y se publica en GitHub Pages.

## ¿Qué hace?

1. **Scraping**: Se conecta a OTRS, busca tickets con los filtros configurados (palabra clave, colas, fechas)
2. **Extracción**: Obtiene el primer mail/artículo de cada ticket
3. **Análisis de sentimiento**: Clasifica cada ticket como Positivo, Negativo o Neutro usando IA (modelo BERT en español)
4. **Nube de palabras**: Genera una nube con las palabras más frecuentes
5. **Reporte HTML**: Publica un dashboard interactivo en GitHub Pages

## Setup — Paso a paso

### 1. Crear el repositorio en GitHub

1. Ir a [github.com/new](https://github.com/new)
2. Nombre: `otrs-sentiment-report` (o el que prefieras)
3. Visibilidad: **Private** (recomendado, maneja credenciales)
4. Crear el repositorio **vacío** (sin README ni .gitignore)

### 2. Subir el código

```bash
# En tu PC, dentro de la carpeta del proyecto:
git init
git add -A
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/otrs-sentiment-report.git
git push -u origin main
```

### 3. Configurar los Secrets (credenciales)

Ir a **Settings → Secrets and variables → Actions** en tu repositorio.

Crear estos **Secrets** (Repository secrets):

| Secret | Valor |
|--------|-------|
| `OTRS_URL` | `https://webs.comarb.gob.ar/otrs/index.pl` |
| `OTRS_USER` | Tu usuario de OTRS |
| `OTRS_PASS` | Tu contraseña de OTRS |

### 4. Configurar las Variables (parámetros de búsqueda)

En el mismo lugar (**Settings → Secrets and variables → Actions → Variables tab**):

| Variable | Valor | Descripción |
|----------|-------|-------------|
| `SEARCH_FULLTEXT` | `incógnito` | Palabra clave de búsqueda |
| `SEARCH_QUEUES` | `SIFERE,Módulo Consultas,Módulo DDJJ` | Colas separadas por coma |
| `DATE_FROM` | `2025-01-01` | Fecha desde (YYYY-MM-DD) |

> `DATE_TO` se calcula automáticamente como la fecha actual.

### 5. Activar GitHub Pages

1. Ir a **Settings → Pages**
2. Source: **Deploy from a branch**
3. Branch: `gh-pages` / `/ (root)`
4. Guardar

> ⚠️ La primera vez no existirá el branch `gh-pages`. Se creará automáticamente al ejecutar el workflow por primera vez.

### 6. Primera ejecución (manual)

1. Ir a **Actions** en tu repositorio
2. Click en "Generate OTRS Sentiment Report" en la barra lateral
3. Click en **"Run workflow"** → **"Run workflow"**
4. Esperar ~5-10 minutos (la primera vez descarga el modelo de IA)

### 7. Ver el reporte

Una vez completado, el reporte estará disponible en:

```
https://TU_USUARIO.github.io/otrs-sentiment-report/
```

Compartí ese link con quien necesite verlo.

## Ejecución automática

El workflow se ejecuta automáticamente todos los días a las **12:00 hora Argentina** (15:00 UTC).

Para cambiar el horario, editá el cron en `.github/workflows/report.yml`:

```yaml
schedule:
  - cron: '0 15 * * *'  # 15:00 UTC = 12:00 ART
```

## Ejecución local (para testing)

```bash
# Crear un entorno virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Instalar dependencias
pip install -r requirements.txt

# Configurar credenciales
export OTRS_URL="https://webs.comarb.gob.ar/otrs/index.pl"
export OTRS_USER="tu_usuario"
export OTRS_PASS="tu_contraseña"

# Ejecutar
python main.py

# El reporte se genera en docs/index.html
```

## Estructura del proyecto

```
├── .github/workflows/report.yml    # GitHub Actions (cron + deploy)
├── src/
│   ├── scraper.py                  # Login + búsqueda + extracción OTRS
│   ├── analyzer.py                 # Análisis de sentimiento + word cloud
│   └── report_generator.py         # Generación del HTML
├── main.py                         # Orquestador principal
├── requirements.txt                # Dependencias Python
└── README.md
```

## Troubleshooting

### "Failed to authenticate with OTRS"
- Verificar que las credenciales en Secrets sean correctas
- Verificar que OTRS sea accesible desde internet (no solo VPN)
- El script usa HTTP Basic Auth. Si OTRS cambió de método, habrá que ajustar

### "No tickets found"
- Verificar los nombres de las colas (deben coincidir exactamente con OTRS)
- Verificar que la palabra clave sea correcta (con tilde: `incógnito`)
- Revisar el rango de fechas

### El workflow falla en "Install dependencies"
- PyTorch puede ser pesado. Si hay problemas de espacio, se puede usar `torch-cpu`:
  ```
  pip install torch --index-url https://download.pytorch.org/whl/cpu
  ```

### GitHub Pages no muestra el reporte
- Verificar que el branch `gh-pages` existe (se crea en la primera ejecución)
- En Settings → Pages, confirmar que apunta a `gh-pages` / `/ (root)`
- Puede tardar 2-3 minutos en desplegarse después del push

## Notas importantes

- **Credenciales**: Nunca se guardan en el código. Solo existen como GitHub Secrets (encriptados).
- **Rate limiting**: El script espera 1.5 segundos entre requests para no sobrecargar el servidor OTRS.
- **Modelo de IA**: Usa [pysentimiento](https://github.com/pysentimiento/pysentimiento), un modelo BERT fine-tuneado para análisis de sentimiento en español. Corre localmente, sin enviar datos a terceros.
- **Costos**: Todo es gratuito (GitHub Actions Free tiene 2000 min/mes para repos privados).
