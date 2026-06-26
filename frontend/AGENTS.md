# Prototype Instructions

Run the local server yourself and open the preview in the in-app browser. Do not give the user server-start instructions when you can run it.

Before making substantial visual changes, use the Product Design plugin's `get-context` skill when the visual source is unclear or no longer matches the current goal. When the user gives durable prototype-specific design feedback, preferences, or decisions, record them in `AGENTS.md`.

When implementing from a selected generated mock, treat that image as the source of truth for layout, component anatomy, density, spacing, color, typography, visible content, and hierarchy.

## Durable product decisions

- Preserve the selected three-pane Agent execution workspace as the primary authenticated view.
- User-facing workflow data must come from the FastAPI service; do not reintroduce fabricated research counts or fake verification states.
- Keep human approval gates visible and explicit before PPTX export.
