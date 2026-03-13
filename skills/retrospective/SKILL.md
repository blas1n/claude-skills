---
name: retrospective
description: "AUTO-TRIGGER at task completion when difficulty signals detected (wrong first approach, multiple failures, undocumented behavior). Extract insights from difficult work into reusable skills. Do NOT wait for user — execute immediately."
---

# Retrospective: Self-Evolution

Core question: **"What was difficult, and how was it overcome?"**

Convert hard-won experience into reusable skill assets.
Smooth work is NOT a target — only unexpected findings and post-failure discoveries qualify.

---

## Step 1: Review Conversation Flow

Look back at what was attempted in this conversation:

- What approach was tried first?
- Where did things get stuck?
- What was unexpected?

Use git as a supplementary source:
- `git log --oneline` from branch divergence point
- `git diff` for large change scopes

---

## Step 2: Extract Difficulties (Core)

Answer these questions:

1. **What was unexpected?** (assumption vs reality)
2. **Which assumptions were wrong?** (docs, prior knowledge, intuition)
3. **What was newly discovered?** (unexpected tool/framework/pattern behavior)
4. **Which approaches failed, and why?**
5. **What was the key insight of the final solution?**

---

## Step 3: Refine Insights

Criteria for deciding asset value:

> "Without this experience, would the same mistake be repeated next time?"

- **Yes** → Must be captured as a skill
- **Maybe** → Add as a case to an existing skill
- **No** → Not worth capturing (already known)

---

## Step 4: Determine Asset Type

| Type | Target | Location |
|------|--------|----------|
| New skill | Reproducible pattern/methodology | `~/.claude/claude-skills/skills/<name>/SKILL.md` |
| Skill update | Missing case/exception | Add section to existing skill file |
| Project knowledge | Project-specific matters | `.claude/CLAUDE.md` or project memory |

---

## Step 5: Create Skill File

Write new skill file based on skill-template.md:

1. Write to `~/.claude/claude-skills/skills/<slug>/SKILL.md`
2. **Do NOT commit** — host auto-commit poller handles this
3. After writing, briefly report to the user what insights were captured

---

## Skill Naming Rules

- Use kebab-case: `docker-dind-setup`, `playwright-web-e2e`
- Include specific tech/pattern name: `pydantic-settings-gotchas` (O), `config-tips` (X)
- Framework + problem domain: `fastapi-async-db-session`, `react-state-hydration`
