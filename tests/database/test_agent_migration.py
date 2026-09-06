import unittest
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

class AgentMigrationRevisionTests(unittest.TestCase):
    def test_agent_tables_revision_is_linear_head(self) -> None:
        config = Config(str(_PROJECT_ROOT / "alembic.ini"))
        script = ScriptDirectory.from_config(config)

        self.assertSequenceEqual(script.get_current_head(), "e8f1a3c5d7b9")
        self.assertEqual(script.get_heads(), ["e8f1a3c5d7b9"])
        revision = script.get_revision("e8f1a3c5d7b9")
        self.assertEqual(revision.down_revision, "c4d8e2f1a930")