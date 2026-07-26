from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
failures: list[str] = []

required = [
    ROOT / "AGENTS.md",
    ROOT / ".github" / "agents" / "rca-orchestrator.agent.md",
    ROOT / "schemas" / "agent-review.schema.json",
    ROOT / "config" / "confidence-rules.yml",
]
for path in required:
    if not path.exists():
        failures.append(f"arquivo obrigatório ausente: {path.relative_to(ROOT)}")

for skill in (ROOT / ".agents" / "skills").glob("*/SKILL.md"):
    text = skill.read_text(encoding="utf-8")
    if "[TODO" in text:
        failures.append(f"TODO de scaffold em {skill.relative_to(ROOT)}")
    if not re.match(r"^---\nname: [a-z0-9-]+\ndescription: .+\n---", text):
        failures.append(f"frontmatter inválido em {skill.relative_to(ROOT)}")

for path in (ROOT / "src" / "rca_agent").rglob("*.py"):
    source = path.read_text(encoding="utf-8")
    line_count = len(source.splitlines())
    if line_count > 400:
        failures.append(
            f"módulo monolítico: {path.relative_to(ROOT)} tem {line_count} linhas "
            "(limite 400)"
        )
    tree = ast.parse(source, filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        function_lines = (node.end_lineno or node.lineno) - node.lineno + 1
        if function_lines > 100:
            failures.append(
                f"função monolítica: {path.relative_to(ROOT)}::{node.name} "
                f"tem {function_lines} linhas (limite 100)"
            )

if failures:
    print("\n".join(f"ERRO: {item}" for item in failures))
    sys.exit(1)
print("Repository quality checks passed.")

