---
name: analysis-cost-report
description: BSGateway cost analysis skill for generating usage and cost reports
version: 1.0.0
task_types: [analysis, reporting]
executor: claude_code
required_tools: [Read, Bash, Grep]
---

# Cost Report Analysis Skill

Generates cost analysis reports for BSGateway API usage. Analyzes token consumption, model costs, and usage patterns across projects and time periods.

## When to Use

- Generating periodic cost reports
- Analyzing API usage patterns
- Comparing cost across models or projects
- Identifying cost optimization opportunities
