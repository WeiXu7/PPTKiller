# Architecture Visuals Design

## Goal

Improve PPT content depth by letting the Agent choose visual structure when text is weaker than a diagram, especially for technical concepts, systems, frameworks, and workflows.

## Design

Add an `architecture` slide layout. The layout carries editable diagram data rather than a generated bitmap: `diagram_title`, `diagram_nodes`, `diagram_edges`, `diagram_layers`, and `visual_rationale`.

The Agent should prefer this layout for technical architecture, concept frameworks, capability maps, data flows, governance frameworks, and Agent workflows. It should keep searched or uploaded image layouts for scenes, products, cases, people, and other content where a real image communicates better. AI image generation is intentionally out of scope.

The PPT exporter renders architecture diagrams with native PPT shapes so exported decks remain editable. The Python fallback renders a simpler version so export previews remain useful when the professional Node engine is unavailable.

## Acceptance

- Technical framework fallback outlines include at least one architecture slide.
- Architecture slides are not flagged as missing images.
- Node export script supports `layout: "architecture"`.
- Frontend editor can select the architecture layout.
