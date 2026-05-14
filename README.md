# ✈️ Squadron AI

A **multi-agent AI coding platform** powered by LLMs. Squadron AI uses a team of specialized agents (Manager, Developer, Reviewer) to autonomously debug, fix, and review code via a web interface.

---

## 🏗️ Architecture

```
squadron.ai/
├── api.py              ← FastAPI backend (port 8000) — all AI agent endpoints
├── server.py           ← Flask frontend server (port 5000) — serves HTML pages
├── app.py              ← Streamlit app (alternative UI)
├── opensquad/          ← Core multi-agent framework
│   ├── agents/         ← Manager, Developer, Reviewer agents
│   ├── core/           ← LLM client, state management
│   ├── tools/          ← Batch runner, sandbox, report generator
│   ├── benchmark/      ← Evaluation pipeline
│   └── graph.py        ← LangGraph agent orchestration
├── templates/          ← HTML templates (index, audit dashboard)
├── static/             ← Frontend JS & CSS
└── tests/              ← Test suite
```

---

## ⚙️ Setup

### 1. Clone the repository
```bash
git clone https://github.com/anshurana665/squadron-ai.git
cd squadron-ai
```

### 2. Create a virtual environment
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install dependencies
```bash
# Core multi-agent framework
pip install -r opensquad/requirements.txt

# Web server (FastAPI + Flask)
pip install -r requirements_web.txt
```

### 4. Configure environment variables
```bash
# Copy the example file and fill in your API keys
copy .env.example .env        # Windows
cp .env.example .env          # macOS / Linux
```

Edit `.env` and add your keys:
```env
GROQ_API_KEY="your_groq_api_key"
NVIDIA_API_KEY="your_nvidia_api_key"
GOOGLE_API_KEY="your_google_api_key"

NVIDIA_KEY_MANAGER="your_nvidia_api_key"
NVIDIA_KEY_DEVELOPER="your_nvidia_api_key"
NVIDIA_KEY_REVIEWER="your_nvidia_api_key"
```

Get API keys from:
- 🔑 [GROQ Console](https://console.groq.com/keys)
- 🔑 [NVIDIA API Portal](https://build.nvidia.com)
- 🔑 [Google AI Studio](https://aistudio.google.com/app/apikey)

---

## 🚀 Running the Project

### Option A — Web App (Flask + FastAPI) ⭐ Recommended

Open **two terminal windows** in the project directory:

**Terminal 1 — Start the FastAPI backend:**
```bash
uvicorn api:app --port 8000 --reload
```

**Terminal 2 — Start the Flask frontend:**
```bash
python server.py
```

Then open your browser at:
- 🌐 **Frontend:** http://localhost:5000
- 📊 **Audit Dashboard:** http://localhost:5000/audit
- 📖 **API Docs (Swagger):** http://localhost:8000/docs

---

### Option B — Streamlit App

```bash
streamlit run app.py
```

Then open: http://localhost:8501

---

## 🧪 Running Tests

```bash
# Run all tests
pytest tests/

# Run a specific test file
pytest tests/test_opensquad.py -v

# Run with output
pytest tests/ -v -s
```

---

## 🤖 How It Works

1. **Manager Agent** — breaks down the task, delegates to sub-agents
2. **Developer Agent** — writes and fixes code using LLMs
3. **Reviewer Agent** — reviews the code for quality and correctness
4. **LangGraph** — orchestrates the agent pipeline as a stateful graph
5. **Sandbox** — safely executes generated code in an isolated environment

---

## 📋 Requirements

- Python 3.10+
- API keys for GROQ / NVIDIA / Google Gemini

---

## 📄 License

MIT License
