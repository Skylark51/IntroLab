"""Conservative research exports: missing evidence and metadata are never invented."""
import json
import re


def author_text(authors):
    names = []
    for author in authors:
        family = (author.get("family") or "").strip()
        given = (author.get("given") or "").strip()
        initials = " ".join(part[0].upper() + "." for part in re.split(r"[\s-]+", given) if part)
        if family:
            names.append((family + ", " + initials).rstrip(", "))
        elif given:
            names.append(given)
    return "; ".join(names)


def citation(p):
    names = author_text(json.loads(p["authors_json"]))
    parts = []
    if names:
        parts.append(names + ".")
    if p["title"]:
        parts.append(p["title"].rstrip(".") + ".")
    if p["journal_abbrev"] or p["journal"]:
        parts.append((p["journal_abbrev"] or p["journal"]).rstrip(".") + ".")
    if p["year"]:
        parts.append(str(p["year"]) + ("," if p["volume"] else "."))
    if p["volume"]:
        parts.append(p["volume"] + ("," if p["pages"] else "."))
    if p["pages"]:
        parts.append(p["pages"] + ".")
    parts.append("https://doi.org/" + p["doi"])
    return " ".join(parts)


def approved_claims(db):
    return db.execute(
        """SELECT c.id AS claim_id,c.statement,c.locator,c.evidence,c.doi,p.*
           FROM claims c JOIN papers p ON p.doi=c.doi
           WHERE c.review_status='supported'
             AND p.publisher_checked_at IS NOT NULL
             AND p.followup_checked_at IS NOT NULL
           ORDER BY c.id"""
    ).fetchall()


def draft(db, title):
    rows = approved_claims(db)
    refs = {}
    lines = [f"# {title}", "", "## Evidence-backed introduction notes", ""]
    for row in rows:
        doi = row["doi"]
        if doi not in refs:
            refs[doi] = (len(refs) + 1, row)
        number = refs[doi][0]
        lines.append(f"- {row['statement']} [{number}]")
        lines.append(f"  - Provenance: DOI {doi}; {row['locator']}; claim #{row['claim_id']}")
    if not rows:
        lines.append("_No fully reviewed claims yet. Check publisher, follow-up literature and evidence._")
    lines += ["", "## References (JACS-like; final editorial review required)", ""]
    for number, row in refs.values():
        lines.append(f"{number}. {citation(row)}")
    lines += ["", "> Research notes only. Novelty, wording and journal style require author review.", ""]
    return "\n".join(lines)


def research_prompt(topic, journal, db):
    papers = list(db.execute(
        """SELECT doi,title,year FROM papers WHERE LOWER(journal)=LOWER(?)
           ORDER BY year DESC LIMIT 15""", (journal,)
    ))
    seeds = "\n".join(f"- {p['doi']} | {p['year']} | {p['title']}" for p in papers)
    if not seeds:
        seeds = "- No stored DOI candidates; discover sources independently."
    return f"""You are a computational/bioinorganic chemistry literature investigator.
Use ChatGPT web browsing to research this question: {topic}
This batch focuses on: {journal}. Analyze 5-15 relevant studies in one batch.
Also search later publications across ALL journals to see whether a claimed
mechanistic gap was already resolved. Distinguish facts, interpretations, and hypotheses.

Known DOI candidates (metadata only; never evidence for a scientific claim):
{seeds}

Mandatory procedure:
1. Confirm each DOI, author/title/year/journal on the publisher landing page.
2. If legally accessible, read text and SI. For each specific mechanistic claim
   give its section, figure, table, page, or short exact excerpt and source URL.
3. Search independent follow-up works that support, contradict or resolve it.
4. Mark unknown or inaccessible evidence explicitly. Never invent DOI, quote,
   barrier, reaction mechanism, source locator, or claim of novelty.
5. Suggest specific mechanistic gaps suitable for computational examination
   using the user's established Gaussian protocol. Never assume a method alone
   proves a mechanistic interpretation.
6. Return (a) verified bibliographic records, (b) claim-reference-locator matrix,
   (c) follow-up check table, (d) ranked testable gaps, and (e) a compact
   Introduction draft with DOI-linked citations and JACS-like references.
7. Use distinct verification states: metadata_verified, source_checked,
   claim_supported, followup_checked. No state implies another state.
8. Treat all new statements as candidate claims pending researcher review.

Avoid long copyrighted excerpts. Summarize with precise citations.
Report the batch's scope and limits; do not claim an exhaustive review.
"""
