import unittest
from unittest import mock
import os
import tempfile
import sqlite3

import database

class TestDatabaseFilters(unittest.TestCase):
    def setUp(self):
        # Create a temporary file database to isolate test state
        self.db_fd, self.db_path = tempfile.mkstemp()
        self.db_patcher = mock.patch("database.DB_PATH", self.db_path)
        self.db_patcher.start()
        
        # Clear existing tables (if any) and seed clean schema
        database.init_db()

    def tearDown(self):
        self.db_patcher.stop()
        try:
            os.close(self.db_fd)
        except OSError:
            pass
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_recent_filter_returns_only_unfiled_notes(self):
        # Clean out seeded database to have a strict, controlled state
        conn = database.get_db_connection()
        conn.execute("DELETE FROM logs;")
        conn.execute("DELETE FROM artifacts;")
        conn.commit()
        conn.close()

        # 1. Unfiled Note (strictly a dictation)
        art_unfiled_note = database.add_artifact(
            workspace_id=None,
            art_type="Note",
            title="Unfiled Voice Note",
            content="This is a voice transcription capture.",
            status="Completed"
        )

        # 2. Unfiled Task (not a Note, should be excluded)
        art_unfiled_task = database.add_artifact(
            workspace_id=None,
            art_type="Task",
            title="Unfiled Task",
            content="Should not be in dictations.",
            status="Pending"
        )

        # 3. Filed Note (has workspace, should be excluded)
        art_filed_note = database.add_artifact(
            workspace_id="personal",
            art_type="Note",
            title="Personal Workspace Note",
            content="This is associated with personal workspace.",
            status="Completed"
        )

        # 4. Filed Task (has workspace, should be excluded)
        art_filed_task = database.add_artifact(
            workspace_id="personal",
            art_type="Task",
            title="Personal Workspace Task",
            content="This is a personal workspace task.",
            status="Pending"
        )

        # Query recent artifacts (workspace_id = 'recent')
        recent_artifacts = database.get_artifacts("recent")

        # Assert only the unfiled Note is returned
        recent_ids = [r["id"] for r in recent_artifacts]
        
        self.assertIn(art_unfiled_note, recent_ids)
        self.assertNotIn(art_unfiled_task, recent_ids)
        self.assertNotIn(art_filed_note, recent_ids)
        self.assertNotIn(art_filed_task, recent_ids)

        self.assertEqual(len(recent_artifacts), 1)
        self.assertEqual(recent_artifacts[0]["title"], "Unfiled Voice Note")
        self.assertEqual(recent_artifacts[0]["type"], "Note")
        self.assertIsNone(recent_artifacts[0]["workspace_id"])
