"""Title/abstract screening of a search report, e.g. by Claude Code subagents.

python -m syslitsearch.screening <command> ...

  prepare  report -> batches of papers (blind to the reference labels) and one prompt per batch
  judge    let the model configured in .env (LLM_*) screen the batches of a run
  check    result files of a run against their batches
  build    report + results -> screening workbook (Verdict to revise by hand, Model verdict, Summary, Criteria)
  compare  two runs on the same batches (e.g. two models in a pilot) -> agreement workbook
  related  screening workbook -> excluded papers that use the terms of a CSV file

A run is a subfolder of the screening folder holding result_XX.jsonl, one JSON object per paper:
{"id": "R12", "verdict": "include" | "exclude" | "unsure", "reason": "...", "conflicts": true | false}
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import shutil
import sys
import textwrap
from collections import Counter
from datetime import date
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .llm import LLM, LLMError
from .references import load_references
from .report import _clean

VERDICTS = ('include', 'unsure', 'exclude')
FILL = {'include': 'C6EFCE', 'unsure': 'FFEB9C', 'exclude': 'E7E6E6'}
BOLD = Font(bold=True)
WRAP_TOP = Alignment(wrap_text=True, vertical='top')

PROMPT = """You are screening papers for a systematic literature review by title and abstract.

1. Read the screening criteria: {criteria}
2. Read ALL papers in: {batch}
   Each paper starts with "### <id>". Read the whole file; if it is too long for one Read call, read it in parts
   with offset/limit (e.g. limit 300 per call) until you reach the end.
3. Judge every paper strictly by the criteria, one at a time, from its own title and abstract only. Do not search
   the web, do not look anything up, and do not read any other files.
4. Write the result with the Write tool to: {result}
   Exactly one JSON object per line and exactly one line per paper id, in the format given in the criteria,
   nothing else in the file.
5. Reply only with: the number of papers judged and the counts per verdict. Do not repeat the judgments.
"""

JUDGE_SYSTEM = ('You screen papers for a systematic literature review by title and abstract only. Apply the following '
                'criteria strictly and judge every paper on its own.\n\n<criteria>\n{criteria}\n</criteria>\n\n'
                'Answer with exactly one JSON object per paper, one object per line (JSON Lines), in the output format of '
                'the criteria: {{"id": ..., "verdict": "include" | "exclude" | "unsure", "reason": ..., "conflicts": true | false}}. '
                'Write nothing else: no code fences, no comments.')
JUDGE_USER = 'Judge these {n} papers (ids: {ids}).\n\n{papers}'

# --- input: papers of a search report ---------------------------------------------------------

def load_papers(report: Path) -> list[dict]:
    """Papers of the sheets "Reading list" (ids R1, R2, ...) and "No abstract" (N1, N2, ...)."""
    wb = openpyxl.load_workbook(report, read_only=True)
    papers = []
    for sheet, prefix in (('Reading list', 'R'), ('No abstract', 'N')):
        if sheet not in wb.sheetnames:
            continue
        rows = wb[sheet].iter_rows(values_only=True)
        header = next(rows)
        for r in rows:
            d = dict(zip(header, r))
            if not d.get('Title'):
                continue
            papers.append({'id': f'{prefix}{d["#"]}', 'title': d['Title'], 'year': d.get('Year'),
                           'venue': d.get('Venue') or '', 'venue_type': d.get('Venue type') or '',
                           'databases': d.get('Databases') or '', 'reference': d.get('Reference') or '',
                           'doi': d.get('DOI') or '', 'arxiv': d.get('arXiv') or '', 'url': d.get('URL') or '',
                           'abstract': d.get('Abstract') or '', 'sheet': sheet})
    return papers


def criteria_labels(criteria: str) -> tuple[str, ...]:
    """Reason labels defined in the criteria, written as "Label:" in quotes."""
    return tuple(dict.fromkeys(re.findall(r'"([A-Z][A-Za-z/ -]+):"', criteria)))


# --- immutable input provenance ---------------------------------------------------------------

def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _input_manifest(out: Path) -> dict:
    path = out / 'input_manifest.json'
    if not path.is_file():
        raise ValueError(f'Missing input_manifest.json in {out}; legacy screening must be migrated or rerun.')
    return json.loads(path.read_text(encoding='utf-8'))


def _verify_inputs(out: Path, report: Path | None = None) -> dict:
    manifest = _input_manifest(out)
    files = manifest['files']
    for name, expected in files.items():
        actual = out / name
        if not actual.is_file() or _sha256(actual) != expected:
            raise ValueError(f'Screening input changed or missing: {name}; stop to avoid invalid judgments.')
    if report is not None:
        if _sha256(report) != manifest['report_sha256']:
            raise ValueError('Search report differs from the one used at prepare; BUILD aborted.')
        if [p['id'] for p in load_papers(report)] != manifest['all_report_ids']:
            raise ValueError('Paper identities in the search report changed; BUILD aborted.')
    return manifest


def _bind_run(out: Path, run: str) -> None:
    manifest = _input_manifest(out)
    signature = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    path = out / run / 'input_signature.json'
    if path.exists():
        old = json.loads(path.read_text(encoding='utf-8'))
        if old.get('signature') != signature:
            raise ValueError('Run input signature differs from prepared inputs; refusing reuse.')
    else:
        if list((out / run).glob('result_*.jsonl')):
            raise ValueError('Existing results without input signature; refusing unsafe reuse.')
        path.write_text(json.dumps({'signature': signature}, indent=2), encoding='utf-8')

# --- prepare -----------------------------------------------------------------------------------

def prepare(report: Path, out: Path, criteria: Path, run: str, size: int = 100, pilot: int | None = None,
            seed: int = 42) -> list[Path]:
    """Write the batches, the ids, a copy of the criteria and one prompt per batch; returns the batch files.

    pilot: screen only the reference papers, up to 3 papers without abstract and this many random others.
    """
    if out.exists() and any(out.iterdir()):
        raise ValueError(f'Screening folder is not empty: {out}. Use a new folder for prepare.')
    if size < 1:
        raise ValueError('Batch size must be >= 1')
    all_papers = load_papers(report)
    papers = all_papers
    if pilot is not None:
        rng = random.Random(seed)
        refs = [p for p in papers if p['reference']]
        no_abs = [p for p in papers if p['sheet'] == 'No abstract']
        others = [p for p in papers if not p['reference'] and p['sheet'] == 'Reading list']
        papers = refs + rng.sample(no_abs, min(3, len(no_abs))) + rng.sample(others, min(pilot, len(others)))
        rng.shuffle(papers)
    out.mkdir(parents=True, exist_ok=True)
    (out / run).mkdir(exist_ok=True)
    (out / 'prompts').mkdir(exist_ok=True)
    shutil.copyfile(criteria, out / 'criteria.md')
    (out / 'ids.json').write_text(json.dumps([p['id'] for p in papers]), encoding='utf-8')
    (out / 'source.json').write_text(json.dumps({'report': str(report.resolve()), 'created': date.today().isoformat(),
                                                 'papers': len(papers), 'pilot': pilot}), encoding='utf-8')
    batches = []
    for b in range(0, len(papers), size):
        n = f'{b // size + 1:02d}'
        lines = []
        for p in papers[b:b + size]:  # the reference label stays out: the judge screens blind
            lines += [f'### {p["id"]}', f'Title: {p["title"]}', f'Year: {p["year"]} | Venue: {p["venue"]}']
            lines += textwrap.wrap('Abstract: ' + (p['abstract'] or '(no abstract)'), 400) + ['']
        batch = out / f'batch_{n}.txt'
        batch.write_text('\n'.join(lines), encoding='utf-8')
        prompt = PROMPT.format(criteria=(out / 'criteria.md').resolve(), batch=batch.resolve(),
                               result=(out / run / f'result_{n}.jsonl').resolve())
        (out / 'prompts' / f'batch_{n}.md').write_text(prompt, encoding='utf-8')
        batches.append(batch)
    tracked = ['criteria.md', 'ids.json', 'source.json'] + [p.name for p in batches]
    manifest = {'schema': 1, 'report_sha256': _sha256(report),
                'all_report_ids': [p['id'] for p in all_papers],
                'selected_ids': [p['id'] for p in papers],
                'files': {name: _sha256(out / name) for name in tracked}}
    (out / 'input_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    _bind_run(out, run)
    return batches


# --- results -----------------------------------------------------------------------------------

def load_results(out: Path, run: str) -> tuple[dict[str, dict], list[str]]:
    """Judgments of a run by paper id, and the problems found while reading them."""
    results, problems = {}, []
    for f in sorted((out / run).glob('result_*.jsonl')):
        for n, line in enumerate(f.read_text(encoding='utf-8').splitlines(), 1):
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                problems.append(f'{f.name}:{n} not JSON')
                continue
            if r.get('verdict') not in VERDICTS:
                problems.append(f'{f.name}:{n} verdict {r.get("verdict")!r}')
            if r.get('id') in results:
                problems.append(f'{f.name}:{n} duplicate id {r.get("id")}')
            results[r.get('id')] = r
    return results, problems


def check(out: Path, run: str) -> list[str]:
    """One line per batch: ok, no result yet, or what is wrong."""
    if (out / 'input_manifest.json').exists():
        _verify_inputs(out)
        _bind_run(out, run)
    labels = criteria_labels((out / 'criteria.md').read_text(encoding='utf-8'))
    report = []
    for batch in sorted(out.glob('batch_*.txt')):
        n = batch.stem.split('_')[1]
        ids = re.findall(r'^### (\S+)$', batch.read_text(encoding='utf-8'), re.M)
        res = out / run / f'result_{n}.jsonl'
        if not res.exists():
            report.append(f'{n}: no result yet')
            continue
        got, bad = [], []
        for k, line in enumerate(res.read_text(encoding='utf-8').splitlines(), 1):
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                bad.append(f'line {k} not JSON')
                continue
            got.append(r.get('id'))
            if r.get('verdict') not in VERDICTS:
                bad.append(f'{r.get("id")} verdict {r.get("verdict")!r}')
            elif labels and r['verdict'] != 'include' and not str(r.get('reason', '')).startswith(labels):
                bad.append(f'{r.get("id")} reason without label')
        missing, extra = sorted(set(ids) - set(got)), sorted(set(got) - set(ids))
        dup = len(got) - len(set(got))
        ok = not (missing or extra or dup or bad)
        report.append(f'{n}: {"ok" if ok else "PROBLEM"} ({len(got)}/{len(ids)})'
                      + (f' missing {missing[:5]}' if missing else '') + (f' extra {extra[:5]}' if extra else '')
                      + (f' duplicates {dup}' if dup else '') + (f' {bad[:5]}' if bad else ''))
    return report


# --- judge -------------------------------------------------------------------------------------

def batch_papers(text: str) -> list[tuple[str, str]]:
    """(id, text block) of every paper in a batch file."""
    blocks = re.split(r'^(?=### \S+$)', text, flags=re.M)
    return [(b.split('\n', 1)[0][4:].strip(), b.strip()) for b in blocks if b.startswith('### ')]


def parse_judgments(text: str, ids: set[str]) -> dict[str, dict]:
    """Judgments in a model answer (JSON Lines, also inside code fences or as one JSON array), by paper id."""
    candidates = []
    try:
        whole = json.loads(text.strip().removeprefix('```json').removeprefix('```').removesuffix('```'))
        candidates = whole if isinstance(whole, list) else [whole]
    except json.JSONDecodeError:
        for line in text.splitlines():
            line = line.strip().rstrip(',')
            if line.startswith('{'):
                try:
                    candidates.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    found = {}
    for c in candidates:
        if not isinstance(c, dict) or str(c.get('id')) not in ids:
            continue
        verdict = str(c.get('verdict', '')).strip().lower()
        conflicts = c.get('conflicts')
        found[str(c['id'])] = {'id': str(c['id']), 'verdict': verdict, 'reason': str(c.get('reason', '')).strip(),
                               'conflicts': conflicts is True or str(conflicts).lower() == 'true'}
    return found


def _ask(llm: LLM, system: str, chunk: list[tuple[str, str]], log) -> dict[str, dict]:
    ids = [i for i, _ in chunk]
    user = JUDGE_USER.format(n=len(chunk), ids=', '.join(ids), papers='\n\n'.join(t for _, t in chunk))
    try:
        return parse_judgments(llm.complete(system, user), set(ids))
    except LLMError as e:
        log(f'  request for {ids[0]}..{ids[-1]} failed: {str(e)[:200]}')
        return {}


def judge(out: Path, run: str, llm: LLM, per_request: int = 20, only: list[str] | None = None, force: bool = False,
          log=print) -> dict:
    """Screen the batches of a run with the model; papers without a usable answer are asked again once,
    on their own. A batch whose result file already covers all its papers is skipped unless force is set."""
    if (out / 'input_manifest.json').exists():
        _verify_inputs(out)
    system = JUDGE_SYSTEM.format(criteria=(out / 'criteria.md').read_text(encoding='utf-8'))
    (out / run).mkdir(parents=True, exist_ok=True)
    if (out / 'input_manifest.json').exists():
        _bind_run(out, run)
    judge_meta = out / run / 'judge.json'
    if judge_meta.exists() and list((out / run).glob('result_*.jsonl')):
        previous = json.loads(judge_meta.read_text(encoding='utf-8'))
        if previous.get('judge') != llm.describe() or previous.get('papers_per_request') != per_request:
            raise ValueError('Judge settings differ from the existing run; use a new run name.')
    else:
        judge_meta.write_text(json.dumps({'judge': llm.describe(), 'papers_per_request': per_request,
                                          'date': date.today().isoformat()}, indent=1), encoding='utf-8')
    total = judged_total = 0
    for batch in sorted(out.glob('batch_*.txt')):
        n = batch.stem.split('_')[1]
        if only and n not in only:
            continue
        papers = batch_papers(batch.read_text(encoding='utf-8'))
        total += len(papers)
        result = out / run / f'result_{n}.jsonl'
        if result.exists() and not force:
            done, _ = load_results(out, run)
            if all(i in done for i, _ in papers):
                log(f'batch {n}: already judged, skipped')
                judged_total += len(papers)
                continue
        judged: dict[str, dict] = {}
        for k in range(0, len(papers), per_request):
            judged.update(_ask(llm, system, papers[k:k + per_request], log))
        missing = [p for p in papers if p[0] not in judged or judged[p[0]]['verdict'] not in VERDICTS]
        for p in missing:
            judged.update(_ask(llm, system, [p], log))
        lines = [json.dumps(judged[i], ensure_ascii=False) for i, _ in papers if i in judged]
        result.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        counts = Counter(j['verdict'] for j in judged.values())
        judged_total += len(judged)
        log(f'batch {n}: {len(judged)}/{len(papers)} judged ({", ".join(f"{v} {counts[v]}" for v in VERDICTS)}); '
            f'{llm.calls} requests, {llm.cache_hits} from cache, {llm.input_tokens} input / {llm.output_tokens} output tokens')
    return {'papers': total, 'judged': judged_total, 'requests': llm.calls, 'cache_hits': llm.cache_hits,
            'input_tokens': llm.input_tokens, 'output_tokens': llm.output_tokens}


def _label(r: dict) -> str:
    reason = r.get('reason', '')
    return reason.split(':')[0] if ':' in reason[:40] else '(no label)'


def _lines(ws, lines: list[tuple[str, bool]]) -> None:
    for text, bold in lines:
        ws.append([text])
        if bold:
            ws.cell(ws.max_row, 1).font = BOLD
        ws.cell(ws.max_row, 1).alignment = WRAP_TOP
    ws.column_dimensions['A'].width = 130


def _criteria_sheet(wb, criteria: Path) -> None:
    ws = wb.create_sheet('Criteria')
    for line in criteria.read_text(encoding='utf-8').splitlines():
        ws.append([line])
    ws.column_dimensions['A'].width = 130


def _reference_labels(references: Path | None) -> set[str] | None:
    return {r.label for r in load_references(references)} if references else None


# --- build -------------------------------------------------------------------------------------

def build(out: Path, run: str, report: Path, output: Path, model: str | None = None, references: Path | None = None,
          screened_on: str | None = None) -> dict:
    """Screening workbook; returns the verdict counts. "Verdict" starts as the model verdict and is meant
    to be revised by hand; "Model verdict" keeps the original. model defaults to the judge settings of the run."""
    if (out / 'input_manifest.json').exists():
        _verify_inputs(out, report)
        _bind_run(out, run)
    ids = json.loads((out / 'ids.json').read_text(encoding='utf-8'))
    meta = out / run / 'judge.json'
    if model is None and meta.exists():
        j = json.loads(meta.read_text(encoding='utf-8'))
        model = f'{j["judge"]["model"]} via {j["judge"]["style"]} API ({j["papers_per_request"]} papers per request)'
        screened_on = screened_on or j.get('date')
    model = model or 'unknown'
    results, problems = load_results(out, run)
    papers = {p['id']: p for p in load_papers(report)}
    ref_labels = _reference_labels(references)
    missing = [i for i in ids if i not in results]
    extra = [i for i in results if i not in set(ids)]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Screening'
    cols = ['ID', 'Verdict', 'Reason', 'Mentions conflicts/updates', 'Reference', 'Title', 'Year', 'Venue', 'Venue type',
            'Databases', 'Abstract', 'DOI', 'arXiv', 'URL', 'Sheet in report', 'Model verdict']
    ws.append(cols)
    for c in ws[1]:
        c.font = BOLD
    order = {v: k for k, v in enumerate(VERDICTS)}
    for i in sorted(ids, key=lambda i: (order.get(results.get(i, {}).get('verdict'), 3), i[0], int(i[1:]))):
        p, r = papers[i], results.get(i, {})
        verdict = r.get('verdict', 'MISSING')
        ws.append([_clean(v) for v in [i, verdict, r.get('reason', ''), 'yes' if r.get('conflicts') else '', p['reference'],
                                       p['title'], p['year'], p['venue'], p['venue_type'], p['databases'], p['abstract'],
                                       p['doi'], p['arxiv'], p['url'], p['sheet'], verdict]])
        if verdict in FILL:
            ws.cell(ws.max_row, 2).fill = PatternFill('solid', start_color=FILL[verdict], end_color=FILL[verdict])
    for k, w in enumerate([8, 10, 60, 12, 18, 60, 7, 30, 12, 22, 80, 22, 12, 30, 12, 12], 1):
        ws.column_dimensions[get_column_letter(k)].width = w
    for row in ws.iter_rows(min_row=2):
        for c in (row[2], row[5]):
            c.alignment = WRAP_TOP
    ws.freeze_panes = 'C2'
    ws.auto_filter.ref = ws.dimensions

    verdicts = Counter(results[i]['verdict'] for i in ids if i in results)
    refs = [i for i in ids if papers[i]['reference'] and (ref_labels is None or papers[i]['reference'] in ref_labels)]
    ref_verdicts = Counter(results.get(i, {}).get('verdict', 'MISSING') for i in refs)
    source = json.loads((out / 'source.json').read_text(encoding='utf-8')) if (out / 'source.json').exists() else {}
    labels = Counter((results[i]['verdict'], _label(results[i])) for i in ids
                     if i in results and results[i]['verdict'] != 'include')
    lines = [
        ('Title and abstract screening', True),
        (f'Screening run: {screened_on or date.today().isoformat()}', False),
        (f'Papers: {len(ids)}' + (f' (pilot sample: reference papers, up to 3 without abstract, {source["pilot"]} random others)'
                                  if source.get('pilot') is not None else ' (reading list + papers without abstract)'), False),
        (f'Source report: {report.name}', False),
        (f'Screened by: {model}, title and abstract only, blind to the reference labels; criteria in sheet "Criteria"', False),
        ('', False),
        ('Verdicts', True),
        *[(f'{v}: {verdicts.get(v, 0)}', False) for v in VERDICTS],
        ('Reasons by label (exclude and unsure)', True),
        *[(f'{v} / {lab}: {n}', False) for (v, lab), n in sorted(labels.items())],
        (f'Abstract mentions conflicts/updates: {sum(bool(results[i].get("conflicts")) for i in ids if i in results)}', False),
        ('', False),
        ('Check against the reference papers (must all be include)', True),
        (f'{len(refs)} reference papers: ' + ', '.join(f'{k} {v}' for k, v in ref_verdicts.most_common()), False),
        *[(f'  {papers[i]["reference"]}: {results.get(i, {}).get("verdict", "MISSING")} - {results.get(i, {}).get("reason", "")}', False)
          for i in refs if results.get(i, {}).get('verdict') != 'include'],
    ]
    if missing or extra or problems:
        lines += [('', False), ('Problems', True), (f'missing ids: {missing}', False), (f'unknown ids: {extra}', False),
                  *[(p, False) for p in problems]]
    _lines(wb.create_sheet('Summary'), lines)
    _criteria_sheet(wb, out / 'criteria.md')
    output.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output)
    return {'papers': len(ids), **{v: verdicts.get(v, 0) for v in VERDICTS}, 'missing': len(missing),
            'problems': len(problems) + len(extra), 'references': dict(ref_verdicts)}


# --- compare -----------------------------------------------------------------------------------

def compare(out: Path, run_a: str, label_a: str, run_b: str, label_b: str, report: Path, output: Path,
            references: Path | None = None) -> dict:
    """Agreement of two runs on the same papers (same verdict, Cohen's kappa, keep/drop decision)."""
    ids = json.loads((out / 'ids.json').read_text(encoding='utf-8'))
    a, _ = load_results(out, run_a)
    b, _ = load_results(out, run_b)
    papers = {p['id']: p for p in load_papers(report)}
    ref_labels = _reference_labels(references)
    va = {i: a.get(i, {}).get('verdict', 'MISSING') for i in ids}
    vb = {i: b.get(i, {}).get('verdict', 'MISSING') for i in ids}
    n = len(ids)
    agree = sum(va[i] == vb[i] for i in ids)
    pa, pb = Counter(va.values()), Counter(vb.values())
    pe = sum(pa[v] * pb[v] for v in VERDICTS) / n / n if n else 0
    kappa = (agree / n - pe) / (1 - pe) if n and pe < 1 else 1.0
    keep = sum((va[i] == 'exclude') == (vb[i] == 'exclude') for i in ids)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Comparison'
    ws.append(['ID', 'Same verdict', f'{label_a}: verdict', f'{label_a}: reason', f'{label_b}: verdict',
               f'{label_b}: reason', 'Reference', 'Title', 'Year', 'Venue', 'Abstract', 'URL'])
    for c in ws[1]:
        c.font = BOLD
    for i in sorted(ids, key=lambda i: (va[i] == vb[i], i)):
        p = papers[i]
        ws.append([_clean(v) for v in [i, 'yes' if va[i] == vb[i] else 'NO', va[i], a.get(i, {}).get('reason', ''), vb[i],
                                       b.get(i, {}).get('reason', ''), p['reference'], p['title'], p['year'], p['venue'],
                                       p['abstract'], p['url']]])
        for col, v in ((3, va[i]), (5, vb[i])):
            if v in FILL:
                ws.cell(ws.max_row, col).fill = PatternFill('solid', start_color=FILL[v], end_color=FILL[v])
    for k, w in enumerate([8, 8, 10, 50, 10, 50, 16, 55, 7, 25, 80, 30], 1):
        ws.column_dimensions[get_column_letter(k)].width = w
    ws.freeze_panes = 'C2'
    ws.auto_filter.ref = ws.dimensions

    refs = [i for i in ids if papers[i]['reference'] and (ref_labels is None or papers[i]['reference'] in ref_labels)]
    _lines(wb.create_sheet('Agreement'), [
        ('Comparison of two screening runs', True),
        (f'Date: {date.today().isoformat()}; {n} papers; source report {report.name}; criteria in sheet "Criteria"', False),
        (f'Same verdict: {agree} of {n} ({agree / n:.0%}); Cohen\'s kappa {kappa:.2f}' if n else 'no papers', False),
        (f'Same keep/drop decision (include or unsure vs. exclude): {keep} of {n}', False),
        (f'Verdicts (rows: {label_a}, columns: {label_b})', True),
        ('               ' + ''.join(f'{v:>10}' for v in VERDICTS), False),
        *[(f'{x:>13}  ' + ''.join(f'{sum(va[i] == x and vb[i] == y for i in ids):>10}' for y in VERDICTS), False) for x in VERDICTS],
        (f'Reference papers ({len(refs)}, must be include)', True),
        (f'{label_a}: ' + ', '.join(f'{k} {v}' for k, v in Counter(va[i] for i in refs).most_common()), False),
        (f'{label_b}: ' + ', '.join(f'{k} {v}' for k, v in Counter(vb[i] for i in refs).most_common()), False),
    ])
    _criteria_sheet(wb, out / 'criteria.md')
    output.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output)
    return {'papers': n, 'agree': agree, 'kappa': round(kappa, 2), 'keep_drop_agree': keep}


# --- related work ------------------------------------------------------------------------------

def load_terms(path: Path) -> list[dict]:
    """Terms for `related`: a CSV with name, pattern (regex, case-insensitive) and fields ("title abstract" or "title")."""
    terms = []
    for row in csv.DictReader(open(path, encoding='utf-8-sig')):
        fields = (row.get('fields') or 'title abstract').split()
        if not row.get('name') or not row.get('pattern') or not set(fields) <= {'title', 'abstract'}:
            raise ValueError(f'{path}: every row needs name, pattern and fields (title and/or abstract): {row}')
        terms.append({'name': row['name'], 're': re.compile(row['pattern'], re.I), 'fields': fields})
    if not terms:
        raise ValueError(f'{path}: no terms')
    return terms


def related(screening: Path, output: Path, terms_file: Path, skip_reasons: tuple[str, ...] = ()) -> int:
    """Excluded papers (by the model verdict) whose title or abstract uses one of the terms in terms_file; a lexical
    pre-selection for background reading. Papers whose reason starts with one of skip_reasons are left out."""
    terms = load_terms(terms_file)
    ws = openpyxl.load_workbook(screening, read_only=True)['Screening']
    rows = ws.iter_rows(values_only=True)
    header = next(rows)
    found = []
    for r in rows:
        d = dict(zip(header, r))
        verdict = d.get('Model verdict') or d.get('Verdict')
        if verdict != 'exclude' or any(str(d.get('Reason') or '').startswith(x) for x in skip_reasons):
            continue
        texts = {'title': d.get('Title') or '', 'abstract': d.get('Abstract') or ''}
        hits = []
        for t in terms:
            where = [f for f in t['fields'] if t['re'].search(texts[f])]
            if where:
                hits.append(f'{t["name"]} ({"+".join(where)})')
        if hits:
            found.append((d, hits))
    found.sort(key=lambda x: (-len(x[1]), str(x[0].get('Reason')).split(':')[0], x[0].get('Title') or ''))

    wb = openpyxl.Workbook()
    out = wb.active
    out.title = 'Related work'
    cols = ['ID', 'Title', 'Matched terms', 'Exclusion reason', 'Mentions conflicts/updates', 'Year', 'Venue', 'Databases',
            'Abstract', 'DOI', 'arXiv', 'URL']
    out.append(cols)
    for c in out[1]:
        c.font = BOLD
    for d, hits in found:
        out.append([_clean(v) for v in [d.get('ID'), d.get('Title'), '; '.join(hits), d.get('Reason'),
                                        d.get('Mentions conflicts/updates'), d.get('Year'), d.get('Venue'), d.get('Databases'),
                                        d.get('Abstract'), d.get('DOI'), d.get('arXiv'), d.get('URL')]])
    for k, w in enumerate([8, 60, 35, 60, 12, 7, 28, 22, 80, 22, 12, 30], 1):
        out.column_dimensions[get_column_letter(k)].width = w
    for row in out.iter_rows(min_row=2):
        for c in (row[1], row[2], row[3]):
            c.alignment = WRAP_TOP
    out.freeze_panes = 'C2'
    out.auto_filter.ref = out.dimensions
    _lines(wb.create_sheet('About'), [
        (f'Related work candidates from {screening.name}', True),
        (f'{len(found)} excluded papers whose title or abstract contains a term from {terms_file.name}: '
         f'{", ".join(t["name"] for t in terms)}'
         + (f' (reasons left out: {", ".join(skip_reasons)})' if skip_reasons else '')
         + '. Lexical pre-selection for background reading, not a screening verdict.', False),
    ])
    output.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output)
    return len(found)


# --- command line ------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog='python -m syslitsearch.screening', description=__doc__.split('\n\n')[0])
    sub = p.add_subparsers(dest='command', required=True)

    s = sub.add_parser('prepare', help='write batches and prompts for a screening run')
    s.add_argument('--report', type=Path, required=True, help='search report (sheets "Reading list" and "No abstract")')
    s.add_argument('--out', type=Path, required=True, help='screening folder, e.g. results/screening/261012_full')
    s.add_argument('--criteria', type=Path, required=True, help='screening criteria (Markdown), e.g. examples/screening_criteria.md')
    s.add_argument('--run', default='run1', help='name of the run folder for the results (default: run1)')
    s.add_argument('--size', type=int, default=100, help='papers per batch (default: 100)')
    s.add_argument('--pilot', type=int, help='pilot: reference papers + up to 3 without abstract + this many random others')
    s.add_argument('--seed', type=int, default=42, help='random seed of the pilot sample (default: 42)')

    s = sub.add_parser('judge', help='screen the batches with the model configured in .env (LLM_*)')
    s.add_argument('--out', type=Path, required=True)
    s.add_argument('--run', default='run1')
    s.add_argument('--papers-per-request', type=int, default=20, help='papers sent in one request (default: 20)')
    s.add_argument('--batches', help='only these batches, e.g. 01,02 (default: all)')
    s.add_argument('--force', action='store_true', help='judge batches again that already have a complete result')
    s.add_argument('--no-cache', action='store_true', help='do not read or write cached answers')
    s.add_argument('--env-file', type=Path, help='file with the LLM_* settings (default: .env)')

    s = sub.add_parser('check', help='check the result files of a run')
    s.add_argument('--out', type=Path, required=True)
    s.add_argument('--run', default='run1')

    s = sub.add_parser('build', help='write the screening workbook')
    s.add_argument('--out', type=Path, required=True)
    s.add_argument('--run', default='run1')
    s.add_argument('--report', type=Path, required=True)
    s.add_argument('--output', type=Path, required=True, help='screening workbook (.xlsx)')
    s.add_argument('--model', help='who screened, e.g. "Claude subagents (Sonnet 5.5)" (default: the judge settings of the run)')
    s.add_argument('--references', type=Path, help='reference CSV: only these labels count as references')
    s.add_argument('--screened-on', help='date of the screening run (default: today)')

    s = sub.add_parser('compare', help='compare two runs on the same batches')
    s.add_argument('--out', type=Path, required=True)
    s.add_argument('--run-a', required=True)
    s.add_argument('--label-a', required=True)
    s.add_argument('--run-b', required=True)
    s.add_argument('--label-b', required=True)
    s.add_argument('--report', type=Path, required=True)
    s.add_argument('--output', type=Path, required=True)
    s.add_argument('--references', type=Path)

    s = sub.add_parser('related', help='list excluded papers whose title or abstract uses given terms')
    s.add_argument('--screening', type=Path, required=True, help='screening workbook')
    s.add_argument('--terms', type=Path, required=True, help='CSV: name, pattern, fields (see examples/related_terms.csv)')
    s.add_argument('--skip-reason', action='append', default=[], help='leave out exclusions whose reason starts with this')
    s.add_argument('--output', type=Path, required=True)

    a = p.parse_args(argv)
    if a.command == 'prepare':
        batches = prepare(a.report, a.out, a.criteria, a.run, a.size, a.pilot, a.seed)
        print(f'{len(batches)} batches in {a.out}; prompts in {a.out / "prompts"}; results go to {a.out / a.run}')
    elif a.command == 'judge':
        from .cli import load_env
        if a.env_file and not a.env_file.is_file():
            p.error(f'env file not found: {a.env_file}')
        load_env(a.env_file)
        try:
            llm = LLM.from_env(None if a.no_cache else Path('.cache') / 'llm')
        except ValueError as e:
            p.error(f'{e} (see .env.example)')
        d = llm.describe()
        print(f'judge: {d["model"]} via {d["style"]} API' + (f' at {d["base_url"]}' if d['base_url'] else '')
              + f'; API key {"set" if llm.api_key else "not set"}', flush=True)
        only = [b.strip().zfill(2) for b in a.batches.split(',')] if a.batches else None
        print(judge(a.out, a.run, llm, a.papers_per_request, only, a.force, log=lambda m: print(m, flush=True)))
    elif a.command == 'check':
        lines = check(a.out, a.run)
        print('\n'.join(lines))
        print(f'{sum(l.split(": ")[1].startswith("ok") for l in lines)} of {len(lines)} batches ok')
    elif a.command == 'build':
        print(f'{a.output}: {build(a.out, a.run, a.report, a.output, a.model, a.references, a.screened_on)}')
    elif a.command == 'compare':
        print(f'{a.output}: {compare(a.out, a.run_a, a.label_a, a.run_b, a.label_b, a.report, a.output, a.references)}')
    elif a.command == 'related':
        print(f'{a.output}: {related(a.screening, a.output, a.terms, tuple(a.skip_reason))} related-work candidates')
    return 0


if __name__ == '__main__':
    sys.exit(main())
