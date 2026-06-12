# Local Run Notes

This workspace is configured to run in local mock mode by default, so you can open
the Streamlit app without Google Vertex AI credentials.

## Setup

```powershell
.\.venv\Scripts\python.exe setup_database.py
.\.venv\Scripts\streamlit.exe run main.py
```

Then open the local URL printed by Streamlit, usually:

```text
http://localhost:8501
```

## Local Mock Mode

`.env` contains:

```text
AGENT_MODE=mock
LOCAL_MOCK_MODE=true
```

In this mode, the app uses `virtual_sales_agent/local_graph.py`, a deterministic
local graph that can answer simple product, category, recommendation, and order
status questions from SQLite.

## Real Model Mode

To use an OpenAI-compatible chat model, edit `.env`:

```text
AGENT_MODE=openai
OPENAI_API_KEY=your_key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

Many providers expose OpenAI-compatible APIs. In that case, set
`OPENAI_BASE_URL` and `OPENAI_MODEL` to the provider's values.

## Doubao / Volcengine Ark Mode

For Doubao through Volcengine Ark, edit `.env`:

```text
AGENT_MODE=doubao
LOCAL_MOCK_MODE=false
DOUBAO_API_KEY=your_ark_api_key
DOUBAO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
DOUBAO_ENDPOINT_ID=your_endpoint_id
OPENAI_TEMPERATURE=0.2
```

Use the endpoint id from your Ark console as `DOUBAO_ENDPOINT_ID`.

To use the original Gemini/Vertex AI agent, set:

```text
AGENT_MODE=vertex
LOCAL_MOCK_MODE=false
```

Then fill in the Google and LangSmith environment variables.
