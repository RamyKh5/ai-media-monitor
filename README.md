ai-media-monitor
1. Overview
The AI Media Monitoring System is an automated, multi‑agent platform designed for internal Ministry use. It monitors journals, electronic press, social media, and TV broadcasts, shifting from manual, error‑prone monitoring to an intelligent pipeline that summarizes content and flags potentially harmful information for human verification.

2. System Architecture
The system uses a modular multi‑agent pipeline built on LangGraph. Each input source (Press, Web, TV, Social) is processed by a specialized adapter node, unified into a standardized data model, and passed to centralized intelligence agents.

Ingestion: Playwright (Web/Social), OCR Engine (Journals), FFmpeg + Whisper (TV audio).

Intelligence:

ML Classifier for sentiment analysis and risk detection.

Fine‑tuned Synthesis Agent that generates structured summaries and reports.

Orchestration: LangGraph state machine with Human‑in‑the‑Loop (HITL) workflows.

3. Project Structure
Code
ministry-ai-monitor/
├── main.py             # Entry point (workflow graph)
├── state.py            # Data contract (AgentState)
├── nodes/              # Logic units (scraper, ocr, transcriber, classifier, synthesizer)
├── models/             # AI weights & fine-tuned checkpoints (git-ignored)
├── utils/              # DB connections & logging
├── tests/              # Unit & integration tests
├── data/               # Sample inputs or storage
├── .env                # Environment configuration (private, git-ignored)
└── .gitignore          # Excludes .env, models, logs, cache, etc.
4. Setup & Installation
Prerequisites

Python 3.10+

Playwright browser binaries

Database access (PostgreSQL/MongoDB)

Installation

Clone the repository:
git clone https://github.com/RamyKh5/ai-media-monitor.git

Create virtual environment:
python -m venv .venv

Install dependencies:
pip install -r requirements.txt

Install Playwright binaries:
playwright install chromium

Configure .env:
DATABASE_URL=db_connection
OPENAI_API_KEY=your_key
PROXY_URL=your_proxy_config

5. Security & Compliance
Data Isolation: Operates within the Ministry’s secure network.

Audit Trail: All alerts and human verification steps are logged for compliance.

Environment Variables: No credentials are hardcoded. .env is used locally; system variables are required for deployment.

Models: Fine‑tuned weights stored in models/ are git‑ignored to prevent accidental leaks.

6. Development Workflow
Node Addition: Add a new file in nodes/ and update main.py graph logic.

State Updates: Modify state.py when data flow changes to maintain type safety.

Model Integration: Place fine‑tuned weights in models/ and load them inside the relevant node (e.g., classifier.py or synthesizer.py).