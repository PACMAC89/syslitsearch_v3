# PRISMA – Volltextsuche und Textextraktion (Pilot)

Dieses Update ergänzt zwei neue Befehle. Es überschreibt **niemals** `fulltext_decisions.csv`, die Suche oder das Screening.

## Installation

Im Projektordner `C:\Users\Philipp\syslitsearch`:

```powershell
Expand-Archive -Path "$env:USERPROFILE\Downloads\syslitsearch_fulltext_pilot_patch.zip" -DestinationPath . -Force
python -m pip install pypdf
python -m pytest -q
```

## 1. Open-Access-Volltextlinks für zehn Paper finden

```powershell
python -m syslitsearch.review fulltext-discover --config examples/review_config.example.json
```

Ergebnis: `results\prisma\retriever_2026_pilot\fulltext\fulltext_discovery.csv`.

Für die ersten zehn noch nicht bearbeiteten Kandidaten wird anhand der DOI bei OpenAlex nach OA-Landingpages und PDF-Links gesucht. Wiederholte Aufrufe überspringen bereits protokollierte IDs und bearbeiten die nächsten zehn. Ein gefundener Link ist **noch kein Beleg**, dass der Volltext vollständig heruntergeladen wurde. Fehlende DOI und HTTP-Fehler werden dokumentiert.

## 2. PDFs lokal bereitstellen

Lege zugängliche PDFs in folgendem Ordner ab:

`results\prisma\retriever_2026_pilot\fulltext\pdfs\`

Dateinamen: **genau die Paper-ID** aus der CSV, z. B. `R2.pdf`.

Diese Version lädt PDFs **nicht selbstständig** herunter. Das ist eine bewusste Begrenzung: OpenAlex-Links können auf Webseiten, Zugangsbarrieren oder ungeprüfte Ziele führen. Manuelles Bereitstellen verhindert unbeabsichtigte Downloads und Zugriffsprobleme.

## 3. Gesamten extrahierbaren PDF-Text auslesen

```powershell
python -m syslitsearch.review fulltext-extract --config examples/review_config.example.json
```

Ausgabe: `fulltext\texts\R2.txt` etc. mit Seitenmarkierungen. Die Extraktion verarbeitet maximal zehn PDFs pro Aufruf; bereits vorhandene Textdateien werden nicht überschrieben. Bei gescannten PDFs ist OCR erforderlich; Formeln und Tabellen können unvollständig extrahiert werden.

## 4. Wissenschaftlicher Status

Die neuen Befehle treffen **keine** LLM- oder menschlichen Eignungsentscheidungen und ändern **keine** PRISMA-Inklusionszahlen. Die vollständige, kriteriumsgebundene LLM-Volltextbewertung mit Textbelegen, menschlicher Freigabe und sicherem automatischem PDF-Download sind noch nicht implementiert. `retrieval_status` darf erst auf `retrieved` gesetzt werden, wenn ein Volltext tatsächlich vorliegt.
