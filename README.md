# NexusAI Sales Workspace

NexusAI has two app entry points:

- `index.html`: the interactive static dashboard used by the Vercel deployment. It includes inbound scoring/reply drafts, outbound campaign drafts, objection battlecards, CSV export, and a CRM stored in the browser's local storage.
- `app.py`: the Streamlit version, with login, rep filtering, SQLite storage, and optional Gemini integration.

## Local run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Then open the local Streamlit URL in your browser.

## Demo login

Use any of the built-in demo accounts:

- admin / sales123
- tanvir / sales123
- nadia / sales123
- farhan / sales123

## Optional AI setup

For the Streamlit app, add a Gemini API key as either:

- a Streamlit Cloud secret named `GEMINI_API_KEY`, or
- an environment variable in your local shell

For the static `index.html` app, use its API Key button. The key stays in the current browser session and is sent from that browser to Google. Do not enter a key on a shared device. Both apps work without a key using built-in drafts.

## Deployment

The Vercel site serves `index.html` as a static app; its CRM data is local to each browser and is not shared across devices or users. Push changes to the connected Git repository to trigger a Vercel deployment.

The Streamlit version is structured for standard Streamlit deployment patterns and includes:

- `requirements.txt`
- `Procfile`
- `.streamlit/config.toml`
- `Dockerfile` for container-compatible hosts

Deploy `app.py` to Streamlit Community Cloud or another Streamlit-compatible host. The Vercel site and Streamlit version are separate deployments; the Vercel site does not run the Python app.

## Notes

- Data is stored locally in `sales_pipeline.db` for the demo setup.
- For production use, replace the demo auth flow and local SQLite storage with a more secure backend.
