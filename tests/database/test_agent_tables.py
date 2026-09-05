import unittest

from app.database.agent_tables import (
    AgentConditionWriteTable,
    AgentMemoryTable,
    AgentMessageTable,
    AgentSessionTable,
)
# Register domain tables to the base metadata
from app.database.domain_tables import InvestmentThesisTable, ThesisConditionTable
from app.database.base import Base

def _constraint_names(table) -> set[str]:
    return {constraint.name for constraint in table.constraints}

def _index_names(table) -> set[str]:
    return {index.name for index in table.indexes}

# input: ForeignKeyConstraint(
#     ["thesis_id", "user_id"],
#     ["investment_theses.id", "investment_theses.user_id"],
#     name="agent_session_thesis_owner",
#     ondelete="CASCADE",
# ),
# return: {(("thesis_id", "user_id"), "investment_theses")}
def _foreign_key_pairs(table) -> set[tuple[tuple[str, ...], str]]:
    pairs: set[tuple[tuple[str, ...], str]] = set()
    for constraint in table.foreign_key_constraints:
        local_columns = tuple(column.name for column in constraint.columns)
        pairs.add((local_columns, constraint.referred_table.name))
    return pairs

class AgentTableContractTests(unittest.TestCase):
    def test_tables_are_registered_on_shared_metadata(self) -> None:
        expected = {
            "agent_sessions",
            "agent_messages",
            "agent_memory",
            "agent_condition_writes",
        }
        self.assertTrue(expected.issubset(Base.metadata.tables))
    def test_session_owns_identity_and_points_at_thesis(self) -> None:
        names = _constraint_names(AgentSessionTable.__table__)
        self.assertIn("agent_session_owner_identity", names)
        self.assertIn("agent_session_thesis_chain", names)
        self.assertIn("agent_session_thesis_owner", names)
        self.assertIn(
            (("thesis_id", "user_id"), "investment_theses"),
            _foreign_key_pairs(AgentSessionTable.__table__),
        )
        self.assertIn(
            "uq_agent_sessions_one_open_per_thesis",
            _index_names(AgentSessionTable.__table__),
        )
    def test_messages_and_memory_cannot_change_owner(self) -> None:
        self.assertIn(
            (("session_id", "user_id"), "agent_sessions"),
            _foreign_key_pairs(AgentMessageTable.__table__),
        )
        self.assertIn(
            (("session_id", "user_id"), "agent_sessions"),
            _foreign_key_pairs(AgentMemoryTable.__table__),
        )
        memory_names = _constraint_names(AgentMemoryTable.__table__)
        self.assertIn("agent_memory_session_identity", memory_names)
    def test_condition_writes_bind_session_message_and_condition(self) -> None:
        pairs = _foreign_key_pairs(AgentConditionWriteTable.__table__)
        self.assertIn(
            (("session_id", "thesis_id", "user_id"), "agent_sessions"),
            pairs,
        )
        self.assertIn(
            (("message_id", "session_id", "user_id"), "agent_messages"),
            pairs,
        )
        self.assertIn(
            (("condition_id", "thesis_id", "user_id"), "thesis_conditions"),
            pairs,
        )
    def test_timestamps_are_timezone_aware(self) -> None:
        self.assertTrue(AgentSessionTable.__table__.c.created_at.type.timezone)
        self.assertTrue(AgentMessageTable.__table__.c.created_at.type.timezone)