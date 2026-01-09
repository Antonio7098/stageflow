# Stageflow Test Application

A Flask-based test application to demonstrate and test the stageflow pipeline framework.

## Features

- **DAG Visualization**: Real-time visualization of pipeline stages with node highlighting during execution
- **Observability Panel**: Live logs and events from pipeline execution
- **Chat Interface**: Interactive chat to trigger pipelines with real LLM responses (Groq)
- **Pipeline Switching**: Switch between different pipeline configurations
- **Resizable Panels**: Drag to resize all panels

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Copy `.env.example` to `.env` and add your Groq API key:
```bash
cp .env.example .env
# Edit .env and add your GROQ_API_KEY
```

3. Run the application:
```bash
python app.py
```

4. Open http://localhost:5000 in your browser

## Pipelines

The app includes several pipelines of increasing complexity:

1. **Simple Echo**: Single stage that echoes input (tests basic execution)
2. **Transform Chain**: Linear chain of transform stages (tests dependencies)
3. **Parallel Enrich**: Parallel enrichment stages (tests parallel execution)
4. **LLM Chat**: Real LLM integration with Groq (tests external APIs)
5. **Full Pipeline**: Complete pipeline with routing, enrichment, LLM, and guards (tests all features)

## Architecture

```
test_app/
├── app.py              # Flask application entry point
├── pipelines/          # Pipeline definitions
│   ├── __init__.py
│   ├── simple.py       # Simple echo pipeline
│   ├── transform.py    # Transform chain pipeline
│   ├── parallel.py     # Parallel enrichment pipeline
│   ├── llm.py          # LLM chat pipeline
│   └── full.py         # Full feature pipeline
├── stages/             # Stage implementations
│   ├── __init__.py
│   ├── echo.py
│   ├── transform.py
│   ├── enrich.py
│   ├── llm.py
│   ├── guard.py
│   └── router.py
├── services/           # Service implementations
│   ├── __init__.py
│   ├── groq_client.py  # Groq LLM client
│   └── mocks.py        # Mock services
├── static/
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── app.js
└── templates/
    └── index.html
```
