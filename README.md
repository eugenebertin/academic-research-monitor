# Academic Research Monitor

Academic Research Monitor finds new [arXiv](https://arxiv.org) papers that match your research interests. You describe your interests in your own words, and the program:

1. suggests arXiv categories to follow, for you to accept or revise,
2. downloads every paper posted in those categories between two dates,
3. asks an AI model which papers fit your description, with a one-sentence reason for each.

You answer its questions in a Windows PowerShell window.

**Before you start:**
- **Cost.** The normal path uses your signed-in GitHub Copilot account. Input checks and category selection already use Copilot before the screening confirmation. Screening shows the number of prompts and defaults to a maximum of 25; it does not estimate token use or cost. Allowances and billing depend on your account and model; check [GitHub's pricing](https://docs.github.com/en/copilot/reference/copilot-billing/models-and-pricing) and your budget. Downloading from arXiv is free.
- **Privacy.** Your research description and the papers' titles and abstracts are sent through Copilot to its model provider.
- **Limits.** The AI judges each paper from its **title and abstract only**, never the full text. It can miss relevant papers or include irrelevant ones, so check each result yourself.

---

## Setup (once)

You need:
- **Git:** <https://git-scm.com/download/win> (default options are fine)
- **Python 3.12 or newer:** <https://www.python.org/downloads/>. On the installer's first screen, tick **"Add python.exe to PATH"**.
- **A GitHub Copilot account:** sign in with the [Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/cli-getting-started). The SDK uses the stored CLI sign-in by default; environment credentials can take precedence.

Open **Windows PowerShell** (press the Windows key and type `PowerShell`). Paste each block with right-click or **Ctrl+V**, and press **Enter**.

Check the tools. Each command should print a version; type `curl.exe` exactly, including `.exe`:

```powershell
git --version
py --version
curl.exe --version
```

Download the project and go into its folder:

```powershell
git clone https://github.com/notrealjulia/academic-research-monitor.git
cd academic-research-monitor
```

Create a virtual environment (a private Python setup for this project), switch it on, and install the program:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

The prompt should now start with `(.venv)`. If activation fails with *"running scripts is disabled on this system"*, see [Troubleshooting](docs/troubleshooting.md).

The SDK downloads its matching runtime on first use. A separate OpenAI API key and billing are needed only for the experimental hybrid option and OpenAI experiments.

---

## Running it

```powershell
research_monitor
```

To start with the supplied thin-film research focus, use `research_monitor --interest-file data\research_focus.txt`. You can still revise it when choosing categories.

Type each answer on a single line and press **Enter**. Press **Ctrl+C** to stop at any time.

1. **Research interests.** Describe what you study and want to read about, including what you're *not* interested in. For example:
   > I study machine translation for low-resource and regional European languages, such as Basque, Welsh or Sámi. I want new methods, datasets and evaluations, especially for dialects. I am not interested in speech recognition without translation.

   The AI checks that the description is specific enough. It then suggests categories: type `a` to accept, `r` to revise your description, or `x` to exit.
2. **Dates.** Enter a start and end date as day-month-year, e.g. `21-09-2026`, or press Enter for today. Both days count. The last day or two may be incomplete, because arXiv lists papers only once it has announced them.
3. **Download.** Papers in your categories are downloaded from arXiv. This is free, but takes a moment for long date ranges.
4. **Optional details.** Add anything that narrows the selection, e.g. *"only papers with new datasets"* or *"skip surveys"*. Press Enter to skip.
5. **Matching.** Choose how the AI screens the papers:
   - **`l`: screen every paper.** The AI reads the title and abstract of every downloaded paper. This is the most thorough option, and it costs the most on large downloads.
   - **`h`: search first, then screen the top 10% (experimental).** This entire path uses the separately billed OpenAI API, including embeddings and screening; Copilot does not provide these embeddings. A relevant paper that search ranks low is never screened. [How it works](docs/experiments.md#the-search-first-option-in-research_monitor).

   The program shows how many papers and requests it will send, then asks `Run matching? [y/N]`. Type `y` to start. Anything else stops without sending anything.

At the end it lists the matches and prints how long each stage took.

---

## Your results

Results are saved in the `data` folder. To open it:

```powershell
explorer data
```

- **`research_report.txt`:** start here. It includes your search, the categories and dates, and every selected paper with its reason, link and abstract. Where the title or abstract names a material or database, the Copilot path can list it as a lead. These are not verified growth recommendations or database records: check synthesis history and suitability yourself. It's written only when matching runs. If matching stopped partway, it says **INCOMPLETE** at the top.
- Selected papers' arXiv-supplied DOIs are checked against Crossref. If no DOI is supplied, the program searches Crossref for a possible journal article with the same title and first author. This is a lead, not a verified match; a journal DOI alone does **not** establish peer review. Missing, unmatched or failed lookups do not mean a paper is unreviewed.
- **`paper_matches.csv`:** the selected papers, as a spreadsheet.
- **`retrieved_papers.csv`:** every downloaded paper.
- **`selected_categories.csv`:** the categories you accepted.

**Each run replaces these files.** Copy them elsewhere if you want to keep them.

---

## Next time

Open PowerShell, then:

```powershell
cd academic-research-monitor
.\.venv\Scripts\Activate.ps1
research_monitor
```

For a manual test, run `monthly_monitor manual` and enter how many days to fetch. For a future local monthly run, `monthly_monitor prepare --max-prompts 2` fetches a preview without calling a model. After reviewing either preview, a person must approve that exact snapshot using the printed `monthly_monitor screen` command. Reports are saved separately by run. See [monthly usage](docs/advanced_usage.md#monthly-local-workflow) before automating; no scheduler is installed.

---

## More help

- [Troubleshooting](docs/troubleshooting.md): installation problems, error messages, no papers found
- [Advanced usage](docs/advanced_usage.md): running single steps, file contents, settings
- [Experiments](docs/experiments.md): how the search-first option works, and the search and judge experiments
