"""IntroLab command-line entry point (Python standard library only)."""
import argparse
from contextlib import closing
import json
import os
import sys
import sqlite3
from pathlib import Path

from .crossref import fetch_doi, normalize_doi, search_works, to_record
from .render import citation, draft, research_prompt
from .store import add_claim, connect, export_data, mark_checked, record_search, review_claim, upsert_paper
from . import workflow
from .workflow_cli import register, dispatch

DEFAULT_DB = ".introlab/research.sqlite3"


def parser():
    p = argparse.ArgumentParser(prog="introlab", description="Evidence-first introduction research")
    p.add_argument("--db", default=os.environ.get("INTROLAB_DB", DEFAULT_DB), help="SQLite database path")
    commands = p.add_subparsers(dest="command", required=True)
    register(commands)
    commands.add_parser("init", help="Create local project database")

    discover = commands.add_parser("discover", help="Fetch one journal/topic batch from Crossref")
    discover.add_argument("query")
    discover.add_argument("--journal", required=True, help="Crossref container title, e.g. Journal of the American Chemical Society")
    discover.add_argument("--rows", type=int, default=10)
    discover.add_argument("--offset", type=int, default=0)
    discover.add_argument("--from-year", type=int)
    discover.add_argument("--to-year", type=int)

    paper = commands.add_parser("paper", help="Manage DOI metadata and checks")
    paper_cmds = paper.add_subparsers(dest="operation", required=True)
    paper_add = paper_cmds.add_parser("add")
    paper_add.add_argument("doi")
    paper_cmds.add_parser("list")
    paper_check = paper_cmds.add_parser("check")
    paper_check.add_argument("doi")
    paper_check.add_argument("--kind", required=True, choices=["publisher", "followup"])
    paper_check.add_argument("--note", required=True, help="Human-reviewed URL, details and date / literature checked")

    claim = commands.add_parser("claim", help="Record a source-linked mechanistic claim")
    claim_cmds = claim.add_subparsers(dest="operation", required=True)
    claim_add = claim_cmds.add_parser("add")
    claim_add.add_argument("doi")
    claim_add.add_argument("statement")
    claim_add.add_argument("--locator", required=True, help="e.g. Figure 3, page 7 or SI Table S1")
    claim_add.add_argument("--evidence", required=True, help="Brief verbatim excerpt or faithful source note")
    claim_review = claim_cmds.add_parser("review")
    claim_review.add_argument("id", type=int)
    claim_review.add_argument("--decision", required=True, choices=["supported", "refuted", "uncertain"])
    claim_review.add_argument("--note", default="")
    claim_cmds.add_parser("list")

    gap = commands.add_parser("gap", help="Store unresolved mechanistic questions")
    gap_cmds = gap.add_subparsers(dest="operation", required=True)
    gap_add = gap_cmds.add_parser("add")
    gap_add.add_argument("question")
    gap_add.add_argument("--dois", nargs="*", default=[], help="Relevant registered DOIs")
    gap_cmds.add_parser("list")
    ga = gap_cmds.add_parser('assess')
    ga.add_argument('id', type=int)
    ga.add_argument('file')

    prompt = commands.add_parser("prompt", help="Export prompt for ChatGPT web browsing")
    prompt.add_argument("--topic", required=True)
    prompt.add_argument("--journal", required=True)
    prompt.add_argument("--out", default="chatgpt_research_prompt.md")

    draft_cmd = commands.add_parser("draft", help="Export reviewed evidence notes and references")
    draft_cmd.add_argument("--title", default="Introduction 초안")
    draft_cmd.add_argument("--out", default="introduction_notes.md")
    draft_cmd.add_argument('--notes', action='store_true', help='Legacy evidence notes')
    bib = commands.add_parser("bibliography", help="Print JACS-like references")
    bib.add_argument("--reviewed-only", action="store_true")

    exp = commands.add_parser("export", help="Export portable project JSON for future modules")
    exp.add_argument("--out", default="introlab_export.json")
    exp.add_argument('--resultlab', action='store_true')
    return p


def write_text(path, text):
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    print(f"Written: {output.resolve()}")


def main(argv=None):
    # Frozen Windows programs otherwise emit legacy code pages when redirected.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure') and not stream.isatty():
            stream.reconfigure(encoding='utf-8')
    args = parser().parse_args(argv)
    try:
        with closing(connect(args.db)) as db:
            if dispatch(args, db, write_text):
                pass
            elif args.command == "init":
                print(f"Initialized: {Path(args.db).resolve()}")
            elif args.command == "discover":
                if args.from_year and args.to_year and args.from_year > args.to_year:
                    raise ValueError("--from-year must not exceed --to-year")
                try:
                    items = search_works(args.query, args.journal, args.rows, args.offset, args.from_year, args.to_year)
                    records = [to_record(item) for item in items]
                except (ValueError, RuntimeError, OSError, KeyError, TypeError) as exc:
                    record_search(db, args, 0, status='failed', note=str(exc))
                    raise
                added = 0
                for record in records:
                    if db.execute('SELECT 1 FROM papers WHERE doi=?', (record['doi'],)).fetchone():
                        continue
                    upsert_paper(db, record)
                    added += 1
                    print(f"{record['doi']} | {record['year']} | {record['title']}")
                record_search(db, args, len(items), [r['doi'] for r in records])
                print(f"Stored {added} new Crossref candidates; existing DOIs skipped; no web-browsing completion implied.")
            elif args.command == "paper":
                if args.operation == "add":
                    record = to_record(fetch_doi(args.doi))
                    upsert_paper(db, record)
                    print(f"Crossref metadata stored: {record['doi']} | {record['title']}")
                elif args.operation == "check":
                    doi = normalize_doi(args.doi)
                    mark_checked(db, doi, args.kind, args.note)
                    print(f"Recorded human {args.kind} review: {doi}")
                else:
                    for row in db.execute("SELECT * FROM papers ORDER BY year DESC,doi"):
                        flags = (
                            ("M" if row['metadata_verified'] else "-") +
                            ("P" if row["publisher_checked_at"] else "-") +
                            ("F" if row["followup_checked_at"] else "-")
                        )
                        print(f"[{flags}] {row['doi']} | {row['year']} | {row['title']}")
            elif args.command == "claim":
                if args.operation == "add":
                    doi = normalize_doi(args.doi)
                    cid = add_claim(db, doi, args.statement, args.locator, args.evidence)
                    print(f"Claim #{cid} pending review")
                elif args.operation == "review":
                    review_claim(db, args.id, args.decision, args.note)
                    print(f"Claim #{args.id}: {args.decision}")
                else:
                    for row in db.execute("SELECT * FROM claims ORDER BY id"):
                        print(f"#{row['id']} [{row['review_status']}] {row['statement']} ({row['doi']}, {row['locator']})")
            elif args.command == "gap":
                if args.operation == 'assess':
                    workflow.assess_gap(db, args.id, workflow.read_json(args.file))
                    print('Recorded assessment; journal acceptance is not guaranteed.')
                elif args.operation == "add":
                    dois = [normalize_doi(value) for value in args.dois]
                    db.execute(
                        "INSERT INTO gaps(question,related_dois,created_at) VALUES (?,?,datetime('now'))",
                        (args.question, json.dumps(dois)),
                    )
                    db.commit()
                    print("Recorded unresolved question; this is not a verified novelty claim.")
                else:
                    for row in db.execute("SELECT * FROM gaps ORDER BY id"):
                        print(f"#{row['id']} [{row['status']}] {row['question']} | {row['related_dois']}")
            elif args.command == "prompt":
                write_text(args.out, research_prompt(args.topic, args.journal, db))
            elif args.command == "draft":
                if args.notes:
                    write_text(args.out, draft(db, args.title))
                else:
                    text, cmap = workflow.korean_draft(db, args.title)
                    write_text(args.out, text)
                    write_text(str(args.out) + '.citations.json', json.dumps(cmap, ensure_ascii=False, indent=2))
            elif args.command == "bibliography":
                query = "SELECT * FROM papers"
                if args.reviewed_only:
                    query += " WHERE publisher_checked_at IS NOT NULL AND followup_checked_at IS NOT NULL"
                for n, row in enumerate(db.execute(query + " ORDER BY year,doi"), 1):
                    print(f"{n}. {citation(row)}")
            elif args.command == "export":
                data = workflow.resultlab_export(db) if args.resultlab else export_data(db)
                write_text(args.out, json.dumps(data, ensure_ascii=False, indent=2))
    except (ValueError, RuntimeError, OSError, sqlite3.Error, KeyError, TypeError) as exc:
        print(f"IntroLab error: {exc}", file=sys.stderr)
        return 1
    return 0
