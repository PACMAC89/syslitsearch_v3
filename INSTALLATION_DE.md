# Sichere Installation der konsolidierten Version

**Nicht** das Originalprojekt oder `results/` löschen. Die ZIP enthält nur Code, Tests, Beispiele und Dokumentation; sie ist **kein** Ersatz für `.env`, `.git`, `.venv` oder bestehende Ergebnisordner.

1. Das ZIP in einen **neuen Ordner** entpacken, z. B. `C:\Users\Philipp\syslitsearch_konsolidiert_test`. Nicht direkt über das Original entpacken.
2. Im neuen Ordner Tests mit der vorhandenen Python-Umgebung ausführen:

```powershell
cd C:\Users\Philipp\syslitsearch_konsolidiert_test
C:\Users\Philipp\syslitsearch\.venv\Scripts\python.exe -m pytest -q
C:\Users\Philipp\syslitsearch\.venv\Scripts\python.exe -m syslitsearch.review plan --config examples/review_config.retriever_new_run.json
```

3. Erst nach erfolgreichem Vergleich entscheiden, ob die drei entfallenen Altdateien aus dem Originalprojekt entfernt werden sollen. Die vorhandene `.env` und die Ergebnisse verbleiben im Original. Bei einem späteren Austausch nur **gezielt** Code-Dateien übertragen, keine ganze Projektstruktur spiegeln oder löschen.
4. Der neue Run darf erst nach Konfigurationsprüfung, Prüfung der API-/LLM-Zugänge und der Kostenbedingungen gestartet werden. Die Konfiguration ist ein begrenzter Pilot mit `max_records=100` je Datenbank, keine vollständige Systematic-Review-Suche.

## Verifikation dieses Lieferpakets

- Offline-Tests: 113 bestanden.
- `review plan`: funktioniert ohne Netzwerk.
- Keine neuen Datenbank- oder LLM-Aufrufe ausgeführt.
- Entfernte Altmodule liegen im **separaten** Rückfallarchiv, nicht in der aktiven Code-ZIP.
