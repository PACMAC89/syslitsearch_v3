# syslitsearch – Literaturrecherche und PRISMA-orientierter Review

**Stand: konsolidierte Codebasis, 20.11.2026.** Der Workflow ist PRISMA-orientiert; weder die Software noch ein automatisches Screening begründen PRISMA-2020-Konformität oder eine verifizierte Peer-Review-Einstufung. Ein `max_records`-Pilot ist keine vollständige systematische Suche.

## Einrichtung (Windows PowerShell)

Im Projektverzeichnis und in der bestehenden `.venv`:

```powershell
python -m pip install -e .
python -m pytest -q
python -m syslitsearch.review plan --config examples/review_config.retriever_new_run.json
```

**Wichtig:** `.env` mit API-Zugangsdaten bleibt ausschließlich lokal und ist von Git ausgeschlossen. Die bereitgestellte ZIP enthält keine `.env`, `.git`, `.venv` oder Ergebnisdaten. Es werden keine kostenpflichtigen Such-APIs (z. B. Brave) im dokumentierten Workflow benötigt. Die Datenbanksuche kann jedoch institutionelle API-Zugänge erfordern; das LLM-Screening benötigt den konfigurierten LLM-Endpunkt und kann je nach Anbieter Kosten verursachen. Vor `judge` Zugangsbedingungen prüfen.

## Ein klarer Review-Ablauf

Die neue Konfiguration `examples/review_config.retriever_new_run.json` verwendet absichtlich einen **neuen Ergebnisordner**, damit der bestehende Pilot unangetastet bleibt. Die `max_records=100`-Grenze gilt **je Datenbank**, nicht insgesamt. Für eine vollständige Suche ist die Abdeckung der Datenbanken und die geeignete Abfrage-/Exportstrategie separat zu validieren.

```powershell
# 1. Plan anzeigen – keine API-Aufrufe
python -m syslitsearch.review plan --config examples/review_config.retriever_new_run.json

# 2. Datenbanksuche (API-Aufrufe; zunächst limitierter Pilot)
python -m syslitsearch.review search --config examples/review_config.retriever_new_run.json

# 3. Screening-Batches vorbereiten
python -m syslitsearch.review prepare --config examples/review_config.retriever_new_run.json

# 4. LLM-Screening – erst nach Prüfung von Endpunkt, Modell und Kosten
python -m syslitsearch.review judge --config examples/review_config.retriever_new_run.json

# 5. Screening-Ergebnisse zusammenführen
python -m syslitsearch.review build --config examples/review_config.retriever_new_run.json

# 6. Nachvollziehbarkeit und PRISMA-orientierte Zählung
python -m syslitsearch.review audit --config examples/review_config.retriever_new_run.json
python -m syslitsearch.review flow --config examples/review_config.retriever_new_run.json

# 7. Vorläufige Leseliste
python -m syslitsearch.review reading-list --config examples/review_config.retriever_new_run.json
```

Das Screening kann `include`, `unsure`, `exclude` liefern; ein automatisches Modellurteil ist keine menschliche Volltextentscheidung. Die Dokumentation eines vollständigen PRISMA-Flusses erfordert nachprüfbare Dubletten-, Retrieval- und Ausschlusszahlen.

### Publikationsprüfung und evidenzbasierte Leseliste

Nach `build` in einem **neuen, noch nicht vorhandenen** Publikationsordner:

```powershell
python -m syslitsearch.publication_workflow `
  --screening results/prisma/retriever_2026_new_run/screening.xlsx `
  --out results/prisma/retriever_2026_new_run/publication_review `
  --policy-leads

python -m syslitsearch.publication_refresh `
  --screening results/prisma/retriever_2026_new_run/screening.xlsx `
  --publication-dir results/prisma/retriever_2026_new_run/publication_review `
  --output results/prisma/retriever_2026_new_run/prioritized_reading_list_provisional.xlsx `
  --keywords examples/keywords.csv `
  --criteria examples/screening_criteria.md
```

`publication_workflow` verwendet freie bibliografische Metadatenquellen (z. B. Crossref/OpenAlex) und führt nur eine **Triage** durch. Die A1-Kategorie darf nicht ohne manuell geprüfte, paperbezogene Evidenz vergeben werden. `publication_refresh` benötigt `publication_evidence.csv`, `metadata_suggestions.csv` und `publication_triage.csv`; es verweigert das Überschreiben vorhandener Leselisten.

Optionale, begrenzte freie Webseiten-Evidenzsuche (nur Kandidaten, keine Zertifizierung):

```powershell
python -m syslitsearch.publication_free_finalize `
  --metadata results/prisma/retriever_2026_new_run/publication_review/metadata_suggestions.csv `
  --out results/prisma/retriever_2026_new_run/publication_review/free_evidence_candidates.csv `
  --offline --max-groups 15
```

Ohne `--offline` werden öffentliche HTML-Seiten abgerufen, begrenzt durch `--max-pages` und `--max-groups`. Es werden keine PDFs heruntergeladen. Andere Module können andere Netzwerkbedingungen haben; diese Aussage gilt nur für `publication_free_finalize`.

### Menschliche Volltextentscheidung

```powershell
python -m syslitsearch.review eligibility-template --config examples/review_config.retriever_new_run.json
```

Die CSV muss anschließend von Menschen ausgefüllt werden. Optional: `fulltext-discover` und `fulltext-extract` (siehe `VOLLTEXT_ANLEITUNG.md`). Keine automatische Behauptung einer finalen Einschlussentscheidung.

## Aktive Module und Verantwortlichkeiten

| Bereich | Module | Funktion |
| --- | --- | --- |
| Datenbanksuche | `cli.py`, `query.py`, `search.py`, `sources/`, `report.py` | Datenbanken abfragen, deduplizieren, Excel-Report |
| Screening | `screening.py`, `llm.py` | Batches, Modellurteile, Screening-Export |
| Review-Steuerung | `review.py` | Stufen, Manifest, Audit, PRISMA-orientierte Zählung |
| Publikationsprüfung | `publication.py`, `publication_auto.py`, `publication_verify.py`, `publication_workflow.py`, `publication_discovery.py`, `publication_policy_discovery.py` | Evidenzstruktur, Metadaten, Triage, optionale Kandidatensuche |
| Priorisierung | `reading_list.py`, `publication_refresh.py`, `venue_policy_audit.py` | Evidenzbasierte, vorläufige Leseliste |
| Freie Webseitenkandidaten | `publication_free_finalize.py` | Begrenzt, optional, keine automatische Zertifizierung |
| Volltext | `fulltext.py`, `extraction.py` | Optionale Volltext- und Extraktionshilfen |

**Entfernte Altdateien im Lieferpaket:** `publication_venue_discovery.py` (separater Brave-API-Pfad), `publication_evidence_engine.py` (nicht in den aktiven Importen/Tests referenziert) und `sources/scopus.py.bak` (identische Sicherungskopie). Die beiden Python-Module werden separat im Rückfallarchiv mitgeliefert; sie sind keine Abhängigkeiten des dokumentierten Workflows. Andere Module wurden bewusst **nicht** zusammengelegt, weil dies bestehende CLI-Einstiegspunkte und Tests gefährden würde.

## Datenintegrität und Grenzen

- Ergebnisse und `.env` werden nicht in Git versioniert; sichere Ergebnisordner gesondert.
- Ein vorhandener Ergebnisordner ist nicht automatisch wiederverwendbar; mehrere Stufen verweigern bewusst Überschreiben.
- Für jeden neuen Lauf neue `review_id` und `output_dir` vergeben.
- Der frühere Retriever-Pilot mit 275 Screening-Zeilen und 156 A2 / 19 B / 17 C ist **nicht Bestandteil dieses ZIPs** und wird durch diese Lieferung nicht verändert.
- Die Tests prüfen den Code offline; sie belegen nicht die Erreichbarkeit von Scopus, IEEE, Semantic Scholar oder dem LLM-Endpunkt.
