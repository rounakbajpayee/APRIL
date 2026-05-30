"""
src/control_panel.py — Localhost Web Server (Control Panel & Operator App).

Provides a premium dark-mode web interface to:
1. View overall system status, cluster node diagnostics, and alerts.
2. Promote/file incoming speech dictations from the Recent intake queue.
3. Manage workspaces, edit markdown artifacts, and monitor agent logs in real-time.
4. Introspect developer console activities and live telemetry metrics.
5. Calibrate desktop anchor widget themes, accents, and presets.
"""

from __future__ import annotations

import json
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.parse
from datetime import datetime

import database
from ui import theme

# Expose a global bridge reference inside the module to invoke signals
_bridge_ref = None


class ControlPanelHandler(BaseHTTPRequestHandler):
    """HTTP API and static page server for the APRIL Web Operator App."""

    def log_message(self, format_str, *args):
        # Suppress request logging to prevent console pollution
        pass

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        if path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_DASHBOARD.encode("utf-8"))
            
        elif path == "/api/workspaces":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            workspaces = database.get_workspaces()
            self.wfile.write(json.dumps(workspaces).encode("utf-8"))
            
        elif path == "/api/artifacts":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            w_id = params.get("workspace_id", [None])[0]
            artifacts = database.get_artifacts(w_id)
            self.wfile.write(json.dumps(artifacts).encode("utf-8"))
            
        elif path == "/api/artifact":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            art_id = params.get("id", [None])[0]
            artifact = database.get_artifact(art_id) if art_id else None
            self.wfile.write(json.dumps(artifact).encode("utf-8"))

        elif path == "/api/logs":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            art_id = params.get("artifact_id", [None])[0]
            logs = database.get_logs(art_id) if art_id else []
            self.wfile.write(json.dumps(logs).encode("utf-8"))

        elif path == "/api/settings":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            data = {
                "accent_registry_sync": theme.ACCENT_REGISTRY_SYNC,
                "accent_preset": theme.ACCENT_PRESET,
                "accent_custom_hex": theme.ACCENT_CUSTOM_HEX,
                "active_accent_hex": theme.WINDOWS_ACCENT.name(),
                "mica_opacity": theme.MICA_OPACITY,
                "mica_blur_radius": theme.MICA_BLUR_RADIUS,
            }
            self.wfile.write(json.dumps(data).encode("utf-8"))

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)
        payload = {}
        if post_data:
            try:
                payload = json.loads(post_data.decode("utf-8"))
            except Exception:
                pass

        if path == "/api/dictate":
            # Simulate STT Dictation Finished
            text = payload.get("text", "").strip()
            if text and _bridge_ref is not None:
                # Dispatch transcript event to the bridge (runs thread-safe in PyQt6)
                _bridge_ref.set_transcript(text)
                self._send_json({"ok": True, "message": "Dictation dispatched to Quick Peek card."})
            else:
                self._send_json({"ok": False, "message": "Missing dictation payload."})

        elif path == "/api/artifact/create":
            w_id = payload.get("workspace_id")
            if w_id == "recent" or w_id == "":
                w_id = None
            art_type = payload.get("type", "Note")
            title = payload.get("title", "Untitled")
            content = payload.get("content", "")
            status = payload.get("status", "Completed")

            art_id = database.add_artifact(
                workspace_id=w_id,
                art_type=art_type,
                title=title,
                content=content,
                status=status,
            )
            self._send_json({"ok": True, "artifact_id": art_id})

        elif path == "/api/artifact/update":
            art_id = payload.get("id")
            w_id = payload.get("workspace_id")
            if w_id == "recent" or w_id == "":
                w_id = "recent"  # Database.py handles "recent" string to clear workspace_id to NULL
            art_type = payload.get("type")
            title = payload.get("title")
            content = payload.get("content")
            status = payload.get("status")

            if art_id:
                database.update_artifact(
                    artifact_id=art_id,
                    workspace_id=w_id,
                    art_type=art_type,
                    title=title,
                    content=content,
                    status=status,
                )
                self._send_json({"ok": True})
            else:
                self._send_json({"ok": False, "message": "Missing artifact id."})

        elif path == "/api/artifact/delete":
            art_id = payload.get("id")
            if art_id:
                database.delete_artifact(art_id)
                self._send_json({"ok": True})
            else:
                self._send_json({"ok": False, "message": "Missing artifact id."})

        elif path == "/api/logs":
            # Append log message to running agent activity
            art_id = payload.get("artifact_id")
            msg = payload.get("message", "").strip()
            if art_id and msg:
                database.add_log(art_id, msg)
                self._send_json({"ok": True})
            else:
                self._send_json({"ok": False, "message": "Missing artifact_id or log message."})

        elif path == "/api/settings":
            # Modify active configuration Settings (partial updates supported)
            preset = payload.get("preset", theme.ACCENT_PRESET)
            sync_dwm = payload.get("sync_dwm", theme.ACCENT_REGISTRY_SYNC)
            custom_hex = payload.get("custom_hex", theme.ACCENT_CUSTOM_HEX)
            opacity = payload.get("opacity", theme.MICA_OPACITY)
            blur = payload.get("blur", theme.MICA_BLUR_RADIUS)

            theme.ACCENT_REGISTRY_SYNC = sync_dwm
            theme.ACCENT_CUSTOM_HEX = custom_hex
            theme.MICA_OPACITY = opacity
            theme.MICA_BLUR_RADIUS = blur
            
            if preset and preset in theme.PRESETS:
                theme.ACCENT_PRESET = preset
                
            theme.save_theme_config()
            theme.refresh_theme()

            # Refresh running widget views
            if _bridge_ref is not None:
                if _bridge_ref._overlay is not None:
                    _bridge_ref._overlay._reposition()
                # Send refresh signal to repaint the anchor dot
                if hasattr(_bridge_ref, "_core"):
                    _bridge_ref._core.state_changed.emit(_bridge_ref._core.state)

            self._send_json({"ok": True, "message": "Config saved and widgets updated."})

        else:
            self.send_response(404)
            self.end_headers()

    def _send_json(self, data: dict) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))


def start_control_panel(bridge_ref) -> None:
    """Launch the HTTPServer on a background thread."""
    global _bridge_ref
    _bridge_ref = bridge_ref

    server_address = ("", 8080)
    try:
        httpd = HTTPServer(server_address, ControlPanelHandler)
        print("[Simulator] Web Control Panel active at http://localhost:8080")
        httpd.serve_forever()
    except Exception as exc:
        print(f"[Simulator] Failed to bind to port 8080: {exc}")


# ── Operator Dashboard HTML (Tailwind CSS Dark Mode Glassmorphism) ───────────

HTML_DASHBOARD = """
<!DOCTYPE html>
<html lang="en" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>APRIL Operator Console</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
        body { 
            font-family: 'Outfit', sans-serif; 
            background: linear-gradient(135deg, #09090b 0%, #030712 100%); 
        }
        .code-font {
            font-family: 'JetBrains Mono', monospace;
        }
        .glass-panel {
            background: rgba(17, 24, 39, 0.6);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.08);
        }
        .scrollbar-custom::-webkit-scrollbar {
            width: 6px;
            height: 6px;
        }
        .scrollbar-custom::-webkit-scrollbar-track {
            background: rgba(0, 0, 0, 0.1);
        }
        .scrollbar-custom::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.15);
            border-radius: 3px;
        }
        .scrollbar-custom::-webkit-scrollbar-thumb:hover {
            background: rgba(255, 255, 255, 0.3);
        }
    </style>
</head>
<body class="text-zinc-100 min-h-screen flex flex-col antialiased overflow-hidden">
    
    <!-- Top Global Header -->
    <header class="flex items-center justify-between border-b border-white/5 py-3 px-6 bg-zinc-950/80 backdrop-blur z-20">
        <div class="flex items-center gap-3">
            <div id="status_indicator_dot" class="w-2.5 h-2.5 rounded-full bg-amber-500 animate-pulse"></div>
            <div>
                <span class="text-base font-bold tracking-wider text-amber-500">APRIL OS</span>
                <span class="text-xs text-zinc-400 font-medium ml-2 border-l border-zinc-700 pl-2 uppercase tracking-widest">Operator Console</span>
            </div>
        </div>
        <div class="flex items-center gap-6 text-xs text-zinc-400 font-medium">
            <div class="flex items-center gap-2">
                <span class="text-zinc-500">Intake Queue:</span>
                <span id="global_intake_count" class="bg-zinc-800 text-zinc-200 px-2 py-0.5 rounded-full font-mono text-[10px]">0</span>
            </div>
            <div class="flex items-center gap-2">
                <span class="text-zinc-500">State:</span>
                <span id="global_state" class="text-amber-500 font-mono uppercase tracking-wider">Dormant</span>
            </div>
        </div>
    </header>

    <!-- Main Content Panel -->
    <div class="flex-1 flex overflow-hidden">
        
        <!-- Sidebar Menu Navigation -->
        <nav class="w-64 border-r border-white/5 bg-zinc-950/40 p-4 flex flex-col gap-1.5 z-10">
            <button onclick="switchTab('overview')" id="nav-overview" class="w-full flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-semibold transition-all duration-150 bg-white/5 text-white">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v4a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v4a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v4a2 2 0 01-2 2H6a2 2 0 01-2-2v-4zM14 16a2 2 0 012-2h2a2 2 0 012 2v4a2 2 0 01-2 2h-2a2 2 0 01-2-2v-4z"></path></svg>
                Overview
            </button>
            <button onclick="switchTab('dictations')" id="nav-dictations" class="w-full flex items-center justify-between px-4 py-3 rounded-lg text-sm font-semibold transition-all duration-150 text-zinc-400 hover:bg-white/5 hover:text-white">
                <div class="flex items-center gap-3">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"></path></svg>
                    Dictations
                </div>
                <span id="badge_dictations_count" class="bg-zinc-800 text-zinc-300 font-mono text-[10px] px-1.5 py-0.5 rounded-full hidden">0</span>
            </button>
            <button onclick="switchTab('workspaces')" id="nav-workspaces" class="w-full flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-semibold transition-all duration-150 text-zinc-400 hover:bg-white/5 hover:text-white">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"></path></svg>
                Workspaces
            </button>
            <button onclick="switchTab('developer')" id="nav-developer" class="w-full flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-semibold transition-all duration-150 text-zinc-400 hover:bg-white/5 hover:text-white">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"></path></svg>
                Developer
            </button>
            <button onclick="switchTab('settings')" id="nav-settings" class="w-full flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-semibold transition-all duration-150 text-zinc-400 hover:bg-white/5 hover:text-white">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>
                Settings
            </button>
            <div class="mt-auto pt-4 border-t border-white/5 flex flex-col gap-1 text-[11px] text-zinc-500">
                <div>Client IP: 127.0.0.1</div>
                <div>SQLite Database: Active</div>
            </div>
        </nav>

        <!-- Dynamic Main Panel container -->
        <main class="flex-1 flex overflow-hidden bg-zinc-950/20">
            
            <!-- ── TAB: OVERVIEW ── -->
            <section id="tab-overview" class="flex-1 overflow-y-auto p-6 scrollbar-custom space-y-6">
                
                <!-- Welcome Alert -->
                <div class="glass-panel p-6 rounded-2xl relative overflow-hidden flex items-center justify-between">
                    <div class="relative z-10 space-y-1.5">
                        <h2 class="text-xl font-bold tracking-wide">Welcome, Operator</h2>
                        <p class="text-sm text-zinc-400">All desktop bridges are connected. Ambient status dot listening in the taskbar corner.</p>
                    </div>
                    <div class="w-16 h-16 rounded-full bg-amber-500/10 flex items-center justify-center text-amber-500">
                        <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"></path></svg>
                    </div>
                </div>

                <!-- Global stats grids -->
                <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
                    <div class="glass-panel p-5 rounded-xl space-y-2">
                        <div class="text-xs text-zinc-400 uppercase tracking-widest font-semibold">Active Workspaces</div>
                        <div id="stat_ws_count" class="text-3xl font-extrabold tracking-tight">0</div>
                    </div>
                    <div class="glass-panel p-5 rounded-xl space-y-2">
                        <div class="text-xs text-zinc-400 uppercase tracking-widest font-semibold">Total Artifacts</div>
                        <div id="stat_art_count" class="text-3xl font-extrabold tracking-tight">0</div>
                    </div>
                    <div class="glass-panel p-5 rounded-xl space-y-2">
                        <div class="text-xs text-zinc-400 uppercase tracking-widest font-semibold">Running Agent Jobs</div>
                        <div id="stat_running_count" class="text-3xl font-extrabold tracking-tight text-emerald-500">0</div>
                    </div>
                    <div class="glass-panel p-5 rounded-xl space-y-2">
                        <div class="text-xs text-zinc-400 uppercase tracking-widest font-semibold">System Nodes</div>
                        <div class="text-3xl font-extrabold tracking-tight text-amber-500">3 <span class="text-xs text-zinc-400 font-normal">/ 3 online</span></div>
                    </div>
                </div>

                <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                    
                    <!-- Cluster Nodes Grid -->
                    <div class="glass-panel p-5 rounded-xl space-y-4">
                        <h3 class="text-sm uppercase tracking-widest font-bold text-zinc-400">Node Cluster Status</h3>
                        <div class="space-y-3">
                            <div class="flex items-center justify-between p-3 bg-zinc-950/40 rounded-lg border border-white/5">
                                <div>
                                    <div class="text-sm font-bold">Inference Host (mac)</div>
                                    <div class="text-[11px] text-zinc-500 font-mono">Gemma 4 FP16 - 192.168.0.234</div>
                                </div>
                                <span class="bg-emerald-500/10 text-emerald-400 text-[10px] px-2 py-0.5 rounded font-bold uppercase">Online</span>
                            </div>
                            <div class="flex items-center justify-between p-3 bg-zinc-950/40 rounded-lg border border-white/5">
                                <div>
                                    <div class="text-sm font-bold">Applications Host (dell)</div>
                                    <div class="text-[11px] text-zinc-500 font-mono">Linux Server Core - 192.168.0.162</div>
                                </div>
                                <span class="bg-emerald-500/10 text-emerald-400 text-[10px] px-2 py-0.5 rounded font-bold uppercase">Online</span>
                            </div>
                            <div class="flex items-center justify-between p-3 bg-zinc-950/40 rounded-lg border border-white/5">
                                <div>
                                    <div class="text-sm font-bold">Local Bridge Client (localhost)</div>
                                    <div class="text-[11px] text-zinc-500 font-mono">Desktop Anchor Socket - port 8080</div>
                                </div>
                                <span class="bg-emerald-500/10 text-emerald-400 text-[10px] px-2 py-0.5 rounded font-bold uppercase">Online</span>
                            </div>
                        </div>
                    </div>

                    <!-- Attention List (Running Activities/Tasks) -->
                    <div class="glass-panel p-5 rounded-xl space-y-4">
                        <h3 class="text-sm uppercase tracking-widest font-bold text-zinc-400">Attention / Active Loops</h3>
                        <div id="overview_running_list" class="space-y-3 scrollbar-custom max-h-[220px] overflow-y-auto pr-1">
                            <div class="text-xs text-zinc-500 text-center py-6">No running background activities.</div>
                        </div>
                    </div>

                </div>

            </section>

            <!-- ── TAB: DICTATIONS ── -->
            <section id="tab-dictations" class="flex-1 hidden flex flex-col overflow-hidden">
                <div class="p-6 border-b border-white/5 flex items-center justify-between bg-zinc-950/20">
                    <div>
                        <h2 class="text-lg font-bold tracking-wide">Dictations</h2>
                        <p class="text-xs text-zinc-400">Incoming unfiled voice transcripts. Direct inline editing and copy controls.</p>
                    </div>
                </div>
                <!-- Timeline lists -->
                <div id="dictations_container" class="flex-1 overflow-y-auto p-6 scrollbar-custom space-y-4">
                    <!-- Cards will be populated here -->
                </div>
            </section>

            <!-- ── TAB: WORKSPACES ── -->
            <section id="tab-workspaces" class="flex-1 hidden flex overflow-hidden">
                
                <!-- Workspace List Sidebar -->
                <div class="w-60 border-r border-white/5 bg-zinc-950/10 flex flex-col">
                    <div class="p-4 border-b border-white/5 flex items-center justify-between">
                        <span class="text-xs uppercase tracking-widest font-bold text-zinc-400">Select Workspace</span>
                    </div>
                    <div id="workspace_list" class="flex-1 overflow-y-auto p-2 space-y-1 scrollbar-custom">
                        <!-- Loaded dynamically -->
                    </div>
                </div>

                <!-- Workspace Timelines Feed -->
                <div class="w-72 border-r border-white/5 bg-zinc-950/20 flex flex-col">
                    <div class="p-4 border-b border-white/5 flex items-center justify-between">
                        <span class="text-xs uppercase tracking-widest font-bold text-zinc-400">Timeline</span>
                        <button onclick="openCreateArtifactModal()" class="text-zinc-400 hover:text-white" title="New Note/Task">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path></svg>
                        </button>
                    </div>
                    <!-- Type filters -->
                    <div class="p-2 border-b border-white/5 flex gap-1">
                        <select id="art_filter_type" onchange="loadWorkspaceTimeline()" class="w-full text-[11px] bg-zinc-900 border border-white/10 rounded px-2 py-1 text-zinc-300 focus:outline-none">
                            <option value="">All Types</option>
                            <option value="Note">Notes</option>
                            <option value="Task">Tasks</option>
                            <option value="Reminder">Reminders</option>
                            <option value="Research">Research Requests</option>
                            <option value="Agent Activity">Agent Activities</option>
                        </select>
                    </div>
                    <div id="artifacts_timeline" class="flex-1 overflow-y-auto p-3 space-y-3 scrollbar-custom">
                        <!-- Populated dynamically -->
                    </div>
                </div>

                <!-- Active Editor / Canvas View -->
                <div class="flex-1 flex flex-col overflow-hidden bg-zinc-950/40">
                    <div id="editor_empty_view" class="flex-1 flex flex-col items-center justify-center p-6 text-zinc-500 space-y-2">
                        <svg class="w-12 h-12 text-zinc-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path></svg>
                        <p class="text-sm">Select an artifact from the timeline to edit or review.</p>
                    </div>
                    
                    <div id="editor_pane" class="flex-1 hidden flex flex-col overflow-hidden">
                        
                        <!-- Header / Metadata bar -->
                        <div class="p-4 border-b border-white/5 flex items-center justify-between bg-zinc-950/20">
                            <div class="flex items-center gap-3">
                                <span id="editor_meta_type" class="text-[10px] font-bold tracking-widest uppercase bg-amber-500/10 text-amber-500 px-2 py-0.5 rounded">Note</span>
                                <span id="editor_meta_time" class="text-xs text-zinc-500 font-mono">Created Just Now</span>
                            </div>
                            <div class="flex items-center gap-2">
                                <select id="edit_status" class="bg-zinc-900 border border-white/10 text-xs px-2 py-1 rounded text-zinc-300 focus:outline-none focus:border-amber-500">
                                    <option value="Completed">Completed</option>
                                    <option value="Pending">Pending</option>
                                    <option value="Running">Running</option>
                                </select>
                                <button onclick="saveActiveArtifact()" class="bg-amber-500 hover:bg-amber-600 text-zinc-950 text-xs font-bold px-3 py-1.5 rounded transition">Save</button>
                                <button onclick="deleteActiveArtifact()" class="bg-red-500/10 hover:bg-red-500/20 text-red-400 text-xs font-bold px-3 py-1.5 rounded transition">Delete</button>
                            </div>
                        </div>

                        <!-- Editor Fields -->
                        <div class="flex-1 flex overflow-hidden">
                            <!-- Left: Editor fields -->
                            <div class="flex-1 flex flex-col p-5 space-y-4 overflow-y-auto scrollbar-custom border-r border-white/5">
                                <div class="space-y-1">
                                    <label class="text-[10px] uppercase tracking-wider text-zinc-500 font-bold">Title</label>
                                    <input id="edit_title" type="text" class="w-full text-base font-semibold bg-zinc-950 border border-white/10 rounded px-3 py-2 text-zinc-100 focus:outline-none focus:border-amber-500" />
                                </div>
                                <div class="flex-1 flex flex-col space-y-1">
                                    <label class="text-[10px] uppercase tracking-wider text-zinc-500 font-bold">Content (Markdown Support)</label>
                                    <textarea id="edit_content" class="flex-1 w-full text-sm code-font bg-zinc-950 border border-white/10 rounded p-3 text-zinc-200 focus:outline-none focus:border-amber-500 scrollbar-custom resize-none" placeholder="Enter notes or markdown here..."></textarea>
                                </div>
                            </div>

                            <!-- Right: Logs console or Preview -->
                            <div class="w-80 flex flex-col overflow-hidden bg-zinc-950/60 p-4 space-y-3">
                                <div class="flex items-center justify-between border-b border-white/5 pb-2">
                                    <span class="text-xs uppercase tracking-widest font-bold text-zinc-400">Agent Output & Logs</span>
                                    <span id="agent_status_pill" class="w-2 h-2 rounded-full bg-zinc-500" title="Inactive"></span>
                                </div>
                                <div id="agent_logs_console" class="flex-1 overflow-y-auto text-[11px] code-font text-zinc-400 space-y-2.5 p-2 bg-zinc-950 rounded border border-white/5 scrollbar-custom">
                                    <!-- Log elements will stream here -->
                                    <div class="text-zinc-600 text-center py-8">Select a job to stream active run logs.</div>
                                </div>
                                <div id="agent_log_input_bar" class="flex gap-1.5 pt-1.5 border-t border-white/5 hidden">
                                    <input id="agent_inject_msg" type="text" placeholder="Inject log..." class="flex-1 text-[11px] bg-zinc-900 border border-white/10 rounded px-2 py-1 text-zinc-200 focus:outline-none focus:border-amber-500" />
                                    <button onclick="injectAgentLog()" class="bg-emerald-500/10 text-emerald-400 font-semibold text-[10px] px-2 py-1 rounded border border-emerald-500/20 hover:bg-emerald-500/25 transition">Add</button>
                                </div>
                            </div>
                        </div>

                    </div>
                </section>

            </section>

            <!-- ── TAB: DEVELOPER ROUTE ── -->
            <section id="tab-developer" class="flex-1 hidden flex flex-col overflow-hidden p-6 space-y-6">
                
                <!-- Telemetry Row -->
                <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
                    <!-- CPU usage sparkline -->
                    <div class="glass-panel p-5 rounded-xl space-y-3 relative overflow-hidden">
                        <div class="flex items-center justify-between">
                            <span class="text-xs uppercase tracking-widest font-bold text-zinc-400">Node CPU Telemetry</span>
                            <span id="dev_cpu_percent" class="text-sm font-bold text-amber-500">12%</span>
                        </div>
                        <div class="h-12 w-full flex items-end">
                            <svg class="w-full h-full" viewBox="0 0 300 60">
                                <path id="sparkline_cpu" fill="none" stroke="#f59e0b" stroke-width="1.5" d="M 0,40 L 30,42 L 60,38 L 90,45 L 120,35 L 150,42 L 180,39 L 210,31 L 240,43 L 270,35 L 300,48" />
                            </svg>
                        </div>
                    </div>

                    <!-- Latency Sparkline -->
                    <div class="glass-panel p-5 rounded-xl space-y-3 relative overflow-hidden">
                        <div class="flex items-center justify-between">
                            <span class="text-xs uppercase tracking-widest font-bold text-zinc-400">Host Response Latency</span>
                            <span id="dev_latency" class="text-sm font-bold text-emerald-400">1.2ms</span>
                        </div>
                        <div class="h-12 w-full flex items-end">
                            <svg class="w-full h-full" viewBox="0 0 300 60">
                                <path id="sparkline_latency" fill="none" stroke="#10b981" stroke-width="1.5" d="M 0,30 L 30,32 L 60,28 L 90,35 L 120,25 L 150,32 L 180,29 L 210,21 L 240,33 L 270,25 L 300,38" />
                            </svg>
                        </div>
                    </div>

                    <!-- Memory Gauge -->
                    <div class="glass-panel p-5 rounded-xl space-y-3">
                        <div class="flex items-center justify-between">
                            <span class="text-xs uppercase tracking-widest font-bold text-zinc-400">Cluster VRAM Allocation</span>
                            <span class="text-sm font-bold text-indigo-400">14.2 GB / 16 GB</span>
                        </div>
                        <div class="w-full bg-zinc-900 rounded-full h-2">
                            <div class="bg-indigo-500 h-2 rounded-full" style="width: 88.7%"></div>
                        </div>
                    </div>
                </div>

                <!-- Monospace Logging terminal -->
                <div class="flex-1 glass-panel rounded-xl flex flex-col overflow-hidden">
                    <div class="p-3 bg-zinc-950/60 border-b border-white/5 flex items-center justify-between">
                        <span class="text-xs uppercase tracking-widest font-bold text-zinc-400">Real-time Event Ledger Console</span>
                        <div class="flex items-center gap-1.5">
                            <span class="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                            <span class="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Streaming</span>
                        </div>
                    </div>
                    <div id="dev_console" class="flex-1 p-4 overflow-y-auto text-[11px] code-font text-zinc-300 space-y-2 bg-black/60 scrollbar-custom">
                        <!-- Dynamic output streams -->
                    </div>
                </div>

            </section>

            <!-- ── TAB: SETTINGS ── -->
            <section id="tab-settings" class="flex-1 hidden overflow-y-auto p-6 scrollbar-custom space-y-6 max-w-4xl">
                
                <h2 class="text-lg font-bold tracking-wide border-b border-white/5 pb-2">Desktop Settings & Theme Calibration</h2>

                <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                    
                    <!-- Theme Accent Panel -->
                    <div class="glass-panel p-5 rounded-xl space-y-5">
                        <h3 class="text-sm font-bold text-zinc-300">Widget Appearance Accent</h3>
                        
                        <!-- Presets -->
                        <div class="space-y-2">
                            <label class="text-xs text-zinc-500 uppercase font-semibold tracking-wider">Presets</label>
                            <div class="grid grid-cols-3 gap-2">
                                <button onclick="selectPreset('champagne')" id="preset-champagne" class="flex items-center justify-center gap-2 p-2 bg-zinc-900 rounded border border-white/10 text-xs hover:border-amber-500">
                                    <span class="w-3 h-3 rounded-full bg-[#c9a96e]"></span> Champagne
                                </button>
                                <button onclick="selectPreset('sapphire')" id="preset-sapphire" class="flex items-center justify-center gap-2 p-2 bg-zinc-900 rounded border border-white/10 text-xs hover:border-amber-500">
                                    <span class="w-3 h-3 rounded-full bg-[#4f6d7a]"></span> Sapphire
                                </button>
                                <button onclick="selectPreset('sage')" id="preset-sage" class="flex items-center justify-center gap-2 p-2 bg-zinc-900 rounded border border-white/10 text-xs hover:border-amber-500">
                                    <span class="w-3 h-3 rounded-full bg-[#7f9a82]"></span> Sage
                                </button>
                                <button onclick="selectPreset('blush')" id="preset-blush" class="flex items-center justify-center gap-2 p-2 bg-zinc-900 rounded border border-white/10 text-xs hover:border-amber-500">
                                    <span class="w-3 h-3 rounded-full bg-[#d4a373]"></span> Blush
                                </button>
                                <button onclick="selectPreset('lavender')" id="preset-lavender" class="flex items-center justify-center gap-2 p-2 bg-zinc-900 rounded border border-white/10 text-xs hover:border-amber-500">
                                    <span class="w-3 h-3 rounded-full bg-[#8a7ba7]"></span> Lavender
                                </button>
                                <button onclick="selectPreset('silver')" id="preset-silver" class="flex items-center justify-center gap-2 p-2 bg-zinc-900 rounded border border-white/10 text-xs hover:border-amber-500">
                                    <span class="w-3 h-3 rounded-full bg-[#b5b5ba]"></span> Silver
                                </button>
                            </div>
                        </div>

                        <!-- Custom Hex / Opacity -->
                        <div class="space-y-4 pt-2">
                            <div class="grid grid-cols-2 gap-4">
                                <div class="space-y-1">
                                    <label class="text-xs text-zinc-500">Custom Hex Accent</label>
                                    <div class="flex gap-1.5">
                                        <input type="color" id="settings_color_picker" class="w-8 h-8 rounded bg-transparent border-0 cursor-pointer" oninput="document.getElementById('settings_custom_hex').value = this.value" />
                                        <input id="settings_custom_hex" type="text" value="#c9a96e" class="w-full text-xs font-mono bg-zinc-950 border border-white/10 rounded px-2.5 py-1 text-zinc-200 focus:outline-none focus:border-amber-500" onchange="document.getElementById('settings_color_picker').value = this.value" />
                                    </div>
                                </div>
                                <div class="space-y-1">
                                    <label class="text-xs text-zinc-500">Mica Frame Opacity (%)</label>
                                    <input id="settings_opacity" type="number" min="10" max="100" class="w-full text-xs bg-zinc-950 border border-white/10 rounded px-2.5 py-1.5 text-zinc-200 focus:outline-none" />
                                </div>
                            </div>
                            <div class="flex items-center gap-3">
                                <input id="settings_sync_dwm" type="checkbox" class="rounded text-amber-500 bg-zinc-950 border-white/10 focus:outline-none" />
                                <label class="text-xs text-zinc-400 font-semibold">Sync accent automatically with Windows DWM</label>
                            </div>
                        </div>

                        <button onclick="saveThemeSettings()" class="w-full bg-amber-500 hover:bg-amber-600 text-zinc-950 font-bold py-2 rounded text-xs transition duration-200">
                            Apply Theme Settings
                        </button>
                    </div>

                    <!-- Dictation simulator panel -->
                    <div class="glass-panel p-5 rounded-xl space-y-5">
                        <h3 class="text-sm font-bold text-zinc-300">Voice Dictation Simulator</h3>
                        <p class="text-xs text-zinc-400">Trigger simulated voice commands to verify STT intake pipelines and see Desktop Quick Peek cards pop up instantly.</p>
                        
                        <div class="space-y-3">
                            <textarea id="settings_dict_text" rows="3" class="w-full text-sm bg-zinc-950 border border-white/10 rounded p-2.5 text-zinc-200 focus:outline-none focus:border-amber-500 scrollbar-custom" placeholder="Type notes here (e.g. remind me to run tests tomorrow morning)..."></textarea>
                            <button onclick="triggerSimulatedDictation()" class="w-full bg-zinc-800 hover:bg-zinc-700 text-zinc-200 font-bold py-2 rounded text-xs transition duration-200">
                                Simulate Speech Capture Intake
                            </button>
                        </div>
                    </div>

                </div>

            </section>

        </main>
    </div>

    <!-- Modals: Create Artifact -->
    <div id="create_artifact_modal" class="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 items-center justify-center hidden">
        <div class="glass-panel p-6 rounded-2xl w-[450px] space-y-4">
            <div class="flex justify-between border-b border-white/5 pb-2">
                <h3 class="font-bold text-base">Inject Custom Workspace Artifact</h3>
                <button onclick="closeCreateArtifactModal()" class="text-zinc-500 hover:text-white">&times;</button>
            </div>
            <div class="grid grid-cols-2 gap-3">
                <div class="space-y-1">
                    <label class="text-xs text-zinc-400">Workspace</label>
                    <select id="modal_workspace" class="w-full text-xs bg-zinc-900 border border-white/10 rounded p-1.5 focus:outline-none">
                        <option value="recent">Recent (Unfiled)</option>
                    </select>
                </div>
                <div class="space-y-1">
                    <label class="text-xs text-zinc-400">Artifact Type</label>
                    <select id="modal_type" class="w-full text-xs bg-zinc-900 border border-white/10 rounded p-1.5 focus:outline-none">
                        <option value="Note">Note</option>
                        <option value="Task">Task</option>
                        <option value="Reminder">Reminder</option>
                        <option value="Research">Research Request</option>
                        <option value="Agent Activity">Agent Activity</option>
                    </select>
                </div>
            </div>
            <div class="space-y-1">
                <label class="text-xs text-zinc-400">Title</label>
                <input id="modal_title" type="text" placeholder="Artifact title..." class="w-full text-xs bg-zinc-900 border border-white/10 rounded p-1.5 focus:outline-none focus:border-amber-500" />
            </div>
            <div class="space-y-1">
                <label class="text-xs text-zinc-400">Content</label>
                <textarea id="modal_content" rows="4" class="w-full text-xs bg-zinc-900 border border-white/10 rounded p-2 focus:outline-none focus:border-amber-500 scrollbar-custom resize-none" placeholder="Markdown supported details..."></textarea>
            </div>
            <button onclick="createArtifact()" class="w-full bg-amber-500 hover:bg-amber-600 text-zinc-950 font-bold py-2 rounded text-xs transition duration-150">Create Artifact</button>
        </div>
    </div>

    <!-- UI Logic Scripts -->
    <script>
        let currentTab = 'overview';
        let workspaces = [];
        let selectedWorkspaceId = null;
        let selectedArtifactId = null;
        let activeArtifactsList = [];
        let logsPollingInterval = null;
        let editingArtifactId = null;
        let activeDictations = [];

        // Sparkline buffers
        let cpuHistory = [12, 14, 18, 11, 16, 21, 19, 25, 29, 24, 21];
        let latencyHistory = [1.2, 1.5, 1.1, 1.8, 1.4, 2.3, 1.9, 1.5, 2.8, 2.1, 1.2];

        function switchTab(tabId) {
            document.querySelectorAll('nav button').forEach(b => {
                b.classList.remove('bg-white/5', 'text-white');
                b.classList.add('text-zinc-400');
            });
            document.querySelectorAll('main > section').forEach(s => s.classList.add('hidden'));

            const button = document.getElementById(`nav-${tabId}`);
            if (button) {
                button.classList.add('bg-white/5', 'text-white');
                button.classList.remove('text-zinc-400');
            }
            
            document.getElementById(`tab-${tabId}`).classList.remove('hidden');
            currentTab = tabId;

            // Load resources relative to tabs
            if (tabId === 'dictations') {
                loadDictationsTimeline();
            } else if (tabId === 'workspaces') {
                loadWorkspaces();
            } else if (tabId === 'settings') {
                loadThemeSettingsFields();
            }
        }

        // --- Database CRUD wrappers ---

        function loadWorkspaces() {
            fetch('/api/workspaces')
                .then(r => r.json())
                .then(data => {
                    workspaces = data;
                    
                    // Update create modal select list
                    const modalWs = document.getElementById('modal_workspace');
                    modalWs.innerHTML = '<option value="recent">Recent (Unfiled)</option>';
                    workspaces.forEach(w => {
                        const opt = document.createElement('option');
                        opt.value = w.id;
                        opt.text = w.name;
                        modalWs.add(opt);
                    });

                    // Update side list
                    const list = document.getElementById('workspace_list');
                    list.innerHTML = '';
                    
                    // Auto-select first workspace if none selected
                    if (!selectedWorkspaceId && workspaces.length > 0) {
                        selectedWorkspaceId = workspaces[0].id;
                    }

                    workspaces.forEach(w => {
                        const btn = document.createElement('button');
                        btn.className = `w-full text-left px-3 py-2 rounded-lg text-xs font-semibold flex items-center justify-between transition ${
                            selectedWorkspaceId === w.id ? 'bg-amber-500/10 text-amber-500 border border-amber-500/20' : 'text-zinc-400 hover:bg-white/5 hover:text-white'
                        }`;
                        btn.onclick = () => selectWorkspace(w.id);
                        btn.innerHTML = `
                            <span>${w.name}</span>
                            <span class="text-[9px] text-zinc-500 font-mono">/ws</span>
                        `;
                        list.appendChild(btn);
                    });

                    loadWorkspaceTimeline();
                });
        }

        function selectWorkspace(wsId) {
            selectedWorkspaceId = wsId;
            selectedArtifactId = null;
            document.getElementById('editor_pane').classList.add('hidden');
            document.getElementById('editor_empty_view').classList.remove('hidden');
            loadWorkspaces(); // Redraws borders
        }

        function loadWorkspaceTimeline() {
            if (!selectedWorkspaceId) return;
            const filterType = document.getElementById('art_filter_type').value;
            
            fetch(`/api/artifacts?workspace_id=${selectedWorkspaceId}`)
                .then(r => r.json())
                .then(data => {
                    // Filter by type if select box matches
                    if (filterType) {
                        data = data.filter(a => a.type === filterType);
                    }
                    
                    const list = document.getElementById('artifacts_timeline');
                    list.innerHTML = '';

                    if (data.length === 0) {
                        list.innerHTML = '<div class="text-xs text-zinc-600 text-center py-8">Timeline is empty.</div>';
                        return;
                    }

                    data.forEach(a => {
                        const div = document.createElement('div');
                        div.className = `p-3 rounded-lg border cursor-pointer transition flex flex-col gap-1.5 ${
                            selectedArtifactId === a.id 
                                ? 'bg-zinc-900 border-amber-500/30' 
                                : 'bg-zinc-900/40 border-white/5 hover:border-white/10 hover:bg-zinc-900/60'
                        }`;
                        div.onclick = () => selectArtifact(a.id);

                        let typeBadge = `<span class="text-[8px] font-bold uppercase border border-white/15 px-1.5 py-0.5 rounded text-zinc-400 font-mono">${a.type}</span>`;
                        if (a.status === 'Running') {
                            typeBadge = `<span class="text-[8px] font-bold uppercase bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-1.5 py-0.5 rounded font-mono animate-pulse">Running</span>`;
                        } else if (a.status === 'Pending') {
                            typeBadge = `<span class="text-[8px] font-bold uppercase bg-amber-500/10 text-amber-500 border border-amber-500/20 px-1.5 py-0.5 rounded font-mono">Pending</span>`;
                        }

                        div.innerHTML = `
                            <div class="flex items-center justify-between">
                                ${typeBadge}
                                <span class="text-[9px] text-zinc-600 font-mono">${a.created_at.substring(11,16)}</span>
                            </div>
                            <div class="text-xs font-bold text-zinc-200 truncate">${a.title}</div>
                        `;
                        list.appendChild(div);
                    });
                });
        }

        function selectArtifact(artId) {
            selectedArtifactId = artId;
            // Clear current console interval
            if (logsPollingInterval) clearInterval(logsPollingInterval);

            fetch(`/api/artifact?id=${artId}`)
                .then(r => r.json())
                .then(a => {
                    if (!a) return;
                    document.getElementById('editor_empty_view').classList.add('hidden');
                    document.getElementById('editor_pane').classList.remove('hidden');

                    document.getElementById('editor_meta_type').innerText = a.type;
                    document.getElementById('editor_meta_time').innerText = `Created at ${a.created_at.replace('T', ' ').substring(0, 19)}`;
                    
                    document.getElementById('edit_title').value = a.title;
                    document.getElementById('edit_content').value = a.content;
                    document.getElementById('edit_status').value = a.status;

                    // Display inject bar if type is Agent Activity
                    const bar = document.getElementById('agent_log_input_bar');
                    if (a.type === 'Agent Activity' || a.status === 'Running') {
                        bar.classList.remove('hidden');
                    } else {
                        bar.classList.add('hidden');
                    }

                    // Poll logs
                    loadAgentLogs(artId);
                    logsPollingInterval = setInterval(() => loadAgentLogs(artId), 1500);

                    // Re-draw border selection in timeline list
                    loadWorkspaceTimeline();
                });
        }

        function loadAgentLogs(artId) {
            fetch(`/api/logs?artifact_id=${artId}`)
                .then(r => r.json())
                .then(data => {
                    const consolePanel = document.getElementById('agent_logs_console');
                    const indicator = document.getElementById('agent_status_pill');
                    
                    // Check status to light up agent indicator
                    const status = document.getElementById('edit_status').value;
                    if (status === 'Running') {
                        indicator.className = 'w-2 h-2 rounded-full bg-emerald-500 animate-pulse';
                    } else if (status === 'Completed') {
                        indicator.className = 'w-2 h-2 rounded-full bg-zinc-600';
                    } else {
                        indicator.className = 'w-2 h-2 rounded-full bg-amber-500';
                    }

                    consolePanel.innerHTML = '';
                    if (data.length === 0) {
                        consolePanel.innerHTML = '<div class="text-zinc-600 text-center py-8">Console idle. No running logs generated yet.</div>';
                        return;
                    }
                    data.forEach(msg => {
                        const line = document.createElement('div');
                        line.className = 'border-b border-white/5 pb-1';
                        line.innerHTML = `<span class="text-amber-500/70 mr-1.5">></span>${msg}`;
                        consolePanel.appendChild(line);
                    });
                    // Scroll to bottom
                    consolePanel.scrollTop = consolePanel.scrollHeight;
                });
        }

        function injectAgentLog() {
            const input = document.getElementById('agent_inject_msg');
            const msg = input.value.trim();
            if (!msg || !selectedArtifactId) return;

            fetch('/api/logs', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({artifact_id: selectedArtifactId, message: msg})
            }).then(r => r.json()).then(data => {
                if (data.ok) {
                    input.value = '';
                    loadAgentLogs(selectedArtifactId);
                }
            });
        }

        function saveActiveArtifact() {
            if (!selectedArtifactId) return;
            const title = document.getElementById('edit_title').value;
            const content = document.getElementById('edit_content').value;
            const status = document.getElementById('edit_status').value;

            fetch('/api/artifact/update', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({id: selectedArtifactId, title: title, content: content, status: status})
            }).then(r => r.json()).then(data => {
                if (data.ok) {
                    alert("Artifact saved successfully!");
                    selectArtifact(selectedArtifactId);
                }
            });
        }

        function deleteActiveArtifact() {
            if (!selectedArtifactId || !confirm("Are you sure you want to delete this artifact?")) return;
            fetch('/api/artifact/delete', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({id: selectedArtifactId})
            }).then(r => r.json()).then(data => {
                if (data.ok) {
                    if (logsPollingInterval) clearInterval(logsPollingInterval);
                    selectedArtifactId = null;
                    document.getElementById('editor_pane').classList.add('hidden');
                    document.getElementById('editor_empty_view').classList.remove('hidden');
                    loadWorkspaceTimeline();
                }
            });
        }

        // --- Modal helpers ---
        
        function openCreateArtifactModal() {
            document.getElementById('create_artifact_modal').classList.remove('hidden');
            document.getElementById('create_artifact_modal').classList.add('flex');
            document.getElementById('modal_title').value = '';
            document.getElementById('modal_content').value = '';
        }

        function closeCreateArtifactModal() {
            document.getElementById('create_artifact_modal').classList.add('hidden');
            document.getElementById('create_artifact_modal').classList.remove('flex');
        }

        function createArtifact() {
            const ws = document.getElementById('modal_workspace').value;
            const type = document.getElementById('modal_type').value;
            const title = document.getElementById('modal_title').value;
            const content = document.getElementById('modal_content').value;

            if (!title) {
                alert("Please specify a title.");
                return;
            }

            fetch('/api/artifact/create', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({workspace_id: ws, type: type, title: title, content: content, status: 'Completed'})
            }).then(r => r.json()).then(data => {
                if (data.ok) {
                    closeCreateArtifactModal();
                    if (ws === 'recent') {
                        switchTab('recent');
                    } else {
                        selectedWorkspaceId = ws;
                        loadWorkspaces();
                    }
                }
            });
        }

        // --- Dictations Intakes Page (Copy & Edit) ---

        function loadDictationsTimeline() {
            fetch('/api/artifacts?workspace_id=recent')
                .then(r => r.json())
                .then(data => {
                    activeDictations = data;
                    
                    // Update badges
                    const badge = document.getElementById('badge_dictations_count');
                    const headerCount = document.getElementById('global_intake_count');
                    headerCount.innerText = data.length;
                    
                    if (data.length > 0) {
                        badge.innerText = data.length;
                        badge.classList.remove('hidden');
                    } else {
                        badge.classList.add('hidden');
                    }

                    const container = document.getElementById('dictations_container');
                    container.innerHTML = '';

                    if (data.length === 0) {
                        container.innerHTML = `
                            <div class="glass-panel p-10 rounded-2xl flex flex-col items-center justify-center text-zinc-500 space-y-3">
                                <svg class="w-12 h-12 text-zinc-700" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"></path></svg>
                                <span class="text-sm font-semibold">Dictations queue is empty. Capture something to start!</span>
                            </div>
                        `;
                        return;
                    }

                    data.forEach(a => {
                        const card = document.createElement('div');
                        card.className = 'glass-panel p-5 rounded-xl space-y-4 flex flex-col md:flex-row items-start justify-between gap-6 transition hover:border-white/15';
                        
                        if (editingArtifactId === a.id) {
                            card.innerHTML = `
                                <div class="flex-1 space-y-3 pr-4 w-full">
                                    <div class="flex items-center gap-3">
                                        <span class="text-[9px] uppercase tracking-wider bg-amber-500/10 text-amber-500 font-bold px-2 py-0.5 rounded">Editing</span>
                                        <span class="text-xs text-zinc-500 font-mono">${a.created_at.replace('T', ' ').substring(0, 19)}</span>
                                    </div>
                                    <div class="space-y-1">
                                        <label class="text-[10px] uppercase tracking-wider text-zinc-500 font-bold">Title</label>
                                        <input id="edit-title-${a.id}" type="text" class="w-full text-sm bg-zinc-950 border border-white/10 rounded px-2.5 py-1 text-zinc-100 focus:outline-none focus:border-amber-500 font-semibold" value="${a.title}" />
                                    </div>
                                    <div class="space-y-1">
                                        <label class="text-[10px] uppercase tracking-wider text-zinc-500 font-bold">Content</label>
                                        <textarea id="edit-content-${a.id}" rows="3" class="w-full text-xs code-font bg-zinc-950 border border-white/10 rounded p-2 text-zinc-200 focus:outline-none focus:border-amber-500 resize-none scrollbar-custom">${a.content}</textarea>
                                    </div>
                                </div>
                                <div class="flex flex-col md:flex-row items-center gap-2 self-end md:self-center shrink-0 w-full md:w-auto">
                                    <button onclick="saveInlineDictation('${a.id}')" class="w-full md:w-auto text-xs bg-emerald-500 hover:bg-emerald-600 text-zinc-950 px-3 py-1.5 rounded font-bold transition">Save</button>
                                    <button onclick="cancelInlineEdit()" class="w-full md:w-auto text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-white/10 px-3 py-1.5 rounded font-bold transition">Cancel</button>
                                </div>
                            `;
                        } else {
                            card.innerHTML = `
                                <div class="flex-1 space-y-2">
                                    <div class="flex items-center gap-3">
                                        <span class="text-[9px] uppercase tracking-wider bg-amber-500/10 text-amber-500 font-bold px-2 py-0.5 rounded">Dictation</span>
                                        <span class="text-xs text-zinc-500 font-mono">${a.created_at.replace('T', ' ').substring(0, 19)}</span>
                                    </div>
                                    <div class="text-sm font-bold text-zinc-100">${a.title}</div>
                                    <blockquote class="text-sm border-l-2 border-zinc-700 pl-3 text-zinc-400 italic font-medium leading-relaxed">${a.content}</blockquote>
                                </div>
                                <div class="flex items-center gap-2 self-end md:self-center shrink-0">
                                    <button onclick="copyDictationText('${a.id}', this)" class="text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-white/10 px-3 py-1.5 rounded font-bold transition flex items-center gap-1.5">
                                        <svg class="w-3.5 h-3.5 text-zinc-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3"></path></svg>
                                        Copy
                                    </button>
                                    <button onclick="startInlineEdit('${a.id}')" class="text-xs bg-amber-500 hover:bg-amber-600 text-zinc-950 px-3 py-1.5 rounded font-bold transition flex items-center gap-1.5">
                                        <svg class="w-3.5 h-3.5 text-zinc-950" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path></svg>
                                        Edit
                                    </button>
                                </div>
                            `;
                        }
                        container.appendChild(card);
                    });
                });
        }

        function copyDictationText(artId, btn) {
            const item = activeDictations.find(x => x.id === artId);
            if (item && item.content) {
                navigator.clipboard.writeText(item.content).then(() => {
                    const originalText = btn.innerHTML;
                    btn.innerHTML = `
                        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
                        Copied
                    `;
                    btn.classList.add('text-emerald-400', 'border-emerald-500/30', 'bg-emerald-500/10');
                    setTimeout(() => {
                        btn.innerHTML = originalText;
                        btn.classList.remove('text-emerald-400', 'border-emerald-500/30', 'bg-emerald-500/10');
                    }, 1500);
                });
            }
        }

        function startInlineEdit(artId) {
            editingArtifactId = artId;
            loadDictationsTimeline();
        }

        function cancelInlineEdit() {
            editingArtifactId = null;
            loadDictationsTimeline();
        }

        function saveInlineDictation(artId) {
            const titleVal = document.getElementById(`edit-title-${artId}`).value.trim();
            const contentVal = document.getElementById(`edit-content-${artId}`).value.trim();
            if (!titleVal) {
                alert("Title cannot be empty.");
                return;
            }

            fetch('/api/artifact/update', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({id: artId, title: titleVal, content: contentVal})
            }).then(r => r.json()).then(data => {
                if (data.ok) {
                    editingArtifactId = null;
                    loadDictationsTimeline();
                } else {
                    alert("Error saving dictation: " + data.message);
                }
            });
        }

        // --- Developer / Sparklines & Event LEDGER ---

        function runTelemetryStream() {
            // Update CPU sparkline
            let lastCpu = cpuHistory[cpuHistory.length - 1];
            let nextCpu = Math.max(5, Math.min(95, lastCpu + Math.floor(Math.random() * 15) - 7));
            cpuHistory.push(nextCpu);
            if (cpuHistory.length > 20) cpuHistory.shift();
            document.getElementById('dev_cpu_percent').innerText = `${nextCpu}%`;

            let cpuPath = cpuHistory.map((val, idx) => `${idx * 15},${60 - val * 0.55}`).join(' L ');
            document.getElementById('sparkline_cpu').setAttribute('d', 'M ' + cpuPath);

            // Update Latency sparkline
            let lastLat = latencyHistory[latencyHistory.length - 1];
            let nextLat = Math.max(0.2, Math.min(8.0, lastLat + (Math.random() * 0.8) - 0.4));
            latencyHistory.push(nextLat);
            if (latencyHistory.length > 20) latencyHistory.shift();
            document.getElementById('dev_latency').innerText = `${nextLat.toFixed(1)}ms`;

            let latPath = latencyHistory.map((val, idx) => `${idx * 15},${60 - val * 6}`).join(' L ');
            document.getElementById('sparkline_latency').setAttribute('d', 'M ' + latPath);

            // Stream fake system ledger lines if Developer tab active
            if (currentTab === 'developer') {
                const logs = [
                    'Ledger entry synced. Workspace "Personal" loaded in background.',
                    'Audio capture device pipeline opened [sample_rate=16000].',
                    'Ollama server connection healthy. Latency 1.2ms.',
                    'Transmitted core.state transition to status dot.',
                    'Cleared window boundary mask on PyQt6 layout.',
                    'Crystallized voice dictation note. Inserted unfiled Recent card.'
                ];
                if (Math.random() > 0.6) {
                    const devConsole = document.getElementById('dev_console');
                    const div = document.createElement('div');
                    div.className = 'border-b border-white/5 pb-1 flex gap-4';
                    
                    const time = new Date().toISOString().substring(11,19);
                    const randLog = logs[Math.floor(Math.random() * logs.length)];
                    div.innerHTML = `
                        <span class="text-zinc-600 select-none">${time}</span>
                        <span class="text-emerald-500 font-bold select-none">[system]</span>
                        <span>${randLog}</span>
                    `;
                    devConsole.appendChild(div);
                    devConsole.scrollTop = devConsole.scrollHeight;
                }
            }
        }

        // --- Settings & Appearance Calibration ---

        function loadThemeSettingsFields() {
            fetch('/api/settings')
                .then(r => r.json())
                .then(s => {
                    document.getElementById('settings_sync_dwm').checked = s.accent_registry_sync;
                    document.getElementById('settings_custom_hex').value = s.active_accent_hex;
                    document.getElementById('settings_color_picker').value = s.active_accent_hex;
                    document.getElementById('settings_opacity').value = s.mica_opacity;
                    
                    // Highlight selected preset
                    document.querySelectorAll('[id^="preset-"]').forEach(btn => {
                        btn.className = btn.className.replace(' border-amber-500/50 bg-amber-500/5', ' border-white/10');
                    });
                    const selPresetBtn = document.getElementById(`preset-${s.accent_preset}`);
                    if (selPresetBtn) {
                        selPresetBtn.className = selPresetBtn.className.replace(' border-white/10', ' border-amber-500/50 bg-amber-500/5');
                    }
                });
        }

        function selectPreset(preset) {
            // Uncheck dwm check box
            document.getElementById('settings_sync_dwm').checked = false;
            
            fetch('/api/settings', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({preset: preset, sync_dwm: false})
            }).then(r => r.json()).then(data => {
                loadThemeSettingsFields();
            });
        }

        function saveThemeSettings() {
            const sync = document.getElementById('settings_sync_dwm').checked;
            const custom = document.getElementById('settings_custom_hex').value;
            const op = parseInt(document.getElementById('settings_opacity').value);

            fetch('/api/settings', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({sync_dwm: sync, custom_hex: custom, opacity: op})
            }).then(r => r.json()).then(data => {
                alert("Appearance saved!");
                loadThemeSettingsFields();
            });
        }

        function triggerSimulatedDictation() {
            const txt = document.getElementById('settings_dict_text').value.trim();
            if (!txt) {
                alert("Please enter speech command text.");
                return;
            }
            fetch('/api/dictate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({text: txt})
            }).then(r => r.json()).then(data => {
                alert(data.message);
                document.getElementById('settings_dict_text').value = '';
                loadDictationsTimeline();
            });
        }

        // --- Master Polling Loops ---

        function globalMonitoringLoop() {
            // Check active state
            fetch('/api/artifacts')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('stat_art_count').innerText = data.length;
                    
                    const running = data.filter(a => a.status === 'Running');
                    document.getElementById('stat_running_count').innerText = running.length;

                    // Update Overview running activities
                    const overContainer = document.getElementById('overview_running_list');
                    if (running.length === 0) {
                        overContainer.innerHTML = '<div class="text-xs text-zinc-500 text-center py-6">No running background activities.</div>';
                    } else {
                        overContainer.innerHTML = '';
                        running.forEach(r => {
                            const line = document.createElement('div');
                            line.className = 'p-3 bg-zinc-900/60 border border-white/5 rounded-lg flex items-center justify-between';
                            line.innerHTML = `
                                <div>
                                    <div class="text-xs font-bold text-zinc-200">${r.title}</div>
                                    <div class="text-[9px] text-zinc-500 uppercase font-mono tracking-wider">${r.type}</div>
                                </div>
                                <span class="text-[10px] text-emerald-400 font-mono animate-pulse uppercase font-semibold">Running</span>
                            `;
                            overContainer.appendChild(line);
                        });
                    }
                });

            // Get total workspaces counts
            fetch('/api/workspaces')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('stat_ws_count').innerText = data.length;
                });

            // Update badge counts for recent unfiled
            fetch('/api/artifacts?workspace_id=recent')
                .then(r => r.json())
                .then(data => {
                    const badge = document.getElementById('badge_dictations_count');
                    const headerCount = document.getElementById('global_intake_count');
                    headerCount.innerText = data.length;
                    if (data.length > 0) {
                        badge.innerText = data.length;
                        badge.classList.remove('hidden');
                    } else {
                        badge.classList.add('hidden');
                    }
                    if (currentTab === 'dictations') {
                        loadDictationsTimeline();
                    }
                });
        }

        // Run bootstrap on window load
        loadWorkspaces();
        globalMonitoringLoop();
        
        // Check hash to auto-switch tab
        const hash = window.location.hash.substring(1);
        if (hash && ['overview', 'dictations', 'workspaces', 'developer', 'settings'].includes(hash)) {
            switchTab(hash);
        }

        // 1.5s interval to check global numbers
        setInterval(globalMonitoringLoop, 1500);
        // Telemetry telemetry ticks (updates latency charts)
        setInterval(runTelemetryStream, 1000);
    </script>
</body>
</html>
"""
