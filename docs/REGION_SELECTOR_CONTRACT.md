# IBL region selector contract v1

`ibl-region-selector` defines the shared behavior of the Allen, Beryl, and Cosmos
region selector. It is a renderer-independent interaction contract: consumers
provide a finite ordered region inventory and state, apply explicit actions, and
compare the resulting state with the reviewed traces in the packaged
`region_selector_contract/v1/` resources. The contract does not prescribe a UI
framework or add runtime dependencies.

The v1 bundle contains `schema.json`, `traces.json`, and `manifest.json`. The
manifest records SHA-256 for the schema and traces; it does not hash itself.
Consumers should record the source repository revision separately from those
stable bundle hashes. `ibl_anatomy.region_selector_contract` loads the bundled
resources through `importlib.resources`; its sync command copies or checks a
bundle between explicit source and destination paths.

## Input model

A catalog is an ordered array of regions. `id` is the stable consumer identity;
`parentId` is null or references another region. Parent links must be acyclic.
`atlasId` is the signed Allen region identity, while `acronym` and `name` are
display and search strings. Left-hemisphere identities may be negative; the
string `id` preserves the consumer identity exactly. `mappingMember` defaults to true in application
adapters; when false, a region remains visible/searchable but cannot be
selected for region mapping. Branch status is derived from whether a region has
children in the active anatomical hierarchy.

The initial state includes a query, collapsed branch IDs, ordered selected IDs,
requested order (`anatomy`, `value-asc`, or `value-desc`), multiple-selection
mode, focus and range anchor IDs, and regional values. A missing or null value
is unavailable. Non-finite values are unavailable and sort after finite values.
Values affect ranked order only; they do not change identity or membership.

## Search and hierarchy

Search trims surrounding query whitespace. A blank query matches every region.
Otherwise, a region matches when the query occurs in its acronym or name after
case-insensitive Unicode default lowercasing (ECMAScript `toLowerCase`, without
a locale argument). Matching does not remove diacritics, normalize Unicode, or
use full case folding. Lowercase mappings that expand to multiple code points
are preserved; for example, `İ` lowers to `i` followed by COMBINING DOT ABOVE.
The query trim follows ECMAScript `String.trim` whitespace, including U+FEFF and
excluding U+0085. Search retains each matching region, its ancestors, and the
descendants of any matching region. Ancestors needed to reach a match are forced
open for that query. Search uses a temporary collapse state: entering a new
nonblank query starts with unrelated branches collapsed, and clearing the query
restores the user's ordinary collapse state. A changed nonblank query starts a
new temporary collapse state. Search temporarily uses anatomical order and
restores the requested value order when cleared.

Visible IDs are the retained rows in display order after applying collapsed
ancestors. A collapsed branch remains visible as a disclosure row; its descendants
are hidden. In anatomical order, rows follow catalog sibling order in depth-first
hierarchy order. In ranked order, only mapping-member leaves are shown, as a
flat list. Finite values sort first, ascending or descending as requested;
equal or unavailable values retain catalog order. Ranked rows retain their
original parent identities for range-selection eligibility.

## Selection and focus

Selected IDs are an ordered sequence. External selection updates preserve the
provided sequence. Activation of a mapping-member leaf toggles membership when Ctrl/Cmd is held,
multiple mode is enabled, or the leaf is already selected. Otherwise it replaces
selection. This means an ordinary click adds an unselected leaf in multiple mode,
and removes an already selected leaf in either mode. A non-mapping member
cannot be selected. Activating a branch changes its expansion state instead of
selecting it. Activation sets the
selection anchor for a leaf selection; a range activation leaves the anchor in
place.

Shift activation selects the visible mapping-member leaf siblings between the
anchor and target, inclusive, in current display order. Both must share the same
non-null parent and be visible. Range selection adds to the existing ordered
selection, appending newly selected IDs in range order. An invalid range has no
effect. In single-selection mode a range action is still additive, matching the
selector's explicit range gesture.

Focus is the region row receiving tree keyboard focus. Arrow Up/Down and Home/
End move through visible rows. In anatomical order, Right expands a collapsed
branch or focuses its first visible child; Left collapses an expanded branch or
focuses its parent. In value order, horizontal arrows do not change focus.
Enter and Space activate the focused row. Shift with keyboard activation follows ordinary activation rather than pointer range selection. Activation of a hidden row is ignored, including stale input from a previous projection. When query, collapse, or order changes
hide the focused row, focus moves to the first visible row. If there is no visible row, the previous focus is retained.
A direct focus action sets focus explicitly; activation alone does not move it.

Hover is nullable and may refer to a branch or leaf. It describes pointer/focus
hover supplied by the UI. Only visible mapping-member rows can receive hover. Hiding a hovered row through search, folding or projection clears hover; a null hover action clears it explicitly. A null focus target ignores navigation until focus returns to a visible row.

## Conformance

`traces.json` is the normative executable example set. Each scenario gives its
ordered catalog, initial state, sequence of actions, and the expected snapshot
after every action. Set-like snapshot arrays (`matches`, `retained`, and
`expanded`) use catalog order; `visible` uses current display order; `selected`
retains selection order. `requestedOrder` records the user's order preference;
`order` is effective order after temporary search behavior.

Consumers must validate the document against `schema.json`, then run every
scenario without reordering inputs or expected values. Trace additions are
reviewed examples; generated outputs must not be accepted as expected results
without independent semantic review. This package provides data and a loader,
not a selector runtime.
