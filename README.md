# NexusAI Sales Workspace

NexusAI has two app entry points:

- `index.html`: the interactive static dashboard used by the Vercel deployment. It includes inbound scoring/reply drafts, outbound campaign drafts, objection battlecards, CSV export, and a CRM stored in the browser's local storage. Dashboard figures are calculated from that CRM.
- `app.py`: the Streamlit version, with login, rep filtering, SQLite storage, and optional Gemini integration. Scoring and storage live in `sales_core.py`.

Both apps use the same lead-scoring rules (`score_lead()` in `sales_core.py`, `scoreLead()` in `index.html`). Change them together.

## Local run

Requires Python 3.11 or newer (current Streamlit releases no longer support 3.9 or 3.10).

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Then open the local Streamlit URL in your browser.

To try the static app, serve the folder and open `http://localhost:8000/index.html`:

```bash
python3 -m http.server 8000
```

## Sign-in accounts

If no accounts are configured, the app falls back to built-in demo accounts and says so on the sign-in page:

- admin / sales123
- tanvir / sales123
- nadia / sales123
- farhan / sales123

**Configure real accounts before deploying anywhere public.** Either add them to `.streamlit/secrets.toml` (or Streamlit Cloud secrets):

```toml
[users]
admin = "a-long-unique-password"
tanvir = "another-long-unique-password"
```

or set an environment variable:

```bash
export NEXUSAI_USERS="admin:a-long-unique-password,tanvir:another-long-unique-password"
```

Once any account is configured, the demo accounts stop working. `admin` sees and manages every lead and is the only account that can reset the pipeline. Every other username is a sales rep (named after the username, e.g. `tanvir` → `Tanvir`) and can view, edit, and delete only their own leads.

## Optional AI setup

For the Streamlit app, provide a Gemini API key as either:

- a Streamlit Cloud secret named `GEMINI_API_KEY`, or
- an environment variable in your local shell, or
- the key field in the app's sidebar.

The model defaults to `gemini-3.8-flash`; override it with the `GEMINI_MODEL` environment variable. If a Gemini call fails, the app shows a warning and uses its built-in draft.

For the static `index.html` app, use its API Key button. The key stays in the current browser session and is sent from that browser to Google in a request header. Do not enter a key on a shared device. The model is set by `GEMINI_MODEL` near the top of the page's script. Both apps work without a key using built-in drafts.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The tests drive `app.py` with Streamlit's `AppTest` against a temporary database, so they never touch `sales_pipeline.db`.

## Deployment

The Vercel site serves `index.html` as a static app; its CRM data is local to each browser and is not shared across devices or users. Push changes to the connected Git repository to trigger a Vercel deployment. Its third-party scripts are pinned to exact versions (the icon library is also integrity-checked), so update those URLs deliberately.

The Streamlit version is structured for standard Streamlit deployment patterns and includes:

- `requirements.txt`
- `Procfile`
- `.streamlit/config.toml`
- `Dockerfile` for container-compatible hosts

Deploy `app.py` to Streamlit Community Cloud or another Streamlit-compatible host. The Vercel site and Streamlit version are separate deployments; the Vercel site does not run the Python app.

## Notes

- Data is stored in `sales_pipeline.db` next to `app.py`. Set `SALES_DB_PATH` to use a different file.
- Older databases are upgraded automatically on startup (missing rep/stage columns are added and the legacy `Referral` channel becomes `Customer Referral`).
- Each save, edit, or delete changes only that lead's row, so several people can use the app at once without overwriting each other. SQLite still suits small teams only; use a proper database server for heavier production use.
