"""Validate that every YAML example in docs/task-schema.md parses without error."""

import re
from pathlib import Path

import pytest
import yaml

from grind.tasks import build_task_graph


SCHEMA_DOC = Path(__file__).parent.parent / "docs" / "task-schema.md"


def _extract_yaml_examples() -> list[tuple[str, str]]:
    """Return list of (label, yaml_text) pairs extracted from fenced code blocks."""
    text = SCHEMA_DOC.read_text()
    # Match ```yaml blocks that start with "# example: <label>"
    pattern = re.compile(r"```yaml\n# example: (\S+)\n(.*?)```", re.DOTALL)
    return [(m.group(1), m.group(2)) for m in pattern.finditer(text)]


EXAMPLES = _extract_yaml_examples()


@pytest.mark.parametrize("label,yaml_text", EXAMPLES, ids=[e[0] for e in EXAMPLES])
def test_schema_example_parses(label: str, yaml_text: str, tmp_path: Path) -> None:
    """Each named example in docs/task-schema.md must be accepted by build_task_graph."""
    task_file = tmp_path / f"{label}.yaml"
    task_file.write_text(yaml_text)
    # build_task_graph raises ValueError on any parse or validation error
    graph = build_task_graph(str(task_file))
    assert len(graph.nodes) >= 1, f"Example '{label}' produced an empty graph"
