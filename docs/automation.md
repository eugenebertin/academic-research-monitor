# Monthly automation

This guide sets up a **local GitHub Copilot app automation** for a single researcher on Windows. The app starts a fresh worktree for each run. The automation prepares a preview, but a person must approve that specific preview before the monitor screens papers.

> **Before enabling:** the computer and app must be available at the scheduled time. An automation is not a guaranteed delivery or alert service; check its runs and failures. Do not enable a second schedule for the same monitor unless you want duplicate runs.

## 1. Set up the repository

Clone this repository, register it in the Copilot app, and follow the [README setup](../README.md#setup-once). You need Python 3.12 or newer, Git, `curl.exe`, network access, and a signed-in Copilot account with access to the configured model. The SDK may download its runtime on first use. Check your account's usage and budget.

The monitor sends only titles and abstracts to Copilot, not full papers. Its local BM25 shortlist can miss relevant papers; material names and database references are unverified leads. A Crossref journal record is not proof of peer review. The automation agent itself can also consume Copilot credits; neither prompt counts nor this guide predict token use or cost.

## 2. Save your focus and categories

The repository includes an example thin-film focus and approved categories in `data\research_focus.txt` and `data\monthly_categories.csv`. Use them only if they describe **your** interests. To create your own, make a durable folder outside the checkout:

```powershell
$inputs = Join-Path $env:LOCALAPPDATA 'AcademicResearchMonitor\inputs'
New-Item -ItemType Directory -Force -Path $inputs | Out-Null
notepad (Join-Path $inputs 'focus.txt')
```

Write your research description and save it as UTF-8. In the installed repository, run:

```powershell
research_monitor --interest-file (Join-Path $inputs 'focus.txt')
```

Copilot checks the description and suggests categories; these calls use Copilot before screening. Accept or revise the suggestions. Once categories are accepted, stop at the date prompt with **Ctrl+C**; there is no need to fetch or screen papers during setup. If you revised the description, update `focus.txt` to the exact accepted description. Then save the accepted categories:

```powershell
Copy-Item -LiteralPath 'data\selected_categories.csv' -Destination (Join-Path $inputs 'categories.csv')
```

That command replaces an existing destination file. Back it up first if needed. The monitor requires the focus file to match the description saved in the categories file exactly; choose and approve categories again when changing the focus. These input files are local to your account: back them up, do not commit sensitive research interests, and ensure the automation account can read them.

## 3. Choose durable output

Use an absolute directory outside disposable worktrees, for example:

```powershell
$runs = Join-Path $env:LOCALAPPDATA 'AcademicResearchMonitor\runs'
```

Each run saves its plan, approval marker and uniquely named report in its own dated folder. Keep **all three** for completed runs: they establish date coverage for the next run. Back up the directory. Copy an existing completed run's entire folder there if you want to continue from it; this does not happen automatically.

The first automatic preview covers 30 days ending three days ago. Later previews continue after contiguous completed coverage for the same focus and categories. Incomplete or unapproved runs cannot advance coverage. If more than 90 days are due, the oldest 90 are prepared first; approve further runs to catch up. Delayed arXiv announcements can still be missed.

## 4. Create the automation

In the Copilot app's **Automations** view, create a local automation for the registered repository. Use a fresh **worktree**, interactive mode, and a low-cost available model. Set a local schedule, for example `0 9 28 * *` for 09:00 on the 28th of each month. Review the saved settings and enable it only after checking for duplicate schedules. App-local schedules use the computer's local time.

Use the following as the task instructions, replacing the focus, category and runs paths with your own **absolute** paths. The model named below is the monitor's configured screening model; check that it is available to your account and adjust the instruction if the program's model changes.

```text
Use this repository in a fresh local worktree. My focus is at <absolute focus.txt path>,
my approved categories are at <absolute categories.csv path>, and my durable runs
directory is <absolute runs directory>. Do not change these inputs or delete any runs.

Determine whether this run was launched manually or on schedule: use
get_session_automation to identify this session ID, and list_workflows to find
the run with that exact session ID and its trigger. If the trigger is unavailable
or ambiguous, stop and report the problem; do not guess. For a manual run, ask
me how many days to fetch (1-90), and use --days with that answer and
--max-prompts 1. For a scheduled run, omit --days and use --max-prompts 2.

Use Python 3.12+, curl.exe and a worktree-local virtual environment with the
repository's declared dependencies. Run monthly_monitor prepare with --focus,
--categories and --runs-dir set to the paths above and the options for this run.
Use no OpenAI API, embeddings or provider fallback. Preparation makes no
monitor model calls.

Show me the plan path and SHA-256, date range, retrieved and shortlisted counts,
screening model, batch size and prompt count. Explain the title-and-abstract-only
and local-ranking limits and that token use and charges are not estimated. Stop
if the prompt cap is exceeded, the model is not gpt-6-luna or the batch size
exceeds 40. Ask me to approve or decline this exact snapshot. A hash, silence
or these instructions are not approval. Only after my explicit approval run the
printed monthly_monitor screen command with that plan and hash. Otherwise stop.
On errors or incomplete output, report the status; never retry a started plan.
Show the report path and explain that materials and database names are unverified
leads and a journal DOI does not prove peer review. Do not commit or push.
```

The agent can use `.\.venv\Scripts\monthly_monitor.exe` in its worktree after installing the package. Test manually only when you are ready: the automation should ask for a day count, then show a preview. Approve only after reviewing the count and exact plan. If the app cannot determine the trigger or cannot deliver the approval question, the instructions require it to stop rather than screen.

## 5. Review and maintain

Open the resulting `research_report-<timestamp>-<ID>.txt` in the durable runs folder. A failed screening leaves an **INCOMPLETE** checkpoint and the same plan cannot be restarted. Prepare a new plan after resolving the error; a failed batch may already have consumed usage. If a preview is above the prompt cap, prepare a shorter window or reduce the shortlist percentage rather than bypassing approval.

Periodically check the automation's run history, account sign-in, model availability, budget, backups and result quality. Changes to the screening code or model invalidate a previously prepared plan; prepare and approve a new one. See [advanced usage](advanced_usage.md#monthly-local-workflow) for all bounds and recovery details.
