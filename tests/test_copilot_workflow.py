import asyncio
import unittest
from unittest import mock

from pydantic import BaseModel

import copilot_provider as cp
import find_categories as fc
import find_paper_matches as fm
from tests.test_find_paper_matches import paper


class Answer(BaseModel):
    value: str


class ProviderTest(unittest.TestCase):
    def test_request_disables_tools_and_uses_structured_response(self):
        session = mock.MagicMock()
        session.__aenter__ = mock.AsyncMock(return_value=session)
        session.__aexit__ = mock.AsyncMock(return_value=None)
        session.send_and_wait_typed = mock.AsyncMock(return_value=Answer(value="ok"))
        client = mock.MagicMock()
        client.__aenter__ = mock.AsyncMock(return_value=client)
        client.__aexit__ = mock.AsyncMock(return_value=None)
        client.create_session = mock.AsyncMock(return_value=session)
        with mock.patch("copilot.CopilotClient", return_value=client) as factory:
            result = asyncio.run(cp._request("instructions", "prompt", Answer))
        self.assertEqual(factory.call_args.kwargs["mode"], "empty")
        self.assertIn("runtime", factory.call_args.kwargs)
        client.create_session.assert_awaited_once_with(
            model=cp.MODEL, tools={"available_tools": []},
            system_message={"mode": "replace", "content": "instructions"},
            enable_config_discovery=False,
        )
        session.send_and_wait_typed.assert_awaited_once_with("prompt", Answer, timeout=cp.TIMEOUT_SECONDS)
        self.assertEqual(result.value, "ok")

    def test_sdk_error_is_reported_as_setup_error(self):
        from copilot import JsonRpcError
        with mock.patch.object(cp, "_request", side_effect=JsonRpcError(401, "not authenticated")):
            with self.assertRaisesRegex(fc.SetupError, "not authenticated"):
                cp.request("instructions", "prompt", Answer)

    def test_legacy_session_error_is_reported(self):
        with mock.patch.object(cp, "_request", side_effect=Exception("Session error: quota reached")):
            with self.assertRaisesRegex(fc.SetupError, "quota reached"):
                cp.request("instructions", "prompt", Answer)


class CopilotScreeningTest(unittest.TestCase):
    def test_evidence_names_must_appear_in_the_same_paper(self):
        batch = [paper(1, "Cu2O thin films"), paper(2, "Other")]
        batch[0]["abstract"] = "The Materials Project lists Cu2O."
        records = fm.collect_copilot([
            ("P01", "A promising oxide", "Cu2O", "Materials Project"),
            ("P02", "Other", "Cu2O", "Imaginary database"),
            ("P99", "invalid label", "Cu2O", ""),
        ], batch)
        self.assertEqual(records[batch[0]["arxiv_id"]]["material_mentioned"], "Cu2O")
        self.assertEqual(records[batch[0]["arxiv_id"]]["database_mentioned"], "Materials Project")
        self.assertEqual(records[batch[1]["arxiv_id"]]["material_mentioned"], "")
        self.assertEqual(records[batch[1]["arxiv_id"]]["database_mentioned"], "")
        self.assertEqual(len(records), 2)

    def test_limit_refuses_before_sending(self):
        with mock.patch.object(fm, "MAX_COPILOT_BATCHES", 1), mock.patch.object(fm, "match_batch") as send:
            with self.assertRaisesRegex(fc.SetupError, "over the limit"):
                fm.match_papers("interest", [paper(i, "x") for i in range(fm.BATCH_SIZE + 1)], None)
            send.assert_not_called()

    def test_failure_retains_completed_batch_and_marks_incomplete(self):
        papers = [paper(i, "x") for i in range(fm.BATCH_SIZE + 1)]
        with mock.patch.object(fm, "match_batch", side_effect=[
            [("P01", "Relevant", "", "")], fc.SetupError("offline")
        ]):
            matches, done, error = fm.match_papers("interest", papers, None)
        self.assertEqual(done, 1)
        self.assertEqual(matches[0]["arxiv_id"], papers[0]["arxiv_id"])
        self.assertIn("offline", str(error))


if __name__ == "__main__":
    unittest.main()
