"""Command line: python -m syslitsearch --keywords keywords.csv [--references references.csv] ..."""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from .query import load_keywords
from .references import load_references
from .report import write_report
from .search import run
from .sources import SOURCES
from .web import Http

REPO_ROOT = Path(__file__).resolve().parent.parent
KEY_VARIABLES = ('S2_API_KEY', 'SCOPUS_API_KEY', 'SCOPUS_INSTTOKEN', 'IEEE_API_KEY', 'DIMENSIONS_API_KEY')


def load_env(env_file: Path | None = None) -> list[Path]:
    """Read API keys from a .env file: the given one, else .env in the working directory and in the repo root.

    Variables already set in the environment are kept. Returns the files that were read.
    """
    candidates = [env_file] if env_file else [Path.cwd() / '.env', REPO_ROOT / '.env']
    read = []
    for path in dict.fromkeys(p.resolve() for p in candidates):
        if path.is_file():
            load_dotenv(path, override=False)
            read.append(path)
    return read


def dated(path: Path, now: datetime) -> Path:
    """Prefix the file name with the run date (yymmdd_), unless it already starts with six digits and '_'."""
    if re.match(r'\d{6}_', path.name):
        return path
    return path.with_name(f'{now:%y%m%d}_{path.name}')


def parse_years(text: str | None):
    if not text:
        return None
    a, _, b = text.partition('-')
    return int(a), int(b or a)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog='syslitsearch', description='Run a grouped search string in literature databases, '
                                'keep only hits whose title or abstract really contain it, and check reference papers.')
    p.add_argument('--keywords', type=Path, required=True, help='CSV with columns term, group (optional), id (optional)')
    p.add_argument('--references', type=Path, help='CSV with columns label, title, doi, arxiv_id (reference papers that must be found)')
    p.add_argument('--groups', help='comma-separated groups that form the search string (default: all groups of the keyword file)')
    p.add_argument('--sources', default='semantic_scholar', help=f'comma-separated databases: {", ".join(SOURCES)} (default: semantic_scholar)')
    p.add_argument('--years', help='publication years, e.g. 2023-2026 (default: no filter)')
    p.add_argument('--output', type=Path, help='Excel report; the file name gets the run date as prefix, e.g. 261012_full.xlsx '
                   '(default: results/<yymmdd>_syslitsearch_<hhmm>.xlsx)')
    p.add_argument('--exact-output', action='store_true', help='Use --output literally without a date prefix')
    p.add_argument('--no-per-keyword', action='store_true', help='skip the per-keyword counts and matrices (fewer API calls)')
    p.add_argument('--max-records', type=int, help='stop downloading after this many records per database')
    p.add_argument('--cache-dir', type=Path, default=Path('.cache'), help='cache for API responses (default: .cache)')
    p.add_argument('--no-cache', action='store_true', help='do not read or write the cache')
    p.add_argument('--env-file', type=Path, help='file with API keys (default: .env in the working directory or the repo root)')
    args = p.parse_args(argv)

    if args.env_file and not args.env_file.is_file():
        p.error(f'env file not found: {args.env_file}')
    env_files = load_env(args.env_file)
    keys = [k for k in KEY_VARIABLES if os.environ.get(k)]
    print(f'API keys set: {", ".join(keys) or "none"}' + (f' (read {", ".join(str(f) for f in env_files)})' if env_files else ''),
          flush=True)

    full = load_keywords(args.keywords)
    query = full.select([g.strip() for g in args.groups.split(',')] if args.groups else None)
    refs = load_references(args.references)
    names = [s.strip() for s in args.sources.split(',') if s.strip()]
    unknown = [n for n in names if n not in SOURCES]
    if unknown:
        p.error(f'unknown database(s): {", ".join(unknown)}; known: {", ".join(SOURCES)}')
    http = Http(None if args.no_cache else args.cache_dir)
    sources = [SOURCES[n](http) for n in names]
    years = parse_years(args.years)
    now = datetime.now()
    output_base = args.output or Path('results') / f'syslitsearch_{now:%H%M}.xlsx'
    output = output_base if args.exact_output else dated(output_base, now)

    print(f'{len(full.terms)} terms in {len(full.groups)} groups; search string uses groups {", ".join(query.names)}; '
          f'{len(refs)} reference papers; databases: {", ".join(s.label for s in sources)}', flush=True)
    settings = {'Keyword file': str(args.keywords), 'Reference file': str(args.references or '–'),
                'Groups in the search string': ', '.join(query.names), 'Databases': ', '.join(s.label for s in sources)}
    result = run(full, query, refs, sources, years, per_keyword=not args.no_per_keyword, max_records=args.max_records, settings=settings)
    settings['API responses'] = f'{http.calls} calls, {http.cache_hits} of them from the cache (fetched in an earlier run)'
    write_report(result, output)
    passed = sum(m.status == 'passed' for m in result.merged)
    no_abs = sum(m.status == 'no abstract' for m in result.merged)
    print(f'Report: {output} ({len(result.merged)} papers, {passed} on the reading list, {no_abs} without abstract; '
          f'{http.calls} API calls, {http.cache_hits} from cache)', flush=True)
    return 0 if all(r.status == 'ok' for r in result.sources) else 1


if __name__ == '__main__':
    sys.exit(main())
