import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import find_categories as fc
import monthly_monitor as mm
from tests.test_find_paper_matches import paper


class MonthlyMonitorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.focus = self.root / "focus.txt"
        self.categories = self.root / "categories.csv"
        self.focus.write_text("Cu2O thin film", encoding="utf-8")
        self.categories.write_text("code,interest\ncond-mat.mtrl-sci,Cu2O thin film\n", encoding="utf-8")
        self.rows = [paper(i, "Cu2O thin film") for i in range(41)]
        self.now = datetime(2026, 9, 30, tzinfo=timezone.utc)
        self.fetch = mock.patch.object(mm.fp, "fetch_papers", return_value=(self.rows, len(self.rows)))
        self.fetch_mock = self.fetch.start()
        self.addCleanup(self.fetch.stop)
        self.model = mock.patch.object(mm.fm, "match_batch")
        self.model_mock = self.model.start()
        self.addCleanup(self.model.stop)
        self.annotate = mock.patch.object(mm.pc, "annotate")
        self.annotate.start()
        self.addCleanup(self.annotate.stop)

    def prepare(self, percent=100, limit=2):
        with contextlib.redirect_stdout(io.StringIO()):
            return mm.prepare(self.focus, self.categories, 30, 3, percent, limit, self.root / "runs", self.now)

    def approve(self, path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_prepare_is_model_free_and_dated_with_exact_preview(self):
        path = self.prepare(percent=10, limit=1)
        plan = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual((plan["start"], plan["end"]), ("2026-08-29", "2026-09-27"))
        self.assertEqual(len(plan["papers"]), 5)
        self.assertEqual(mm.fm.request_count(plan["papers"]), 1)
        self.model_mock.assert_not_called()
        self.assertTrue(path.parent.name.startswith("20260930"))
        self.assertNotEqual(path, self.prepare(percent=10, limit=1))
        self.fetch_mock.assert_called()

    def test_preview_shows_model_and_prompt_budget_without_calling_model(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            mm.prepare(self.focus, self.categories, 30, 3, 10, 1, self.root / "runs", self.now)
        text = output.getvalue()
        self.assertIn(f"Screening model: {mm.cp.MODEL}", text)
        self.assertIn("1 Copilot prompts; configured limit 1", text)
        self.assertIn("Token/credit usage is not estimated", text)
        self.model_mock.assert_not_called()

    def test_focus_mismatch_and_bounds_refuse_before_fetch(self):
        self.focus.write_text("Different focus", encoding="utf-8")
        with self.assertRaisesRegex(fc.SetupError, "exact focus"):
            self.prepare()
        self.fetch_mock.assert_not_called()
        with self.assertRaisesRegex(fc.SetupError, "Invalid bounds"):
            mm.prepare(self.focus, self.categories, 91, 3, 10, 1, self.root, self.now)

    def test_runs_path_must_be_absolute_before_fetch(self):
        with self.assertRaisesRegex(fc.SetupError, "absolute path"):
            mm.prepare(self.focus, self.categories, 30, 3, 10, 1, Path("relative"), self.now)
        self.fetch_mock.assert_not_called()

    def test_repository_snapshot_matches_approved_focus_and_categories(self):
        interest, categories = mm.load_inputs(mm.FOCUS, mm.fc.ROOT / "data" / "monthly_categories.csv")
        self.assertEqual(interest, mm.FOCUS.read_text(encoding="utf-8").strip())
        self.assertEqual([row["code"] for row in categories],
                         ["cond-mat.mtrl-sci", "physics.app-ph", "cond-mat.mes-hall", "physics.optics"])

    def test_fresh_workspace_can_screen_plan_in_durable_directory(self):
        path = self.prepare(percent=10, limit=1)
        copy = self.root / "fresh"
        shutil.copytree(mm.fc.ROOT / "scripts", copy / "scripts",
                        ignore=shutil.ignore_patterns("__pycache__"))
        script = ("import sys, monthly_monitor as mm; "
                  "mm.fm.match_batch=lambda *args: [('P01','relevant','','')]; "
                  "mm.pc.annotate=lambda matches: None; "
                  "mm.screen(mm.Path(sys.argv[1]), sys.argv[2])")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(copy / "scripts")
        result = subprocess.run([sys.executable, "-c", script, str(path), self.approve(path)],
                                cwd=copy, env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("MONTHLY RUN: COMPLETE", mm.report_path(path.parent).read_text(encoding="utf-8"))
        self.model_mock.assert_not_called()

    def test_rejects_modified_plan_and_over_limit_without_calls(self):
        path = self.prepare(limit=1)
        digest = self.approve(path)
        with self.assertRaisesRegex(fc.SetupError, "exceeds"):
            mm.screen(path, digest)
        self.assertFalse((path.parent / "screen.started").exists())
        path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
        with self.assertRaisesRegex(fc.SetupError, "hash does not match"):
            mm.screen(path, digest)
        self.model_mock.assert_not_called()

    def test_one_shot_approval_and_checkpoint_on_failure(self):
        path = self.prepare()
        self.model_mock.side_effect = [[("P01", "Possible absorber", "Cu2O", "")], fc.SetupError("offline")]
        with self.assertRaisesRegex(fc.SetupError, "after 1 of 2"):
            mm.screen(path, self.approve(path))
        report = mm.report_path(path.parent).read_text(encoding="utf-8")
        self.assertIn("INCOMPLETE: 1 of 2 batches finished", report)
        self.assertIn("Possible absorber", report)
        self.assertIn("Papers retrieved from arXiv: 41", report)
        self.assertIn("Papers outside the shortlist were not screened", report)
        with self.assertRaisesRegex(fc.SetupError, "already been started"):
            mm.screen(path, self.approve(path))
        self.assertEqual(self.model_mock.call_count, 2)

    def test_success_and_zero_papers(self):
        self.rows.clear()
        path = self.prepare()
        mm.screen(path, self.approve(path))
        self.model_mock.assert_not_called()
        self.assertIn("MONTHLY RUN: COMPLETE", mm.report_path(path.parent).read_text(encoding="utf-8"))

    def test_same_month_runs_have_distinct_report_names_and_contents(self):
        self.rows.clear()
        first, second = self.prepare(), self.prepare()
        mm.screen(first, self.approve(first))
        first_report = mm.report_path(first.parent)
        first_content = first_report.read_bytes()
        mm.screen(second, self.approve(second))
        second_report = mm.report_path(second.parent)
        self.assertIn("202609", first_report.name)
        self.assertIn("202609", second_report.name)
        self.assertNotEqual(first_report.name, second_report.name)
        self.assertEqual(first_report.read_bytes(), first_content)
        self.assertTrue(second_report.exists())

    def test_success_screens_only_approved_shortlist(self):
        path = self.prepare(percent=10, limit=1)
        self.model_mock.return_value = [("P01", "Possible absorber", "Cu2O", "")]
        mm.screen(path, self.approve(path))
        self.assertEqual(self.model_mock.call_count, 1)
        args = self.model_mock.call_args.args
        self.assertIsNone(args[0])
        self.assertEqual(len(args[2]), 5)
        report = mm.report_path(path.parent).read_text(encoding="utf-8")
        self.assertIn("MONTHLY RUN: COMPLETE", report)
        self.assertIn("Cu2O", report)
        self.assertIn("BM25 shortlisted: 5", report)

    def test_no_matching_words_does_not_send_arbitrary_papers(self):
        self.rows[:] = [paper(1, "unrelated")]
        path = self.prepare()
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["papers"], [])
        mm.screen(path, self.approve(path))
        self.model_mock.assert_not_called()

    def test_changed_screening_code_refuses_plan(self):
        path = self.prepare()
        with mock.patch.object(mm, "screening_fingerprint", return_value="changed"):
            with self.assertRaisesRegex(fc.SetupError, "no longer supported"):
                mm.screen(path, self.approve(path))
        self.model_mock.assert_not_called()

    def test_manual_asks_days_and_previews_without_screening(self):
        with mock.patch("builtins.input", side_effect=["", "91", "3"]), \
                mock.patch.object(mm, "prepare") as prepare, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(mm.main(["manual"]), 0)
        prepare.assert_called_once_with(mm.FOCUS, mm.fp.SELECTED, 3, 3, 10, 1, mm.RUNS)
        self.model_mock.assert_not_called()

    def test_manual_eof_stops_before_fetch_or_screening(self):
        with mock.patch("builtins.input", side_effect=EOFError), \
                contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(mm.main(["manual"]), 1)
        self.assertIn("nothing was fetched", errors.getvalue())
        self.fetch_mock.assert_not_called()
        self.model_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
