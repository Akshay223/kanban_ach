import os, uuid, datetime, smtplib, secrets, json
from flask import Flask, request, jsonify, send_from_directory, redirect, make_response
from flask_socketio import SocketIO, join_room, leave_room, emit
from flask_cors import CORS
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import psycopg2
from psycopg2.extras import RealDictCursor
import requests
import jwt

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/kanban_sync")
SMTP_EMAIL = os.environ.get("SMTP_EMAIL", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
APP_URL = os.environ.get("APP_URL", "http://16.16.197.10.nip.io")
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")
JWT_SECRET = os.environ.get("JWT_SECRET", secrets.token_hex(32))
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "akshaytech01@gmail.com")

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["SECRET_KEY"] = JWT_SECRET
CORS(app, supports_credentials=True)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id VARCHAR(36) PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            name TEXT DEFAULT '',
            avatar_url TEXT DEFAULT '',
            provider TEXT DEFAULT 'email',
            role TEXT DEFAULT 'user',
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW(),
            last_login TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS projects (
            id VARCHAR(36) PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            created_by VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS members (
            id VARCHAR(36) PRIMARY KEY,
            project_id VARCHAR(36) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            user_id VARCHAR(36) REFERENCES users(id) ON DELETE CASCADE,
            email TEXT NOT NULL,
            name TEXT DEFAULT '',
            role TEXT DEFAULT 'member',
            joined_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(project_id, email)
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id VARCHAR(36) PRIMARY KEY,
            project_id VARCHAR(36) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'todo',
            priority TEXT NOT NULL DEFAULT 'Medium',
            assignee TEXT DEFAULT '',
            created_by VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS page_views (
            id VARCHAR(36) PRIMARY KEY,
            user_id VARCHAR(36),
            endpoint TEXT DEFAULT '',
            ip_address TEXT DEFAULT '',
            user_agent TEXT DEFAULT '',
            timestamp TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS comments (
            id VARCHAR(36) PRIMARY KEY,
            task_id VARCHAR(36) NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            project_id VARCHAR(36) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            user_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
            user_name TEXT DEFAULT '',
            user_email TEXT DEFAULT '',
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
    # Add created_by column if it doesn't exist (for existing DBs)
    try:
        cur.execute("ALTER TABLE projects ADD COLUMN IF NOT EXISTS created_by VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL;")
        cur.execute("ALTER TABLE members ADD COLUMN IF NOT EXISTS user_id VARCHAR(36) REFERENCES users(id) ON DELETE CASCADE;")
        cur.execute("ALTER TABLE members ADD COLUMN IF NOT EXISTS role TEXT DEFAULT 'member';")
        cur.execute("ALTER TABLE members ADD COLUMN IF NOT EXISTS joined_at TIMESTAMP DEFAULT NOW();")
        cur.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS created_by VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL;")
    except:
        pass
    conn.close()
    print("Database initialized")

def send_invite_email(to_email, project_name, project_id, inviter_name, personal_message):
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        print(f"SMTP not configured. Skipping email to {to_email}")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = f"Kanban Sync <{SMTP_EMAIL}>"
        msg["To"] = to_email
        msg["Subject"] = f'{inviter_name} invited you to join "{project_name}"'
        project_link = f"{APP_URL}/#project/{project_id}"
        if personal_message:
            greeting = f'<p style="color:#e2e8f0;font-size:16px;line-height:1.6;">{personal_message}</p>'
        else:
            greeting = f'<p style="color:#e2e8f0;font-size:16px;">Hi there!</p><p style="color:#e2e8f0;font-size:16px;"><strong>{inviter_name}</strong> has invited you to collaborate on the project <strong style="color:#38bdf8;">{project_name}</strong>.</p>'
        html_body = f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#0f172a;padding:40px;border-radius:12px;">
            <h1 style="color:#38bdf8;text-align:center;">📋 Kanban Sync</h1>
            {greeting}
            <p style="color:#94a3b8;font-size:14px;">You can view tasks, create new ones, and track progress in real-time.</p>
            <div style="text-align:center;margin:30px 0;">
                <a href="{project_link}" style="background:#0ea5e9;color:#fff;padding:14px 32px;border-radius:8px;text-decoration:none;font-size:16px;font-weight:600;display:inline-block;">Open Kanban Board</a>
            </div>
            <p style="color:#64748b;font-size:12px;text-align:center;">Or copy this link: {project_link}</p>
            <hr style="border:none;border-top:1px solid #334155;margin:30px 0;">
            <p style="color:#475569;font-size:12px;text-align:center;">This invite was sent from Kanban Sync by {inviter_name}. If you weren't expecting this, you can ignore this email.</p>
        </div>
        """
        msg.attach(MIMEText(html_body, "html"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.send_message(msg)
        print(f"Invite email sent to {to_email}")
        return True
    except Exception as e:
        print(f"Failed to send email to {to_email}: {e}")
        return False

def send_task_assignment_email(to_email, task_title, project_name, project_id, assigner_name):
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        print(f"SMTP not configured. Skipping task assignment email to {to_email}")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = f"Kanban Sync <{SMTP_EMAIL}>"
        msg["To"] = to_email
        msg["Subject"] = f'{assigner_name} assigned you a task: "{task_title}"'
        project_link = f"{APP_URL}/#project/{project_id}"
        html_body = f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#0f172a;padding:40px;border-radius:12px;">
            <h1 style="color:#38bdf8;text-align:center;">📋 New Task Assigned</h1>
            <p style="color:#e2e8f0;font-size:16px;"><strong>{assigner_name}</strong> assigned you a task in <strong style="color:#38bdf8;">{project_name}</strong>.</p>
            <div style="background:#1e293b;border:1px solid #334155;border-radius:8px;padding:20px;margin:20px 0;">
                <p style="color:#e2e8f0;font-size:18px;font-weight:600;">{task_title}</p>
            </div>
            <div style="text-align:center;margin:30px 0;">
                <a href="{project_link}" style="background:#0ea5e9;color:#fff;padding:14px 32px;border-radius:8px;text-decoration:none;font-size:16px;font-weight:600;display:inline-block;">View Task</a>
            </div>
            <p style="color:#64748b;font-size:12px;text-align:center;">Open the board to see full details and start working.</p>
        </div>
        """
        msg.attach(MIMEText(html_body, "html"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.send_message(msg)
        print(f"Task assignment email sent to {to_email}")
        return True
    except Exception as e:
        print(f"Failed to send task assignment email to {to_email}: {e}")
        return False

def _to_iso(val):
    if val is None: return None
    if isinstance(val, str): return val
    return val.isoformat()

def _ser_user(u):
    return {"id": u["id"], "email": u["email"], "name": u.get("name", ""), "avatar_url": u.get("avatar_url", ""), "role": u.get("role", "user"), "provider": u.get("provider", "email"), "is_active": u.get("is_active", True), "created_at": _to_iso(u.get("created_at")), "last_login": _to_iso(u.get("last_login"))}

def _ser_project(p):
    return {"id": p["id"], "name": p["name"], "description": p.get("description", ""), "created_at": _to_iso(p.get("created_at"))}

def _ser_member(m):
    return {"id": m["id"], "email": m["email"], "name": m.get("name", ""), "role": m.get("role", "member"), "user_id": m.get("user_id")}

def _ser_task(t):
    return {"id": t["id"], "title": t["title"], "description": t.get("description", ""), "status": t["status"], "priority": t.get("priority", "Medium"), "assignee": t.get("assignee", ""), "created_at": _to_iso(t.get("created_at")), "updated_at": _to_iso(t.get("updated_at"))}

# ── AUTH HELPERS ──────────────────────────────────────

def create_jwt(user_id, email, name, role):
    payload = {
        "user_id": user_id, "email": email, "name": name, "role": role,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=24)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def get_user_from_token(request):
    token = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    if not token:
        cookie = request.cookies.get("kanban_token")
        if cookie:
            token = cookie
    if not token:
        return None
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM users WHERE id = %s", (payload["user_id"],))
        user = cur.fetchone()
        conn.close()
        return user
    except:
        return None

def get_or_create_user(email, name, avatar_url, provider):
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cur.fetchone()
    if user:
        cur.execute("UPDATE users SET last_login = NOW(), name = %s WHERE id = %s", (name or user["name"], user["id"]))
        cur.execute("SELECT * FROM users WHERE id = %s", (user["id"],))
        user = cur.fetchone()
    else:
        uid = str(uuid.uuid4())
        role = "admin" if email == ADMIN_EMAIL else "user"
        cur.execute("INSERT INTO users (id, email, name, avatar_url, provider, role, last_login) VALUES (%s, %s, %s, %s, %s, %s, NOW()) RETURNING *", (uid, email, name, avatar_url, provider, role))
        user = cur.fetchone()
    conn.close()
    return user

# ── AUTH ROUTES ───────────────────────────────────────

@app.route("/api/auth/google")
def google_auth():
    redirect_uri = f"{APP_URL}/api/auth/google/callback"
    auth_url = f"https://accounts.google.com/o/oauth2/auth?client_id={GOOGLE_CLIENT_ID}&redirect_uri={redirect_uri}&response_type=code&scope=openid email profile&prompt=consent"
    return redirect(auth_url)

@app.route("/api/auth/google/callback")
def google_callback():
    code = request.args.get("code")
    if not code:
        return redirect(f"{APP_URL}/?error=no_code")
    redirect_uri = f"{APP_URL}/api/auth/google/callback"
    token_resp = requests.post("https://oauth2.googleapis.com/token", data={
        "code": code, "client_id": GOOGLE_CLIENT_ID, "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": redirect_uri, "grant_type": "authorization_code"
    })
    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        return redirect(f"{APP_URL}/?error=auth_failed")
    user_resp = requests.get("https://www.googleapis.com/oauth2/v2/userinfo", headers={"Authorization": f"Bearer {access_token}"})
    user_info = user_resp.json()
    email = user_info.get("email")
    name = user_info.get("name", "")
    avatar_url = user_info.get("picture", "")
    if not email:
        return redirect(f"{APP_URL}/?error=no_email")
    user = get_or_create_user(email, name, avatar_url, "google")
    token = create_jwt(user["id"], user["email"], user["name"], user["role"])
    response = make_response(redirect(f"{APP_URL}/?auth=success"))
    response.set_cookie("kanban_token", token, httponly=True, max_age=86400, samesite="Lax")
    return response

@app.route("/api/auth/github")
def github_auth():
    redirect_uri = f"{APP_URL}/api/auth/github/callback"
    auth_url = f"https://github.com/login/oauth/authorize?client_id={GITHUB_CLIENT_ID}&redirect_uri={redirect_uri}&scope=user:email"
    return redirect(auth_url)

@app.route("/api/auth/github/callback")
def github_callback():
    code = request.args.get("code")
    if not code:
        return redirect(f"{APP_URL}/?error=no_code")
    redirect_uri = f"{APP_URL}/api/auth/github/callback"
    token_resp = requests.post("https://github.com/login/oauth/access_token", data={
        "code": code, "client_id": GITHUB_CLIENT_ID, "client_secret": GITHUB_CLIENT_SECRET,
        "redirect_uri": redirect_uri
    }, headers={"Accept": "application/json"})
    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        return redirect(f"{APP_URL}/?error=auth_failed")
    user_resp = requests.get("https://api.github.com/user", headers={"Authorization": f"token {access_token}"})
    user_info = user_resp.json()
    email_resp = requests.get("https://api.github.com/user/emails", headers={"Authorization": f"token {access_token}"})
    emails = email_resp.json()
    email = None
    for e in emails:
        if e.get("primary"):
            email = e.get("email")
            break
    if not email and emails:
        email = emails[0].get("email")
    if not email:
        email = user_info.get("email")
    if not email:
        return redirect(f"{APP_URL}/?error=no_email")
    name = user_info.get("name") or user_info.get("login", "")
    avatar_url = user_info.get("avatar_url", "")
    user = get_or_create_user(email, name, avatar_url, "github")
    token = create_jwt(user["id"], user["email"], user["name"], user["role"])
    response = make_response(redirect(f"{APP_URL}/?auth=success"))
    response.set_cookie("kanban_token", token, httponly=True, max_age=86400, samesite="Lax")
    return response

@app.route("/api/auth/me")
def auth_me():
    user = get_user_from_token(request)
    if not user:
        return jsonify({"error": "Not authenticated"}), 401
    return jsonify(_ser_user(user))

@app.route("/api/auth/logout", methods=["POST"])
def logout():
    response = jsonify({"ok": True})
    response.delete_cookie("kanban_token")
    return response

# ── PROJECT ROUTES ────────────────────────────────────

@app.route("/api/projects", methods=["POST"])
def create_project():
    user = get_user_from_token(request)
    if not user:
        return jsonify({"error": "Authentication required"}), 401
    data = request.json or {}
    name = (data.get("name") or "").strip()
    if not name: return jsonify({"error": "Project name required"}), 400
    pid = str(uuid.uuid4())
    conn = get_db(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("INSERT INTO projects (id, name, description, created_by) VALUES (%s, %s, %s, %s) RETURNING *", (pid, name, (data.get("description") or "").strip(), user["id"]))
    project = cur.fetchone()
    mid = str(uuid.uuid4())
    cur.execute("INSERT INTO members (id, project_id, user_id, email, name, role) VALUES (%s, %s, %s, %s, %s, %s)", (mid, pid, user["id"], user["email"], user["name"], "owner"))
    conn.close()
    return jsonify(_ser_project(project)), 201

@app.route("/api/projects", methods=["GET"])
def list_projects():
    user = get_user_from_token(request)
    if not user:
        return jsonify({"error": "Authentication required"}), 401
    conn = get_db(); cur = conn.cursor(cursor_factory=RealDictCursor)
    if user["role"] == "admin":
        cur.execute("SELECT * FROM projects ORDER BY created_at DESC")
    else:
        cur.execute("SELECT p.* FROM projects p JOIN members m ON p.id = m.project_id WHERE m.user_id = %s ORDER BY p.created_at DESC", (user["id"],))
    projects = cur.fetchall(); conn.close()
    return jsonify([_ser_project(p) for p in projects])

@app.route("/api/projects/<project_id>", methods=["GET"])
def get_project(project_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"error": "Authentication required"}), 401
    conn = get_db(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM projects WHERE id = %s", (project_id,))
    project = cur.fetchone()
    if not project: conn.close(); return jsonify({"error": "Project not found"}), 404
    cur.execute("SELECT * FROM members WHERE project_id = %s ORDER BY joined_at", (project_id,))
    members = cur.fetchall()
    cur.execute("SELECT * FROM tasks WHERE project_id = %s ORDER BY created_at", (project_id,))
    tasks = cur.fetchall(); conn.close()
    return jsonify({**_ser_project(project), "members": [_ser_member(m) for m in members], "tasks": [_ser_task(t) for t in tasks]})

@app.route("/api/projects/<project_id>", methods=["PUT"])
def rename_project(project_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"error": "Authentication required"}), 401
    data = request.json or {}
    name = (data.get("name") or "").strip()
    if not name: return jsonify({"error": "Name required"}), 400
    desc = (data.get("description") or "").strip()
    conn = get_db(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("UPDATE projects SET name = %s, description = %s WHERE id = %s RETURNING *", (name, desc, project_id))
    project = cur.fetchone(); conn.close()
    if not project: return jsonify({"error": "Project not found"}), 404
    socketio.emit("project_renamed", _ser_project(project), room=project_id)
    return jsonify(_ser_project(project))

@app.route("/api/projects/<project_id>", methods=["DELETE"])
def delete_project(project_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"error": "Authentication required"}), 401
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM projects WHERE id = %s", (project_id,))
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/projects/<project_id>/members", methods=["POST"])
def add_member(project_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"error": "Authentication required"}), 401
    if user["role"] != "admin":
        return jsonify({"error": "Only admins can invite members"}), 403
    data = request.json or {}
    email = (data.get("email") or "").strip().lower()
    name = (data.get("name") or "").strip()
    inviter_name = (data.get("inviter_name") or "Someone").strip()
    personal_message = (data.get("message") or "").strip()
    if not email: return jsonify({"error": "Email required"}), 400
    conn = get_db(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM projects WHERE id = %s", (project_id,))
    project = cur.fetchone()
    if not project: conn.close(); return jsonify({"error": "Project not found"}), 404
    # Check if user exists by email
    cur.execute("SELECT * FROM users WHERE email = %s", (email,))
    existing_user = cur.fetchone()
    user_id = existing_user["id"] if existing_user else None
    try:
        mid = str(uuid.uuid4())
        cur.execute("INSERT INTO members (id, project_id, user_id, email, name) VALUES (%s, %s, %s, %s, %s) RETURNING *", (mid, project_id, user_id, email, name))
        member = cur.fetchone()
        conn.close()
        socketio.emit("member_added", _ser_member(member), room=project_id)
        send_invite_email(email, project["name"], project_id, inviter_name, personal_message)
        return jsonify({**_ser_member(member), "email_sent": True}), 201
    except psycopg2.IntegrityError:
        conn.close(); return jsonify({"error": "Member already in project"}), 409

@app.route("/api/projects/<project_id>/members/<member_id>", methods=["DELETE"])
def remove_member(project_id, member_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"error": "Authentication required"}), 401
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM members WHERE id = %s AND project_id = %s", (member_id, project_id))
    conn.close()
    socketio.emit("member_removed", {"member_id": member_id}, room=project_id)
    return jsonify({"ok": True})

@app.route("/api/projects/<project_id>/tasks", methods=["POST"])
def create_task(project_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"error": "Authentication required"}), 401
    if user["role"] != "admin":
        return jsonify({"error": "Only admins can create tasks"}), 403
    data = request.json or {}
    title = (data.get("title") or "").strip()
    if not title: return jsonify({"error": "Title required"}), 400
    tid = str(uuid.uuid4())
    conn = get_db(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("INSERT INTO tasks (id, project_id, title, description, status, priority, assignee, created_by) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
        (tid, project_id, title, (data.get("description") or "").strip(), data.get("status","todo"), data.get("priority","Medium"), (data.get("assignee") or "").strip(), user["id"]))
    task = cur.fetchone(); conn.close()
    socketio.emit("task_created", _ser_task(task), room=project_id)
    # Send assignment email if task is assigned to someone
    assignee = (data.get("assignee") or "").strip()
    if assignee:
        conn2 = get_db(); cur2 = conn2.cursor(cursor_factory=RealDictCursor)
        cur2.execute("SELECT * FROM projects WHERE id = %s", (project_id,))
        proj = cur2.fetchone(); conn2.close()
        if proj:
            send_task_assignment_email(assignee, title, proj["name"], project_id, user["name"] or user["email"])
    return jsonify(_ser_task(task)), 201

@app.route("/api/projects/<project_id>/tasks/<task_id>", methods=["PUT"])
def update_task(project_id, task_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"error": "Authentication required"}), 401
    data = request.json or {}
    allowed = {"title","description","status","priority","assignee"}
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates: return jsonify({"error": "No valid fields"}), 400
    set_clauses = []; values = []
    for k, v in updates.items():
        set_clauses.append(f"{k} = %s"); values.append(v)
    set_clauses.append("updated_at = NOW()")
    values.extend([task_id, project_id])
    conn = get_db(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(f"UPDATE tasks SET {', '.join(set_clauses)} WHERE id = %s AND project_id = %s RETURNING *", values)
    task = cur.fetchone(); conn.close()
    if not task: return jsonify({"error": "Task not found"}), 404
    socketio.emit("task_updated", _ser_task(task), room=project_id)
    # Send assignment email if assignee changed
    if "assignee" in updates and updates["assignee"]:
        conn2 = get_db(); cur2 = conn2.cursor(cursor_factory=RealDictCursor)
        cur2.execute("SELECT * FROM projects WHERE id = %s", (project_id,))
        proj = cur2.fetchone(); conn2.close()
        if proj:
            send_task_assignment_email(updates["assignee"], task["title"], proj["name"], project_id, user["name"] or user["email"])
    return jsonify(_ser_task(task))

@app.route("/api/projects/<project_id>/tasks/<task_id>", methods=["DELETE"])
def delete_task(project_id, task_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"error": "Authentication required"}), 401
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM tasks WHERE id = %s AND project_id = %s", (task_id, project_id))
    conn.close()
    socketio.emit("task_deleted", {"task_id": task_id}, room=project_id)
    return jsonify({"ok": True})

# ── COMMENT ROUTES ─────────────────────────────────────

@app.route("/api/projects/<project_id>/tasks/<task_id>/comments", methods=["GET"])
def get_comments(project_id, task_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"error": "Authentication required"}), 401
    conn = get_db(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM comments WHERE task_id = %s AND project_id = %s ORDER BY created_at", (task_id, project_id))
    comments = cur.fetchall(); conn.close()
    return jsonify([{"id": c["id"], "task_id": c["task_id"], "user_id": c.get("user_id"), "user_name": c.get("user_name", ""), "user_email": c.get("user_email", ""), "content": c["content"], "created_at": _to_iso(c.get("created_at"))} for c in comments])

@app.route("/api/projects/<project_id>/tasks/<task_id>/comments", methods=["POST"])
def add_comment(project_id, task_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"error": "Authentication required"}), 401
    data = request.json or {}
    content = (data.get("content") or "").strip()
    if not content: return jsonify({"error": "Comment required"}), 400
    cid = str(uuid.uuid4())
    conn = get_db(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("INSERT INTO comments (id, task_id, project_id, user_id, user_name, user_email, content) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING *",
        (cid, task_id, project_id, user["id"], user["name"] or user["email"], user["email"], content))
    comment = cur.fetchone(); conn.close()
    result = {"id": comment["id"], "task_id": comment["task_id"], "user_id": comment.get("user_id"), "user_name": comment.get("user_name", ""), "user_email": comment.get("user_email", ""), "content": comment["content"], "created_at": _to_iso(comment.get("created_at"))}
    socketio.emit("comment_added", result, room=project_id)
    return jsonify(result), 201

# ── ADMIN ROUTES ──────────────────────────────────────

@app.route("/api/admin/stats")
def admin_stats():
    user = get_user_from_token(request)
    if not user or user["role"] != "admin":
        return jsonify({"error": "Admin access required"}), 403
    conn = get_db(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT COUNT(*) as total FROM users"); users_total = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) as total FROM users WHERE last_login > NOW() - INTERVAL '24 hours'"); daily_active = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) as total FROM projects"); projects_total = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) as total FROM tasks"); tasks_total = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) as total FROM tasks WHERE status = 'done'"); tasks_done = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) as total FROM tasks WHERE status = 'done' AND updated_at > NOW() - INTERVAL '7 days'"); weekly_done = cur.fetchone()["total"]
    completion_rate = round((tasks_done / tasks_total * 100) if tasks_total > 0 else 0, 1)
    conn.close()
    return jsonify({"users": {"total": users_total, "daily_active": daily_active}, "projects": {"total": projects_total}, "tasks": {"total": tasks_total, "completion_rate": completion_rate, "weekly_completed": weekly_done}})

@app.route("/api/admin/users")
def admin_users():
    user = get_user_from_token(request)
    if not user or user["role"] != "admin":
        return jsonify({"error": "Admin access required"}), 403
    conn = get_db(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM users ORDER BY created_at DESC")
    users = cur.fetchall(); conn.close()
    return jsonify([_ser_user(u) for u in users])

@app.route("/api/admin/users/<email>/role", methods=["PUT"])
def admin_update_role(email):
    user = get_user_from_token(request)
    if not user or user["role"] != "admin":
        return jsonify({"error": "Admin access required"}), 403
    data = request.json or {}
    role = data.get("role", "user")
    conn = get_db(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("UPDATE users SET role = %s WHERE email = %s RETURNING *", (role, email))
    u = cur.fetchone(); conn.close()
    if not u: return jsonify({"error": "User not found"}), 404
    return jsonify(_ser_user(u))

@app.route("/api/admin/users/<email>/status", methods=["PUT"])
def admin_update_status(email):
    user = get_user_from_token(request)
    if not user or user["role"] != "admin":
        return jsonify({"error": "Admin access required"}), 403
    data = request.json or {}
    is_active = data.get("is_active", True)
    conn = get_db(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("UPDATE users SET is_active = %s WHERE email = %s RETURNING *", (is_active, email))
    u = cur.fetchone(); conn.close()
    if not u: return jsonify({"error": "User not found"}), 404
    return jsonify(_ser_user(u))

# ── PROFILE ROUTE ─────────────────────────────────────

@app.route("/api/profile")
def get_profile():
    user = get_user_from_token(request)
    if not user:
        return jsonify({"error": "Authentication required"}), 401
    conn = get_db(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT COUNT(*) as total FROM members WHERE user_id = %s", (user["id"],))
    projects_count = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) as total FROM tasks WHERE assignee = %s", (user["email"],))
    assigned_tasks = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) as total FROM tasks WHERE created_by = %s", (user["id"],))
    created_tasks = cur.fetchone()["total"]
    conn.close()
    return jsonify({**_ser_user(user), "projects_count": projects_count, "assigned_tasks": assigned_tasks, "created_tasks": created_tasks})

# ── TRAFFIC TRACKING ──────────────────────────────────

@app.before_request
def track_traffic():
    if request.path.startswith("/api/"):
        try:
            conn = get_db()
            cur = conn.cursor()
            user = get_user_from_token(request)
            cur.execute("INSERT INTO page_views (id, user_id, endpoint, ip_address, user_agent) VALUES (%s, %s, %s, %s, %s)",
                (str(uuid.uuid4()), user["id"] if user else None, request.path, request.remote_addr or "", request.headers.get("user-agent", "")[:500]))
            conn.close()
        except:
            pass

# ── SOCKETIO ──────────────────────────────────────────

@socketio.on("join")
def on_join(data):
    pid = data.get("project_id")
    if pid: join_room(pid); emit("joined", {"project_id": pid})

@socketio.on("leave")
def on_leave(data):
    pid = data.get("project_id")
    if pid: leave_room(pid)

# ── SERVE FRONTEND ────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("templates", "index.html")

@app.route("/<path:path>")
def static_files(path):
    return send_from_directory("templates", path)

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port, debug=True)
