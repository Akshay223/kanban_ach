# 📋 Kanban Sync

A real-time collaborative Kanban board with multiple projects, email-based team invites, drag-and-drop task management, and live WebSocket sync.

## Features

- **Multiple Projects** — Create as many boards as you want, each with its own team
- **Email Invites** — Add team members by their email ID (no signup needed)
- **Drag & Drop** — Move tasks across 5 columns: To Do → Initiated → In Progress → Ready for Review → Done
- **Real-time Sync** — When anyone moves a card, it instantly updates on everyone else's screen (WebSocket)
- **Task Management** — Title, description, assignee, priority (High/Medium/Low)
- **Shareable Links** — Each project gets its own URL to share with the team

## Tech Stack

- **Backend:** Python Flask + Flask-SocketIO (WebSockets)
- **Database:** PostgreSQL
- **Frontend:** HTML/CSS/JS (no framework, single page)
- **Deployment:** Docker → AWS EC2 or Railway

## Project Structure

```
kanban-sync/
├── app.py               # Flask backend (REST API + WebSocket)
├── requirements.txt     # Python dependencies
├── Dockerfile           # Docker build config
├── docker-compose.yml   # Runs app + PostgreSQL together (for AWS EC2)
├── setup-aws.sh         # One-command AWS EC2 setup script
├── .env.example         # Environment variable template
├── railway.toml         # Railway deployment config
├── .gitignore
├── templates/
│   └── index.html       # Frontend (single-page app)
└── README.md            # This file
```

---

## Deploy on AWS EC2 (Recommended for full control)

### What you need
- An AWS account (free tier works)
- 10 minutes

### Step 1: Launch an EC2 instance

1. Go to **AWS Console** → **EC2** → **Launch Instance**
2. Name it: `kanban-sync`
3. Choose **Ubuntu Server 22.04 LTS** (or 24.04)
4. Instance type: **t3.small** (2GB RAM, recommended) or **t2.micro** (1GB, free tier — may be slow)
5. Key pair: Create one or use an existing one (you'll need the `.pem` file to connect)
6. Network settings: Click **Edit** → make sure **Allow HTTP traffic from internet** is checked (this opens port 80)
7. Click **Launch Instance**

### Step 2: Connect to your instance

Open your terminal and SSH in:

```bash
ssh -i /path/to/your-key.pem ubuntu@YOUR-EC2-PUBLIC-IP
```

Find your EC2 public IP in the AWS Console → EC2 → Instances → your instance → **Public IPv4 address**

### Step 3: Clone the repo and run the setup script

```bash
git clone https://github.com/YOUR_USERNAME/kanban-sync.git
cd kanban-sync
chmod +x setup-aws.sh
./setup-aws.sh
```

The script automatically:
- Installs Docker and Docker Compose
- Sets up the database
- Builds and starts both containers (app + PostgreSQL)
- Prints your live URL

### Step 4: Open your browser

Go to `http://YOUR-EC2-PUBLIC-IP` — your Kanban board is live!

### Step 5: Change the database password (important!)

```bash
cd kanban-sync
nano .env
# Change DB_PASSWORD to something secure
# Save (Ctrl+O, Enter, Ctrl+X)
sudo docker compose down
sudo docker compose up -d
```

### Useful commands on EC2

```bash
# View live logs
sudo docker compose logs -f

# Restart the app
sudo docker compose restart

# Stop everything
sudo docker compose down

# Start everything
sudo docker compose up -d

# Check container status
sudo docker compose ps
```

---

## Deploy on Railway (Alternative — simpler)

### Step-by-step

1. **Push to GitHub:**
   ```bash
   git init
   git add .
   git commit -m "Initial commit: Kanban Sync"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/kanban-sync.git
   git push -u origin main
   ```

2. Go to [railway.app](https://railway.app) → **Login with GitHub**

3. **New Project** → **Deploy from GitHub repo** → select your `kanban-sync` repo

4. Add **PostgreSQL**: click **+ New** → **Database** → **PostgreSQL**

5. Go to your app service → **Variables** → add:
   - `DATABASE_URL` → copy the PostgreSQL connection URL from the database service

6. Railway auto-builds from the Dockerfile → go to **Settings** → **Generate Domain**

7. Open the URL — your Kanban board is live!

---

## Local Development

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Start PostgreSQL (using Docker)
docker run --name kanban-db -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=kanban_sync -p 5432:5432 -d postgres:15

# 3. Set the database URL
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/kanban_sync"

# 4. Run the app
python app.py

# 5. Open http://localhost:5000
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST   | `/api/projects` | Create a new project |
| GET    | `/api/projects` | List all projects |
| GET    | `/api/projects/{id}` | Get project with members & tasks |
| POST   | `/api/projects/{id}/members` | Add member by email |
| DELETE | `/api/projects/{id}/members/{mid}` | Remove member |
| POST   | `/api/projects/{id}/tasks` | Create a task |
| PUT    | `/api/projects/{id}/tasks/{tid}` | Update task (status, title, etc.) |
| DELETE | `/api/projects/{id}/tasks/{tid}` | Delete task |

### WebSocket Events

| Event | Direction | Description |
|-------|-----------|-------------|
| `join` | Client→Server | Join a project room for live updates |
| `task_created` | Server→Client | New task added by anyone |
| `task_updated` | Server→Client | Task moved/edited by anyone |
| `task_deleted` | Server→Client | Task removed by anyone |
| `member_added` | Server→Client | New member invited |
| `member_removed` | Server→Client | Member removed |

## License

MIT — use it, modify it, ship it.
