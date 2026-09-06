# Story Audio UI/UX Review

A project-local advisory procedure for visible frontend work. It complements the
six CADS core playbooks; it is not a seventh core playbook and creates no
lifecycle state.

## When to use

Use this procedure whenever the active Goal exposes a visible layout, typography,
wrapping, density, responsive, accessibility, or interaction defect. For a
user-visible blocker, enter through CADS Systematic Debugging, use this procedure
to inspect and verify the surface, then resume the same Critical User Journey.

## 1. Start from the screen job

Before editing, state the one decision or task the screen must make easy. Identify
primary information, primary action, supporting evidence, and secondary controls.
Do not optimize isolated components while the overall task flow remains awkward.

## 2. Inspect the rendered surface first

Use the real supported browser/runtime and the current acceptance fixture. Capture
or inspect the rendered desktop surface before changing code. When responsive
behavior matters, also inspect a narrow viewport. Prefer rendered evidence and DOM
geometry over assumptions from CSS alone.

For Story Audio owner-facing work, verify at least:

- the owner's current desktop viewport;
- a representative 1280-1440 px desktop width; and
- a narrow/mobile width when the changed surface is expected to reflow.

## 3. Content hierarchy and density

- Keep identity/status and the primary controls compact and close together.
- Put long read-only evidence in normal document flow below the compact control
  region unless the two sides have comparable height.
- Do not create tall equal-height sibling columns when one side is much shorter;
  large blank regions are a defect, not harmless whitespace.
- Long text must use the available line length. Avoid narrow text columns caused
  by inherited grid rules or generic descendant selectors.
- Independent evidence cards may use a responsive 2-column grid on wide screens,
  but each card's internal text remains full-width and readable. Collapse to one
  column when width becomes constrained.
- Prefer progressive disclosure for repeated evidence. The user must be able to
  identify the speaker without scrolling through unnecessary narrator samples.

## 4. Text integrity

Vietnamese UI text must be valid UTF-8 at source/runtime boundaries. If a legacy
mixed-encoding file makes literal edits unsafe, use stable Unicode escapes in the
smallest affected function rather than rewriting the whole file.

Before claiming a visible text fix:

- scan the changed surface for replacement characters and mojibake-like literals;
- check the served bundle, not only the working-tree file; and
- inspect the real rendered text in the acceptance fixture.

Do not treat a font change as a fix for corrupted source text.

## 5. CSS discipline

- Scope rules to semantic component classes. Avoid selectors such as
  `.component div` or `.details small` when nested content has different layout
  needs.
- Remove superseded rules when changing layout; do not stack competing layout
  versions.
- Keep one authoritative layout implementation per component.
- Verify wrapping, overflow, sticky positioning, and focus behavior in the real
  browser after each structural change.

## 6. Visual acceptance

A UI checkpoint is acceptable only when all of the following are true:

1. The changed surface is visually inspected in the real supported runtime.
2. No large unexplained blank region, clipped content, accidental narrow column,
   overlap, or horizontal overflow remains.
3. Primary controls remain discoverable without competing with supporting text.
4. Vietnamese labels and evidence render correctly.
5. Focused tests pass and the served asset identity is confirmed.
6. The same owner acceptance fixture can continue from the point where the defect
   was found.

Tests and screenshots are evidence. Owner real-use remains the final acceptance
oracle for this user-facing product.
