# ai-legal-claude Skill Integration

This folder vendors the legal skill prompts and supporting agent instructions
from:

https://github.com/zubair-trabzada/ai-legal-claude

The Ask AI engine loads these `SKILL.md` files at runtime and injects the
matching skill instructions into the model prompt for legal workflows such as
contract review, clause risk analysis, plain-English explanation, compliance
review, negotiation, and missing-protection checks.

The integration is prompt-native: Ask AI does not install Claude Code commands.
Instead, it uses these upstream skill instructions as workflow guidance inside
the local browser app.
