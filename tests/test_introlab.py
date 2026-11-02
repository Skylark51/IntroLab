"""Offline contract tests; never require live literature or a model."""
import tempfile
import unittest
from pathlib import Path

from introlab.crossref import normalize_doi, to_record
from introlab.render import citation, draft, research_prompt
from introlab.store import add_claim, connect, mark_checked, review_claim, upsert_paper


ITEM = {
    "DOI": "10.1000/TEST-2026",
    "title": ["Illustrative Mechanistic Study"],
    "container-title": ["Journal of the American Chemical Society"],
    "short-container-title": ["J. Am. Chem. Soc."],
    "author": [{"given": "Ada Mary", "family": "Example"}],
    "published": {"date-parts": [[2026, 2, 1]]},
    "volume": "148",
    "page": "100-110",
}


class IntroLabTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = connect(Path(self.tempdir.name) / "research.db")
        upsert_paper(self.db, to_record(ITEM))

    def tearDown(self):
        self.db.close()
        self.tempdir.cleanup()

    def test_doi_normalization(self):
        self.assertEqual(normalize_doi("HTTPS://DOI.ORG/10.1000/TEST-2026"), "10.1000/test-2026")
        with self.assertRaises(ValueError):
            normalize_doi("invented-reference")

    def test_citation_uses_only_supplied_metadata(self):
        row = self.db.execute("SELECT * FROM papers").fetchone()
        result = citation(row)
        self.assertIn("Example, A. M.", result)
        self.assertIn("J. Am. Chem. Soc.", result)
        self.assertIn("10.1000/test-2026", result)

    def test_approval_gates(self):
        doi = "10.1000/test-2026"
        cid = add_claim(self.db, doi, "A specific pathway was proposed", "Figure 2", "short source evidence")
        with self.assertRaises(ValueError):
            review_claim(self.db, cid, "supported", "reviewed")
        self.assertIn("No fully reviewed claims", draft(self.db, "Test"))
        mark_checked(self.db, doi, "publisher", "Publisher page DOI and Fig. 2 read")
        review_claim(self.db, cid, "supported", "Fig. 2 checked")
        self.assertIn("No fully reviewed claims", draft(self.db, "Test"))
        mark_checked(self.db, doi, "followup", "Follow-up search completed through Nov 2026")
        self.assertIn("A specific pathway was proposed", draft(self.db, "Test"))
        upsert_paper(self.db, to_record(ITEM))
        self.assertIn("A specific pathway was proposed", draft(self.db, "Test"))

    def test_prompt_marks_metadata_only(self):
        prompt = research_prompt("Mn peroxo ring-size mechanisms", "Journal of the American Chemical Society", self.db)
        self.assertIn("metadata only", prompt)
        self.assertIn("10.1000/test-2026", prompt)
        self.assertIn("follow-up", prompt.lower())


if __name__ == "__main__":
    unittest.main()
