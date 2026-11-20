import io
import json
import unittest
from unittest import mock
from urllib.error import HTTPError, URLError

import publication_check as pc


def response(data):
    result = mock.MagicMock()
    result.__enter__.return_value = io.BytesIO(json.dumps({"message": data}).encode())
    return result


class PublicationCheckTest(unittest.TestCase):
    def test_journal_article_is_not_claimed_as_confirmed_peer_review(self):
        with mock.patch.object(pc, "urlopen", return_value=response({
            "DOI": "10.1000/example", "type": "journal-article", "container-title": ["Example Journal"]
        })):
            status, venue = pc.lookup("10.1000/example")
        self.assertIn("journal article", status)
        self.assertIn("peer review unverified", status)
        self.assertEqual(venue, "Example Journal")

    def test_missing_doi_and_crossref_errors_are_unknown(self):
        for error in [HTTPError("url", 404, "not found", {}, None), URLError("offline")]:
            with mock.patch.object(pc, "urlopen", side_effect=error):
                self.assertIn("peer review unverified", pc.lookup("10.1000/example")[0])
        papers = [{"doi": ""}]
        pc.annotate(papers)
        self.assertIn("Insufficient metadata", papers[0]["publication_status"])

    def test_non_journal_and_mismatched_metadata(self):
        with mock.patch.object(pc, "urlopen", return_value=response({"DOI": "10.1000/example", "type": "posted-content"})):
            self.assertIn("posted-content", pc.lookup("10.1000/example")[0])
        with mock.patch.object(pc, "urlopen", return_value=response({"DOI": "10.1000/other", "type": "journal-article"})):
            self.assertIn("mismatch", pc.lookup("10.1000/example")[0])

    def test_duplicate_doi_is_checked_once(self):
        papers = [{"doi": "10.1000/example"}, {"doi": "10.1000/EXAMPLE"}]
        with mock.patch.object(pc, "lookup", return_value=("unverified", "")) as lookup:
            pc.annotate(papers)
        lookup.assert_called_once()
        self.assertEqual([p["publication_status"] for p in papers], ["unverified", "unverified"])

    def test_title_search_requires_exact_title_and_first_author(self):
        data = {"items": [
            {"title": ["Cu2O thin films"], "author": [{"family": "Smith"}], "DOI": "10.1000/a",
             "container-title": ["Materials Journal"]},
            {"title": ["A different work"], "author": [{"family": "Smith"}], "DOI": "10.1000/b"},
        ]}
        with mock.patch.object(pc, "urlopen", return_value=response(data)):
            doi, status, venue = pc.find_candidate("Cu2O thin films", "A. Smith; B. Jones")
        self.assertEqual(doi, "10.1000/a")
        self.assertIn("Possible", status)
        self.assertIn("peer review unverified", status)
        self.assertEqual(venue, "Materials Journal")

    def test_title_search_rejects_wrong_author_or_ambiguous_results(self):
        record = {"title": ["Example"], "author": [{"family": "Smith"}], "DOI": "10.1000/a"}
        with mock.patch.object(pc, "urlopen", return_value=response({"items": [record]})):
            self.assertEqual(pc.find_candidate("Example", "A. Jones")[0], "")
        with mock.patch.object(pc, "urlopen", return_value=response({"items": [
            {**record, "author": [{"family": "Jones"}, {"family": "Smith"}]}
        ]})):
            self.assertEqual(pc.find_candidate("Example", "A. Smith")[0], "")
        with mock.patch.object(pc, "urlopen", return_value=response({"items": [record, {**record, "DOI": "10.1000/b"}]})):
            self.assertIn("Multiple", pc.find_candidate("Example", "A. Smith")[1])


if __name__ == "__main__":
    unittest.main()
