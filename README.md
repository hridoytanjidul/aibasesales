# NexusAI Sales Workspace

NexusAI is a lightweight sales automation dashboard built with Python and Streamlit. It includes:

- inbound lead qualification
- CRM pipeline management
- rep-based filtering and visibility
- outbound campaign generation
- objection-handling battlecards
- optional Gemini-powered live reply generation

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

Add a Gemini API key as either:

- a Streamlit Cloud secret named `GEMINI_API_KEY`, or
- an environment variable in your local shell

If no key is configured, the app falls back to a polished built-in draft response.

## Deployment

This app is structured for standard Streamlit deployment patterns and includes:

- `requirements.txt`
- `Procfile`
- `.streamlit/config.toml`
- `Dockerfile` for container-based hosting such as Vercel or other Docker-compatible platforms

It is ready for deployment to Streamlit Community Cloud, Docker-compatible hosts, and Vercel using the container approach.

## Notes

- Data is stored locally in `sales_pipeline.db` for the demo setup.
- For production use, replace the demo auth flow and local SQLite storage with a more secure backend.
