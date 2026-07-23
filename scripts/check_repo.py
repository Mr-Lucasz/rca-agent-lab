from __future__ import annotations

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

if failures:
    print("\n".join(f"ERRO: {item}" for item in failures))
    sys.exit(1)
print("Repository quality checks passed.")

