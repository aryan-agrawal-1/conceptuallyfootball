# Editorial visual blocks

Visual blocks are structured article content, not embeds. Writers insert them from the editor's **Add visual** action or the existing `/` command menu; there is no separate keyboard shortcut to learn. `/chart`, `/radar`, `/compare`, and related searches narrow the same command menu.

## Configuration contract

Every block stores:

- the visual type and chart type;
- canonical player or team IDs plus the source competition-season for subject-led blocks (custom charts operate on their saved cohort instead);
- the competition or comparison scope (`league`, `BIG5`, or `ALL`) and its season;
- ordered metric keys (X then Y for scatter charts), rate mode, minimum-minutes and team/position filters;
- chart presentation choices such as labels, trend lines, ranking direction and bar count;
- title, caption, required alt text, source note, and data as-of date; and
- an update policy.

This is enough to recreate the intended query and presentation without copying an internal URL or relying on the writer's current site scope.

## Live and frozen behaviour

New blocks use `live_draft_freeze_on_publish`:

1. While an article is a draft or private preview, the block reads current data for its saved configuration. Missing data produces an in-context warning; an as-of date older than 32 days is flagged for re-checking.
2. The publishing workflow must resolve the live block once and persist its rendered data snapshot before changing the article to published. The block then uses the `frozen` policy so the published claim cannot drift after approval.
3. A later explicit editorial refresh creates a new article revision and a new snapshot rather than silently changing the published visual.

All initial chart renderers are SVG or semantic HTML. Exporters should prefer that static renderer and use the saved alt text/configuration as the fallback when data cannot be resolved. Interactive hover detail is an enhancement; the chart remains readable and exportable without it.
