"""Prepare and, after explicit approval, screen a bounded arXiv snapshot."""

import argparse
import csv
import hashlib
import json
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import copilot_provider as cp
import fetch_papers as fp
import find_categories as fc
import find_paper_matches as fm
import publication_check as pc
import research_monitor as rm
import search_experiment as se

FOCUS = fc.ROOT / "data" / "research_focus.txt"
RUNS = fc.ROOT / "data" / "monthly_runs"
MAX_DAYS = 90
MAX_PROMPTS = 6


def screening_fingerprint():
    return hashlib.sha256(Path(fm.__file__).read_bytes() + Path(cp.__file__).read_bytes()).hexdigest()


def load_inputs(focus_path, categories_path):
    try:
        interest = focus_path.read_text(encoding="utf-8-sig").strip()
        with categories_path.open(encoding="utf-8-sig", newline="") as stream:
            selected = list(csv.DictReader(stream))
    except (OSError, UnicodeError) as e:
        raise fc.SetupError(f"Cannot read focus or categories: {e}") from e
    if not interest:
        raise fc.SetupError("The research focus is empty.")
    if not selected or any(row.get("interest", "").strip() != interest for row in selected):
        raise fc.SetupError("Accepted categories must have been selected for the exact focus in the focus file.")
    taxonomy = fc.load_taxonomy()
    codes = [row.get("code", "").strip() for row in selected]
    if any(code not in taxonomy for code in codes) or len(set(codes)) != len(codes):
        raise fc.SetupError("Accepted categories contain unknown, missing or duplicate codes.")
    return interest, [taxonomy[code] for code in codes]


def shortlist(papers, interest, percent):
    docs = {p["arxiv_id"]: se.paper_text(p) for p in papers}
    if len(docs) != len(papers):
        raise fc.SetupError("The retrieved snapshot contains duplicate arXiv IDs.")
    scores = se.bm25_scores(interest, docs)
    count = (len(papers) * percent + 99) // 100
    ids = [key for key in se.rank(scores) if scores[key] > 0][:count]
    by_id = {p["arxiv_id"]: p for p in papers}
    return [by_id[key] for key in ids]


def covered_through(runs, interest, categories):
    if not runs.exists():
        return None
    codes = {row["code"] for row in categories}
    intervals = []
    for run_dir in runs.iterdir():
        if not run_dir.is_dir():
            continue
        for report in (report_path(run_dir), run_dir / "report.txt"):
            if not report.exists():
                continue
            with report.open(encoding="utf-8") as stream:
                complete = stream.readline().rstrip("\r\n") == "MONTHLY RUN: COMPLETE"
            if not complete:
                continue
            try:
                data = (run_dir / "plan.json").read_bytes()
                approved = (run_dir / "screen.started").read_text(encoding="utf-8").strip()
                plan = json.loads(data)
                if hashlib.sha256(data).hexdigest() != approved:
                    raise ValueError("plan does not match approval")
                start = date.fromisoformat(plan["start"])
                end = date.fromisoformat(plan["end"])
                plan_codes = {row["code"] for row in plan["categories"]}
                plan_interest = plan["interest"]
                if start > end or not plan_codes:
                    raise ValueError("invalid date range or categories")
            except (OSError, ValueError, KeyError, TypeError) as e:
                raise fc.SetupError(f"Cannot use completed run {run_dir}: {e}") from e
            if plan_interest == interest and plan_codes == codes:
                intervals.append((start, end))
            break
    if not intervals:
        return None
    intervals.sort()
    _, covered = intervals[0]
    for start, end in intervals[1:]:
        if start > covered + timedelta(days=1):
            break
        covered = max(covered, end)
    return covered


def prepare(focus_path, categories_path, days, lag, percent, max_prompts, runs=RUNS, now=None):
    if not ((days is None or 1 <= days <= MAX_DAYS) and 3 <= lag <= 30 and 1 <= percent <= 100
            and 1 <= max_prompts <= MAX_PROMPTS):
        raise fc.SetupError("Invalid bounds: days 1-90, lag 3-30, shortlist percent 1-100, max prompts 1-5.")
    if not runs.is_absolute():
        raise fc.SetupError("The runs directory must be an absolute path.")
    interest, categories = load_inputs(focus_path, categories_path)
    now = now or datetime.now(timezone.utc)
    end = now.date() - timedelta(days=lag)
    if days is None:
        covered = covered_through(runs, interest, categories)
        if covered is None:
            start = end - timedelta(days=29)
            print("No completed run for this focus and category set; starting with 30 days.")
        else:
            start = covered + timedelta(days=1)
            if start > end:
                raise fc.SetupError(f"No new dates to fetch after {covered}; the latest eligible date is {end}.")
            if (end - start).days + 1 > MAX_DAYS:
                end = start + timedelta(days=MAX_DAYS - 1)
                print(f"Catching up on the oldest {MAX_DAYS} days; later dates need another run.")
            print(f"Continuing after completed coverage through {covered}.")
    else:
        start = end - timedelta(days=days - 1)
    papers, total = fp.fetch_papers([row["code"] for row in categories], *rm.utc_window(start, end))
    chosen = shortlist(papers, interest, percent)
    plan = {
        "version": 1, "created_utc": now.isoformat(), "interest": interest, "categories": categories,
        "start": start.isoformat(), "end": end.isoformat(), "retrieved_count": len(papers),
        "arxiv_total": total, "shortlist_percent": percent, "papers": chosen,
        "max_prompts": max_prompts, "batch_size": fm.BATCH_SIZE, "model": fc.COPILOT_MODEL,
        "screening_fingerprint": screening_fingerprint(),
    }
    data = (json.dumps(plan, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()
    run_dir = runs / (now.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12])
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "plan.json").write_bytes(data)
    count = fm.request_count(chosen)
    print(f"Prepared {run_dir / 'plan.json'}")
    print(f"UTC dates {start} through {end}; {len(papers)} retrieved, {len(chosen)} shortlisted "
          f"by local BM25 (top {percent}%, nonzero matches only).")
    print(f"Screening model: {plan['model']}; up to {plan['batch_size']} titles and abstracts per prompt.")
    print(f"Screening: {count} Copilot prompts; configured limit {max_prompts}, hard limit {MAX_PROMPTS}. "
          "Token/credit usage is not estimated.")
    print("Papers outside the shortlist will not be screened; local ranking may miss relevant materials.")
    if count > max_prompts:
        print("Over the configured limit: prepare a new plan with a shorter window or smaller shortlist.")
    else:
        print(f"To approve this exact snapshot: monthly_monitor screen --plan \"{run_dir / 'plan.json'}\" "
              f"--approve {digest}")
    return run_dir / "plan.json"


def render(plan, matches, done, error, status):
    start = datetime.fromisoformat(plan["start"]).date()
    end = datetime.fromisoformat(plan["end"]).date()
    papers = plan["papers"]
    batches = fm.request_count(papers)
    report = rm.build_report(plan["interest"], "", plan["categories"], start, end, papers,
                             matches, done, batches, None, datetime.now(timezone.utc))
    report = report.replace(f"Papers retrieved from arXiv: {len(papers)}",
                            f"Papers retrieved from arXiv: {plan['retrieved_count']}", 1)
    if status.startswith("INCOMPLETE") and not matches:
        report = report.replace("No papers were selected as matches for your description.",
                                "No completed batch selected a match; screening is incomplete.")
    prefix = (f"MONTHLY RUN: {status}\n"
              f"arXiv retrieved: {plan['retrieved_count']}; BM25 shortlisted: {len(papers)} "
              f"(top {plan['shortlist_percent']}%, nonzero scores only).\n"
              "Papers outside the shortlist were not screened. BM25 is not a relevance judgment.\n"
              f"Screening model: {plan['model']}; configured maximum: {plan['max_prompts']} prompts.\n"
              + (f"INCOMPLETE: {done} of {batches} batches finished. {error}\n" if error else "")
              + "Token consumption and charges are not measured.\n\n")
    return prefix + report


def report_path(run_dir):
    return run_dir / f"research_report-{run_dir.name}.txt"


def write_report(run_dir, content):
    temp = run_dir / "report.tmp"
    temp.write_text(content, encoding="utf-8")
    temp.replace(report_path(run_dir))


def screen(plan_path, approval):
    try:
        data = plan_path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != approval:
            raise fc.SetupError("Approval hash does not match the plan; review and approve the exact snapshot.")
        plan = json.loads(data)
        if (plan["version"] != 1 or plan["model"] != fc.COPILOT_MODEL
                or plan["batch_size"] != fm.BATCH_SIZE or not 1 <= plan["max_prompts"] <= MAX_PROMPTS
                or plan["screening_fingerprint"] != screening_fingerprint()):
            raise fc.SetupError("Plan settings are no longer supported; prepare a new plan.")
        papers = plan["papers"]
        batches = fm.request_count(papers)
        if batches > plan["max_prompts"] or batches > MAX_PROMPTS:
            raise fc.SetupError("The planned screening exceeds the configured prompt limit.")
        lock = plan_path.parent / "screen.started"
        with lock.open("x", encoding="utf-8") as stream:
            stream.write(digest + "\n")
    except FileExistsError as e:
        raise fc.SetupError("This plan has already been started; prepare a new plan rather than retrying.") from e
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise fc.SetupError(f"Cannot start the prepared plan: {e}") from e

    matches, done, error = [], 0, None
    write_report(plan_path.parent, render(plan, matches, done, "Screening has not completed.", "INCOMPLETE"))
    for offset in range(0, len(papers), fm.BATCH_SIZE):
        batch = papers[offset:offset + fm.BATCH_SIZE]
        try:
            found = fm.collect_copilot(fm.match_batch(None, plan["interest"], batch), batch)
        except fc.SetupError as e:
            error = str(e)
            break
        matches.extend({**p, **found[p["arxiv_id"]]} for p in batch if p["arxiv_id"] in found)
        done += 1
        write_report(plan_path.parent, render(plan, matches, done, "Screening has not completed.", "INCOMPLETE"))
    if error:
        write_report(plan_path.parent, render(plan, matches, done, error, "INCOMPLETE"))
        raise fc.SetupError(f"Screening stopped after {done} of {batches} batches: {error}")
    write_report(plan_path.parent, render(plan, matches, done, None, "INCOMPLETE: publication checks pending"))
    pc.annotate(matches)
    write_report(plan_path.parent, render(plan, matches, done, None, "COMPLETE"))
    print(f"Report: {report_path(plan_path.parent)}")


def ask_days():
    while True:
        try:
            answer = input("How many days of papers to fetch (1-90, ending 3 days ago)? ").strip()
        except EOFError as e:
            raise fc.SetupError("No day count was provided; nothing was fetched.") from e
        try:
            days = int(answer)
        except ValueError:
            days = 0
        if 1 <= days <= MAX_DAYS:
            return days
        print(f"Enter a whole number from 1 to {MAX_DAYS}.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    plan = actions.add_parser("prepare", help="Fetch and preview without calling a model")
    plan.add_argument("--focus", type=Path, default=FOCUS)
    plan.add_argument("--categories", type=Path, default=fp.SELECTED)
    plan.add_argument("--days", type=int, help="Override automatic coverage with a 1-90 day window")
    plan.add_argument("--lag", type=int, default=3)
    plan.add_argument("--shortlist-percent", type=int, default=10)
    plan.add_argument("--max-prompts", type=int, required=True)
    plan.add_argument("--runs-dir", type=Path, default=RUNS,
                      help="Absolute directory for saved plans and reports")
    manual = actions.add_parser("manual", help="Ask for a day count and prepare a preview")
    manual.add_argument("--focus", type=Path, default=FOCUS)
    manual.add_argument("--categories", type=Path, default=fp.SELECTED)
    manual.add_argument("--max-prompts", type=int, default=1)
    manual.add_argument("--runs-dir", type=Path, default=RUNS,
                        help="Absolute directory for saved plans and reports")
    execute = actions.add_parser("screen", help="Screen a previously reviewed snapshot")
    execute.add_argument("--plan", type=Path, required=True)
    execute.add_argument("--approve", required=True, help="SHA-256 printed by prepare")
    args = parser.parse_args(argv)
    try:
        if args.action == "prepare":
            prepare(args.focus, args.categories, args.days, args.lag, args.shortlist_percent, args.max_prompts,
                    args.runs_dir)
        elif args.action == "manual":
            prepare(args.focus, args.categories, ask_days(), 3, 10, args.max_prompts, args.runs_dir)
        else:
            screen(args.plan, args.approve)
    except (fc.SetupError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
