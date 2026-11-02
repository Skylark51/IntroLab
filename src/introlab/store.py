"""SQLite store with explicit provenance and review gates."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS papers (
  doi TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  journal TEXT,
  journal_abbrev TEXT,
  year INTEGER,
  volume TEXT,
  issue TEXT,
  pages TEXT,
  authors_json TEXT NOT NULL,
  url TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  metadata_checked_at TEXT NOT NULL,
  publisher_checked_at TEXT,
  publisher_note TEXT NOT NULL DEFAULT '',
  followup_checked_at TEXT,
  followup_note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS searches (
  id INTEGER PRIMARY KEY,
  query TEXT NOT NULL,
  journal TEXT NOT NULL,
  start_year INTEGER,
  end_year INTEGER,
  offset INTEGER NOT NULL,
  returned INTEGER NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS claims (
  id INTEGER PRIMARY KEY,
  doi TEXT NOT NULL REFERENCES papers(doi),
  statement TEXT NOT NULL,
  locator TEXT NOT NULL,
  evidence TEXT NOT NULL,
  review_status TEXT NOT NULL DEFAULT 'pending',
  review_note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS gaps (
  id INTEGER PRIMARY KEY,
  question TEXT NOT NULL,
  related_dois TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'unresolved',
  created_at TEXT NOT NULL
);
"""


def connect(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path))
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    from .workflow import migrate
    migrate(db)
    return db


def upsert_paper(db, p):
    db.execute(
        """INSERT INTO papers (
          doi,title,journal,journal_abbrev,year,volume,issue,pages,
          authors_json,url,metadata_json,metadata_checked_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(doi) DO UPDATE SET
          title=excluded.title,journal=excluded.journal,
          journal_abbrev=excluded.journal_abbrev,year=excluded.year,
          volume=excluded.volume,issue=excluded.issue,pages=excluded.pages,
          authors_json=excluded.authors_json,url=excluded.url,
          metadata_json=excluded.metadata_json,
          metadata_checked_at=excluded.metadata_checked_at,
          metadata_verified=1""",
        (p["doi"], p["title"], p["journal"], p["journal_abbrev"],
         p["year"], p["volume"], p["issue"], p["pages"],
         json.dumps(p["authors"], ensure_ascii=False), p["url"],
         json.dumps(p["metadata"], ensure_ascii=False), timestamp()),
    )
    db.commit()


def record_search(db, args, returned, dois=None, status='ok', note=''):
    db.execute(
        """INSERT INTO searches(query,journal,start_year,end_year,offset,returned,created_at,result_dois,status,note)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (args.query, args.journal, args.from_year, args.to_year,
         args.offset, returned, timestamp(), json.dumps(dois or []), status, note),
    )
    db.commit()


def mark_checked(db, doi, kind, note):
    if not note.strip():
        raise ValueError("Document the reviewed URL/source or follow-up search")
    column = {"publisher": "publisher_checked_at", "followup": "followup_checked_at"}[kind]
    note_column = {"publisher": "publisher_note", "followup": "followup_note"}[kind]
    cursor = db.execute(f"UPDATE papers SET {column}=?, {note_column}=? WHERE doi=?", (timestamp(), note, doi))
    if cursor.rowcount:
        db.execute('INSERT INTO reviews(entity,entity_id,decision,note,created_at) VALUES (?,?,?,?,?)',
                   ('paper', doi, kind, note, timestamp()))
    db.commit()
    if cursor.rowcount == 0:
        raise ValueError(f"DOI not found: {doi}")


def add_claim(db, doi, statement, locator, evidence):
    if not all((statement.strip(), locator.strip(), evidence.strip())):
        raise ValueError("Statement, source locator, and evidence are mandatory")
    cursor = db.execute(
        "INSERT INTO claims(doi,statement,locator,evidence,created_at) VALUES (?,?,?,?,?)",
        (doi, statement, locator, evidence, timestamp()),
    )
    db.commit()
    return cursor.lastrowid


def review_claim(db, claim_id, decision, note):
    if decision not in ('supported', 'refuted', 'uncertain'):
        raise ValueError('Invalid claim decision')
    claim = db.execute(
        """SELECT c.id,c.access, p.publisher_checked_at FROM claims c
           JOIN papers p ON p.doi=c.doi WHERE c.id=?""", (claim_id,)
    ).fetchone()
    if not claim:
        raise ValueError(f"Claim not found: {claim_id}")
    if decision == "supported" and not claim["publisher_checked_at"]:
        raise ValueError("Check the publisher's source before supporting a claim")
    if decision == 'supported' and claim['access'] == 'inaccessible':
        raise ValueError('Inaccessible source cannot support a claim')
    db.execute(
        "UPDATE claims SET review_status=?,review_note=? WHERE id=?",
        (decision, note, claim_id),
    )
    db.execute('INSERT INTO reviews(entity,entity_id,decision,note,created_at) VALUES (?,?,?,?,?)',
               ('claim', str(claim_id), decision, note, timestamp()))
    db.commit()


def export_data(db):
    result = {"format_version": 2, "exported_at": timestamp()}
    for table in ("papers", "searches", "claims", "gaps", "project", "batches", "batch_papers", "imports", "relations", "reviews", "sentences", "sentence_history", "project_results", "gap_assessments"):
        result[table] = [dict(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY ROWID")]
    return result
