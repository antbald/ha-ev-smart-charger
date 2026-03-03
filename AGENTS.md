# AGENTS.md instructions for /Users/antoniobaldassarre/ha-ev-smart-charger

## Repo Context

This repository is a Home Assistant custom integration. Work in this repo should default to Home Assistant-specific guidance instead of generic Python advice.

## Skills

A skill is a set of local instructions stored in a `SKILL.md` file.

### Available repo-local skills

- home-assistant-custom-integration: Example scaffolding and checklists for developing Home Assistant custom integrations. Use when building, reviewing, or refactoring this integration. (file: /Users/antoniobaldassarre/ha-ev-smart-charger/.agents/skills/home-assistant-custom-integration/SKILL.md)
- home-assistant-best-practices: Best practices for Home Assistant automations, helpers, scripts, and device controls. Use when decisions involve entities, helpers, triggers, conditions, templates, device controls, or safe refactors. (file: /Users/antoniobaldassarre/ha-ev-smart-charger/.agents/skills/home-assistant-best-practices/SKILL.md)
- home-assistant-automation-scripts: Home Assistant automations, scripts, and blueprints. Use when the task involves automation/script syntax, triggers, conditions, actions, blueprint usage, automation modes, or troubleshooting automation behavior. (file: /Users/antoniobaldassarre/ha-ev-smart-charger/.agents/skills/home-assistant-automation-scripts/SKILL.md)

## Default Skill Policy For This Repo

- For implementation, debugging, review, and refactoring work in this repository, use `home-assistant-custom-integration` by default.
- Also use `home-assistant-best-practices` by default for any change that touches Home Assistant entities, helpers, services, templates, triggers, or configuration semantics.
- Additionally use `home-assistant-automation-scripts` when the task involves automations, scripts, blueprints, YAML examples, or automation logic.
- Use the minimal set of these skills that covers the task, but do not skip them for Home Assistant-related work in this repo.

## How To Use These Skills

- Open the relevant `SKILL.md` file and read only enough to follow the workflow.
- Resolve any relative paths mentioned by a skill relative to that skill's directory.
- If a skill references `references/`, load only the specific reference files needed for the task.
- Prefer the repo-local skill copies under `.agents/skills` for this project.
