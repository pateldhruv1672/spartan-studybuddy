# Spartan StudyBuddy — DGX Spark deployment runbook

## 0. Unzip and configure

```bash
unzip Spartan-StudyBuddy-Postgres-PGVector-Complete.zip
cd spartan-studybuddy
cp .env.example .env
```

Only runtime configuration belongs in `.env` (tokens/passwords/model settings). No source-code edits are required.

## 1. One-time Spark setup

```bash
make dgx-setup
make doctor
```

This starts PostgreSQL 16 + pgvector, creates the backend venv, installs dependencies, pulls vLLM and builds the training image.

Recommended before the event:

```bash
python3 scripts/models/prefetch_models.py
```

## 2. Hard integration gate

```bash
make test
```

This starts the real pgvector database, runs the backend integration suite, verifies the PostgreSQL vector schema, and runs the Chrome + VS Code extension contract tests. Do not proceed to demo freeze if this command fails.

## 3. Fine-tune and prove the model

Fast pipeline check:

```bash
make train-smoke
```

Full competition experiment:

```bash
INCLUDE_HF_DATASETS=1 make competition
```

Pipeline:

```text
mode-conditioned tutoring data
  → Qwen3-32B LoRA/QLoRA
  → merge
  → held-out base/tuned quality evaluation
  → standard vLLM benchmark
  → n-gram speculative benchmark
  → optional Eagle-3 benchmark
  → measured serving-profile selection
```

## 4. Start Spartan StudyBuddy

```bash
make seed
make start
```

Open from the MacBook:

```text
http://<DGX-SPARK-LAN-IP>:8000
```

## 5. Install client extensions

Chrome:

1. Unzip `dist/extensions/spartan-studybuddy-chrome.zip`.
2. Open `chrome://extensions`, enable Developer Mode, choose **Load unpacked**.
3. Open the extension, set the Spark API URL, press **Refresh workspaces**, select the workspace, save.

VS Code:

```bash
code --install-extension dist/extensions/spartan-studybuddy-vscode.vsix
```

Then run **Spartan StudyBuddy: Connect to Workspace** from the Command Palette. Workspace selection is saved at VS Code workspace scope.

## 6. Mac Browser-Use bridge

```bash
./scripts/mac/setup_browser_use.sh
cp .env.mac.example .env.mac
# STUDYBUDDY_API=http://<DGX-SPARK-IP>:8000
./scripts/mac/launch_studybuddy_chrome.sh
./scripts/mac/start_bridge.sh
```

## 7. Observability

Start the self-hosted observability stack with the deployment Compose configuration documented under `deploy/observability/`. The backend exposes Prometheus metrics and stores local agent traces in PostgreSQL. Hosted LangSmith export is optional.

## Emergency checks

```bash
make db-status
make models-health
make extensions-test
make doctor
curl http://127.0.0.1:8000/api/health
```
