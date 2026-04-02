# CERBERUS MVP - Quick Start Guide

## Local Development Setup

### Prerequisites
- Python 3.10+
- PostgreSQL 13+
- OpenAI API key
- Anthropic API key

### 1. Clone and Install

```bash
cd cerberus-build
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Setup Database

```bash
# Start PostgreSQL locally
# Option A: Using Docker
docker run -d \
  --name cerberus-db \
  -e POSTGRES_DB=cerberus \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 \
  postgres:15

# Option B: Use existing PostgreSQL installation
```

### 3. Configure Environment

```bash
cp .env.example .env
```

Edit `.env`:
```
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
SARAH_MODEL=gpt-5.4
CLAUDE_MODEL=claude-opus-4-6
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/cerberus
PORT=8000
```

### 4. Run the App

```bash
python -m uvicorn app.main:app --reload --port 8000
```

Visit: http://localhost:8000

### 5. Test

Open two browser windows/tabs:
- Both connect to the same session
- Type a message in one window
- Watch it appear in both windows
- Watch as Sarah and Claude respond

Try:
- Message routing: "Sarah Only", "Claude Only", or "Both"
- Multi-turn conversations (each response is added to history)
- Typing indicators while waiting for responses

## Railway Deployment

### Step 1: Create Railway Project
```bash
npm i -g railway
railway login
railway init  # Select "Empty" project
```

### Step 2: Add PostgreSQL
```bash
railway add  # Select PostgreSQL
```

This auto-creates DATABASE_URL environment variable.

### Step 3: Set Environment Variables
```bash
railway variables set OPENAI_API_KEY=sk-...
railway variables set ANTHROPIC_API_KEY=sk-ant-...
railway variables set SARAH_MODEL=gpt-5.4
railway variables set CLAUDE_MODEL=claude-opus-4-6
railway variables set PORT=8000
```

### Step 4: Link GitHub (Optional)
```bash
# Push to GitHub
git init
git add .
git commit -m "Initial CERBERUS MVP"
git remote add origin https://github.com/you/cerberus.git
git push -u origin main

# In Railway dashboard, connect GitHub repo
# Railway will auto-deploy on git push
```

Or upload code directly via Railway CLI:
```bash
railway up
```

### Step 5: Verify Deployment
```bash
railway logs
railway env
```

Your app will be at: `https://your-project.railway.app`

## Troubleshooting

### Database Connection Error
```
Error: could not connect to server
```
- Verify DATABASE_URL format
- Check PostgreSQL is running
- Test with: `psql $DATABASE_URL`

### API Key Errors
```
401 Unauthorized
```
- Verify OPENAI_API_KEY and ANTHROPIC_API_KEY are correct
- Check they're set in .env (local) or Railway variables (deployed)

### WebSocket Connection Fails
```
WebSocket connection failed
```
- Check browser console for errors
- Verify app is running: `curl http://localhost:8000/api/health`
- Check CORS if behind proxy

### Agents Not Responding
```
Error: Unexpected response structure
```
- Verify API keys are valid (not expired/revoked)
- Check rate limits
- Look at server logs for full error details

## Project Structure Overview

```
cerberus-build/
├── app/
│   ├── main.py          # FastAPI app + routes
│   ├── config.py        # Environment config
│   ├── models.py        # Pydantic schemas
│   ├── db.py            # Database layer
│   ├── ws_manager.py    # WebSocket connections
│   ├── agents.py        # API calls to Sarah/Claude
│   └── orchestrator.py  # Message routing logic
├── static/
│   └── index.html       # Web UI
├── requirements.txt     # Python deps
├── .env.example        # Config template
├── Procfile            # Deployment config
├── railway.toml        # Railway nixpacks config
└── IMPLEMENTATION.md   # Architecture details
```

## API Endpoints

### Health Check
```bash
curl http://localhost:8000/api/health
# {"status": "ok"}
```

### Create Session
```bash
curl -X POST http://localhost:8000/api/sessions \
  -H "Content-Type: application/json" \
  -d '{"user_id": "matthew", "user_label": "Matthew"}'
# {"session_id": "ses_...", "user_id": "matthew", "created_at": "..."}
```

### Get Events
```bash
curl "http://localhost:8000/api/sessions/ses_.../events?thread_id=thr_main&limit=100"
# {"events": [...]}
```

### WebSocket (via Browser)
```javascript
const ws = new WebSocket(`ws://localhost:8000/ws/ses_...`);
ws.onopen = () => {
  ws.send(JSON.stringify({
    command: "send_message",
    session_id: "ses_...",
    thread_id: "thr_main",
    payload: {
      text: "Hello!",
      target: "both",
      message_type: "query"
    }
  }));
};
ws.onmessage = (e) => console.log(JSON.parse(e.data));
```

## File Reference

### requirements.txt
Core dependencies with pinned versions. Update with:
```bash
pip install -r requirements.txt --upgrade
pip freeze > requirements.txt
```

### .env.example
Template for environment variables. Never commit .env (it's in .gitignore).

### Procfile
Traditional deploy format. Railway uses nixpacks, but Procfile is a fallback.

### railway.toml
Explicit Railway configuration. Specifies nixpacks builder and start command.

## Next Steps

1. **Test locally** - Run `python -m uvicorn app.main:app --reload`
2. **Deploy** - Use Railway CLI or connect GitHub
3. **Monitor** - Check Railway logs for errors
4. **Iterate** - Update code, git push, Railway auto-deploys

## Documentation

See `IMPLEMENTATION.md` for:
- Detailed architecture
- Event system design
- Component documentation
- Data model schema
- Future roadmap

## Support

- FastAPI docs: http://localhost:8000/docs (when running locally)
- Railway docs: https://docs.railway.app
- OpenAI docs: https://platform.openai.com/docs
- Anthropic docs: https://docs.anthropic.com
