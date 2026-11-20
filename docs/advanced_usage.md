# Advanced usage

[Back to the README](../README.md)

## Running single steps

`research_monitor` runs these steps in order. You can also run them one at a time, with the virtual environment active (`(.venv)` in the prompt). Each step reads the previous step's file from `data`.

| Command | What it does | Provider |
|---|---|---|
| `find_categories "<description>"` | Suggests categories and saves them to `data\selected_categories.csv`. There's no accept/revise step. | Copilot |
| `fetch_papers YYYY-MM-DD` | Downloads the papers in the saved categories for **one** day to `data\retrieved_papers.csv`. Note the year-month-day format. | arXiv |
| `find_paper_matches "<description>"` | Screens every saved paper (option `l`). Saves `data\paper_matches.csv`. | Copilot |
| `rerank_papers "<description>"` | Search first, then screens the top 10% (option `h`). Saves `data\paper_matches.csv` and `data\paper_matches_settings.json`. | OpenAI API |

The two matching commands show a few sample papers, say how many requests they will send, and ask `Proceed? [y/N]` first. They warn you if the description differs from the one used to choose the categories. Unlike `research_monitor`, they don't check the description first, don't take extra details, and **don't write the report**. An older `research_report.txt` may still be in `data`, describing an earlier run.

For example, to try another description on papers you've already downloaded, without contacting arXiv again:

```powershell
find_paper_matches "I study neural machine translation for Basque and other low-resource European languages."
```

## Files in `data`

| File | Contents |
|---|---|
| `research_report.txt` | The readable report (written by `research_monitor` only). |
| `selected_categories.csv` | The accepted categories: code, field, name, the reason each was suggested, and your description. |
| `retrieved_papers.csv` | Every downloaded paper: arXiv ID, title, abstract, authors, first submission date and time, categories, arXiv DOI and journal reference if supplied, and links. |
| `paper_matches.csv` | Selected papers with reasons and publication status. `publication_doi` is a possible Crossref match when arXiv supplied no DOI; review it manually. Copilot also records material and database names found verbatim in the title or abstract. With option `h`, there's also `relevance_score`. |
| `paper_matches_settings.json` | Option `h` only: the models, keyword search terms, shortlist percentage and size, request counts, token use, retries and timing of the run that wrote `paper_matches.csv`. It's deleted when option `l` replaces the matches. |
| `paper_embeddings.json` | Option `h` only: saved paper embeddings, reused so repeat runs on the same papers make no new embedding requests. You can delete it; it's rebuilt when needed. |
| `arxiv_taxonomy.csv` | arXiv's category list (see below). Part of the project; don't delete it. |

Each run replaces the files it writes.

After screening, the program queries Crossref for each selected DOI, or searches by title and first author when arXiv gives no DOI. A journal-article record is a publication indicator, not proof of peer review; a missing DOI or a failed search is also inconclusive. The lookup is not exhaustive and does not check the publisher's peer-review policy.

## Monthly local workflow

First accept categories using `research_monitor --interest-file data\research_focus.txt`. The saved `selected_categories.csv` must contain the same focus as the file; a changed focus requires choosing categories again.

For a manual test, run `monthly_monitor manual`. It asks how many days to fetch (1–90), ending three days ago, and previews the run with at most one screening prompt by default. You can set `--max-prompts` to 1–5. It does not screen until you separately approve the resulting snapshot using the printed command.

```powershell
monthly_monitor prepare --max-prompts 2
```

`prepare` fetches arXiv and saves a dated snapshot but makes **no model calls**. It prints the counts and the SHA-256 approval command for that exact plan. Review the counts and shortlist in `plan.json`, then personally run the printed `monthly_monitor screen --plan ... --approve ...` command. Neither command prompts. Do not automatically approve a plan: the user requested approval before screening. A plan is single-use, even on failure. Make a new plan for another attempt; a failed batch may already have consumed usage.

The default window is 30 inclusive UTC days, ending three days before today. Options: `--days` (1–90), `--lag` (3–30 days), `--shortlist-percent` (1–100, default 10), `--max-prompts` (required, 1–5), `--focus` and `--categories`. More than the approved prompt limit stops before screening; reduce the window or shortlist and prepare again. `prepare` can still preview an over-limit plan.

Local BM25 ranks titles and abstracts using the focus text; only the top percentage with nonzero scores are sent to Copilot. This reduces volume but can miss relevant work, especially materials with different terminology. It does not use embeddings or the OpenAI API. Screening uses `gpt-6-luna`, classified as a lightweight model in [GitHub's pricing table](https://docs.github.com/en/copilot/reference/copilot-billing/models-and-pricing); its availability and pricing may change. Each prompt holds up to 40 papers and the preview shows the model and prompt count. Prompt counts are not token or credit estimates. Check your account's model access, usage and budget separately.

Runs are saved under `data\monthly_runs\<UTC timestamp>-<unique ID>\`: `plan.json` and a report named `research_report-<UTC timestamp>-<unique ID>.txt`. Each report has a different date and ID, even for repeated runs in the same month. Checkpoints update only that run's report and never overwrite another run. A partial failure exits nonzero and keeps an **INCOMPLETE** report; a started plan cannot be replayed. A process crash between receiving a response and saving its checkpoint can lose that response. Crossref checks may also be inconclusive. The output is based on titles and abstracts only; DOI or journal metadata cannot confirm peer review.

Automation still needs an external scheduler to run `prepare`, deliver its preview to the user, and invoke `screen` only after that user approves the exact hash. It also needs failure alerts, durable backups and periodic checks of credentials, model access and relevance quality. Date ranges may overlap or leave gaps if schedules are delayed; arXiv announcements can lag. The repository does not configure a scheduler.

### Fresh local workspaces

The approved focus and categories are also saved as `data\research_focus.txt` and `data\monthly_categories.csv`. They must be integrated into the branch checked out by each new automation workspace, together with the program changes. The default `data\selected_categories.csv` is gitignored and won't be present in a fresh checkout. If the focus changes, select and approve categories again and update the monthly snapshot; the program refuses mismatched inputs.

In each fresh checkout, use Python 3.12+, `curl.exe`, and a virtual environment with `pip install -e .`. The Copilot SDK also needs its compatible runtime, network access, and a signed-in Copilot account available to that same local user; GitHub token environment variables can take precedence over CLI login. Verify model access and GitHub budgets for the account running the job.

Use an **absolute, durable local directory outside the temporary checkout** for plans and reports, for example:

```powershell
monthly_monitor prepare --categories data\monthly_categories.csv --runs-dir (Join-Path $env:LOCALAPPDATA 'AcademicResearchMonitor\runs') --max-prompts 1
```

Deliver the printed preview and plan hash to the user. After explicit approval, use the printed `screen` command and exact plan path; a fresh checkout must contain the same screening code and model settings or the plan is refused. The local account must have read/write access to the same directory in both runs. Back up that directory and the earlier worktree-local report separately; this option does not move earlier reports. Do not have the scheduler automatically copy or approve the hash.

## The timing summary

At the end of a run, `research_monitor` prints how long each stage took. Time spent waiting for your answers isn't included. For option `h` it also shows how many papers were embedded new or reused from the saved embeddings, and how many retries there were. Copilot screening reports completed prompts, not token consumption or charges.

## Settings

Settings are constants at the top of each file in `scripts`. For example:
- `SHORTLIST_PERCENT` in `rerank_papers.py`: the share of papers option `h` passes to the AI (10, rounded up)
- `MODEL` in `copilot_provider.py`: the Copilot model for checks, categories and screening; availability depends on your account.
- `MAX_COPILOT_BATCHES` in `find_paper_matches.py`: maximum screening prompts per run. Larger runs stop rather than producing a misleading partial selection.

After changing anything in `scripts`, run the tests.

## Other project tasks

```powershell
python -m unittest                         # run the automated tests (no OpenAI or arXiv requests)
python scripts/extract_arxiv_taxonomy.py   # rebuild data\arxiv_taxonomy.csv from arXiv's category page
```

## arXiv category list

`data\arxiv_taxonomy.csv` holds arXiv's category list (155 categories in 8 fields). The program checks the AI's category suggestions against it.

| Column | Meaning |
|---|---|
| `field` | Top-level group, e.g. `Computer Science`, `Physics` |
| `subfield` | What arXiv calls an "archive", e.g. `Astrophysics`. Only Physics has these; the column is blank elsewhere. |
| `subject` | Category name, e.g. `Artificial Intelligence` |
| `code` | arXiv category code, e.g. `cs.AI` |
| `description` | arXiv's description of the category |
