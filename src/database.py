"""
src/database.py — SQLite persistence for workspaces, artifacts, and logs.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from uuid import uuid4

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DB_DIR, "april.db")


def get_db_connection() -> sqlite3.Connection:
    """Establish a connection to the SQLite database."""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db() -> None:
    """Initialize the database tables and seed default data if empty."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Create Workspaces Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS workspaces (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
    """)

    # Create Artifacts Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS artifacts (
            id TEXT PRIMARY KEY,
            workspace_id TEXT,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE SET NULL
        );
    """)

    # Create Logs Table (for Agent Activities / Research logs)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            artifact_id TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (artifact_id) REFERENCES artifacts(id) ON DELETE CASCADE
        );
    """)

    conn.commit()

    # Seed default workspaces if none exist
    cursor.execute("SELECT COUNT(*) FROM workspaces;")
    if cursor.fetchone()[0] == 0:
        default_workspaces = [
            ("lens", "Lens", datetime.now().isoformat()),
            ("april", "APRIL", datetime.now().isoformat()),
            ("homelab", "Homelab", datetime.now().isoformat()),
            ("one_fifth", "One Fifth", datetime.now().isoformat()),
            ("personal", "Personal", datetime.now().isoformat()),
        ]
        cursor.executemany(
            "INSERT INTO workspaces (id, name, created_at) VALUES (?, ?, ?);",
            default_workspaces,
        )
        conn.commit()

    # Seed default artifacts if none exist
    cursor.execute("SELECT COUNT(*) FROM artifacts;")
    if cursor.fetchone()[0] == 0:
        now_str = datetime.now().isoformat()
        
        # 1. Lens Research Artifact
        art_lens_id = "art_lens_001"
        cursor.execute("""
            INSERT INTO artifacts (id, workspace_id, type, title, content, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            art_lens_id, "lens", "Research",
            "PyQt6 Animation Libraries Research",
            "### Summary of PyQt6 Animation Libraries\n\n"
            "1. **QPropertyAnimation**:\n"
            "   - Easiest for changing opacity, geometry, and coordinates.\n"
            "   - Fits natively with standard Qt styling.\n\n"
            "2. **QGraphicsItemAnimation**:\n"
            "   - Ideal for canvas-based elements and complex vector canvas movements.\n\n"
            "3. **Paint Event Loops (Custom)**:\n"
            "   - High performance, best for fluid micro-animations (e.g. soundwaves, ripples).",
            "Completed", now_str, now_str
        ))

        # 2. APRIL Task Artifact
        cursor.execute("""
            INSERT INTO artifacts (id, workspace_id, type, title, content, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            "art_april_001", "april", "Task",
            "Write Unit Tests for Bridge Layer",
            "- [ ] Mock the PyQt6 signal callbacks.\n"
            "- [ ] Test thread safety using QueuedConnections.\n"
            "- [ ] Run pytest validation checking for trace emissions.",
            "Pending", now_str, now_str
        ))

        # 3. Homelab Agent Activity (Running)
        art_hl_id = "art_hl_001"
        cursor.execute("""
            INSERT INTO artifacts (id, workspace_id, type, title, content, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            art_hl_id, "homelab", "Agent Activity",
            "Homelab Cluster Health Check",
            "### Health Check Status\n\n"
            "- **Inference (mac)**: Online\n"
            "- **Apps Stack (dell)**: Online\n"
            "- **Gateway (cortex)**: Offline (needs attention)\n\n"
            "Diagnostics run started automatically by background cron.",
            "Running", now_str, now_str
        ))

        # Seed logs for the Homelab Agent Activity
        hl_logs = [
            (art_hl_id, "Connecting to gateway at 192.168.0.234...", now_str),
            (art_hl_id, "Node 'mac (inference)' responded in 1.2ms.", now_str),
            (art_hl_id, "Node 'dell (apps)' responded in 3.4ms.", now_str),
            (art_hl_id, "Gateway 'cortex' ping timed out after 5000ms. Flagged degraded.", now_str),
        ]
        cursor.executemany(
            "INSERT INTO logs (artifact_id, message, created_at) VALUES (?, ?, ?);",
            hl_logs,
        )

        # 4. Personal Reminder
        cursor.execute("""
            INSERT INTO artifacts (id, workspace_id, type, title, content, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            "art_pers_001", "personal", "Reminder",
            "Buy Protein Powder",
            "Buy high-quality grass-fed whey isolate from local store.\n"
            "Trigger condition: Tomorrow at 9:00 AM.",
            "Pending", now_str, now_str
        ))

        # 5. Recent Capture (Transient Intake)
        cursor.execute("""
            INSERT INTO artifacts (id, workspace_id, type, title, content, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            "art_rec_001", None, "Note",
            "Quick Idea for Prompt Testing",
            "We should write automated prompt regression tests directly running against the local Ollama LLM to compare output syntaxes between models.",
            "Completed", now_str, now_str
        ))

        conn.commit()

    conn.close()


def add_artifact(
    workspace_id: str | None,
    art_type: str,
    title: str,
    content: str,
    status: str = "Completed",
) -> str:
    """Create a new artifact inside the database."""
    conn = get_db_connection()
    art_id = f"art_{uuid4().hex[:8]}"
    now_str = datetime.now().isoformat()
    conn.execute(
        """
        INSERT INTO artifacts (id, workspace_id, type, title, content, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (art_id, workspace_id, art_type, title, content, status, now_str, now_str),
    )
    conn.commit()
    conn.close()
    return art_id


def get_artifacts(workspace_id: str | None = None) -> list[dict]:
    """Retrieve artifacts, optionally filtered by workspace_id."""
    conn = get_db_connection()
    cursor = conn.cursor()
    if workspace_id == "recent":
        # 'recent' refers to transient/unfiled dictations (workspace_id IS NULL AND type = 'Note')
        cursor.execute(
            "SELECT * FROM artifacts WHERE workspace_id IS NULL AND type = 'Note' ORDER BY created_at DESC;"
        )
    elif workspace_id is not None:
        cursor.execute(
            "SELECT * FROM artifacts WHERE workspace_id = ? ORDER BY created_at DESC;",
            (workspace_id,),
        )
    else:
        cursor.execute("SELECT * FROM artifacts ORDER BY created_at DESC;")
    
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_artifact(artifact_id: str) -> dict | None:
    """Retrieve details for a single artifact."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM artifacts WHERE id = ?;", (artifact_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def update_artifact(
    artifact_id: str,
    workspace_id: str | None = None,
    art_type: str | None = None,
    title: str | None = None,
    content: str | None = None,
    status: str | None = None,
) -> None:
    """Update fields on an existing artifact."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    fields = []
    params = []
    
    if workspace_id is not None:
        # Note: we use "None" string or python None to set it to NULL
        if workspace_id == "recent":
            fields.append("workspace_id = NULL")
        else:
            fields.append("workspace_id = ?")
            params.append(workspace_id)
            
    if art_type is not None:
        fields.append("type = ?")
        params.append(art_type)
    if title is not None:
        fields.append("title = ?")
        params.append(title)
    if content is not None:
        fields.append("content = ?")
        params.append(content)
    if status is not None:
        fields.append("status = ?")
        params.append(status)
        
    if fields:
        fields.append("updated_at = ?")
        params.append(datetime.now().isoformat())
        params.append(artifact_id)
        
        query = f"UPDATE artifacts SET {', '.join(fields)} WHERE id = ?;"
        cursor.execute(query, params)
        conn.commit()
    conn.close()


def delete_artifact(artifact_id: str) -> None:
    """Delete an artifact by ID."""
    conn = get_db_connection()
    conn.execute("DELETE FROM artifacts WHERE id = ?;", (artifact_id,))
    conn.commit()
    conn.close()


def get_logs(artifact_id: str) -> list[str]:
    """Get logs associated with an agent activity or research task."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT message FROM logs WHERE artifact_id = ? ORDER BY created_at ASC;",
        (artifact_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [r["message"] for r in rows]


def add_log(artifact_id: str, message: str) -> None:
    """Append a log message to an artifact's run log."""
    conn = get_db_connection()
    now_str = datetime.now().isoformat()
    conn.execute(
        "INSERT INTO logs (artifact_id, message, created_at) VALUES (?, ?, ?);",
        (artifact_id, message, now_str),
    )
    conn.commit()
    conn.close()


def get_workspaces() -> list[dict]:
    """Retrieve all available workspaces."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM workspaces ORDER BY name ASC;")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]
