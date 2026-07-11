# Deploying for free (no Railway)

Railway dropped its free tier. Here are two fully-free ways to run this app.
Both keep the frontend on **Vercel (free)** and the database on **Supabase (free)** —
only the backend host changes.

---

## Option A — Render free + GitHub Actions cron (easiest)

Free web hosts sleep when idle, so we don't rely on the in-process scheduler.
Instead a free GitHub Actions cron POSTs to `/api/run-committee` at market times
(it also wakes the sleeping host).

1. **Backend → Render**
   - Render dashboard → **New → Blueprint** → select this repo (uses `render.yaml`).
   - When prompted, fill the secret env vars: `GROQ_API_KEY`,
     `DATABASE_URL`, `FINNHUB_API_KEY`, `FMP_API_KEY`,
     `FRONTEND_URL`, and a `CRON_SECRET` (any random string you choose).
   - `ENABLE_SCHEDULER=false` is set by the blueprint.
   - Note your service URL, e.g. `https://ai-hedge-fund-api.onrender.com`.

2. **Cron → GitHub Actions** (already in `.github/workflows/committee.yml`)
   - Repo → **Settings → Secrets and variables → Actions → New repository secret**:
     - `BACKEND_URL` = your Render URL (no trailing slash)
     - `CRON_SECRET` = the same value you set on Render
   - The workflow runs weekdays at 16:00 UTC; it's skipped when the US market is closed.
   - Test it now: **Actions tab → Trading Committee → Run workflow**.

3. **Frontend → Vercel** (unchanged): set `VITE_API_URL` to your Render URL.

**Trade-off:** ~30–60s cold start on the first request after the host sleeps. The
cron wakes it first, so committee runs still complete.

---

## Option B — Oracle Cloud Always-Free VM (most robust, always-on)

A genuinely always-free 24/7 VM. The in-process scheduler works exactly like it
did on Railway — no GitHub cron needed.

1. Create an **Oracle Cloud** account → launch an **Always Free** Ampere (ARM) VM
   (Ubuntu). Credit card is used for identity only; Always-Free never charges.
2. SSH in, then:
   ```bash
   sudo apt update && sudo apt install -y python3-pip git
   git clone https://github.com/MozartofCode/AI-Hedge-Fund.git
   cd AI-Hedge-Fund
   pip install -r requirements.txt
   cp .env.example .env   # then edit .env with your keys (or create it)
   ```
3. Set `ENABLE_SCHEDULER=true` (default) so the built-in scheduler runs.
4. Run it under systemd or `tmux`:
   ```bash
   uvicorn backend.main:app --host 0.0.0.0 --port 8000
   ```
5. Open port 8000 in the VM's security list, point the frontend's `VITE_API_URL` at it.

---

## Environment variables (both options)

| Var | Purpose |
|-----|---------|
| `GROQ_API_KEY` | LLM provider for all agents + Chairman (free Llama via Groq) |
| `ENABLE_SCHEDULER` | `true` on always-on hosts; `false` on free/sleeping hosts |
| `CRON_SECRET` | Shared secret; if set, `/api/run-committee` requires `X-Cron-Secret` |
| `DATABASE_URL` | Supabase Postgres connection string |
| `FINNHUB_API_KEY`, `FMP_API_KEY` | Market data |
| `FRONTEND_URL` | Allowed CORS origin |
