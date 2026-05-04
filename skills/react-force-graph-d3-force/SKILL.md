---
name: react-force-graph-d3-force
description: "react-force-graph d3Force semantics — modify built-in 'link'/'charge', don't replace. Replacing the link force breaks the canvas because the lib's id-resolution lives inside it."
version: 1.0.0
triggers:
  - pattern: "tuning react-force-graph forces (forceLink, forceManyBody, forceCollide), graph stops rendering after d3Force change, or 'No nodes to graph' / blank canvas after physics tuning"
---

# react-force-graph: d3Force is for modify, not replace

## The trap

`react-force-graph-2d` (and -3d) creates an internal d3
simulation with three default forces wired up at mount: `'charge'`,
`'link'`, and `'center'`. The library's id-resolution (turning
string `link.source` / `link.target` into node references) lives
**inside the link force instance** it created.

If you reach into the simulation and replace that force with a
fresh `forceLink(...)` from `d3-force`:

```tsx
// ❌ Wrong — graph never renders
import { forceLink } from "d3-force";

useEffect(() => {
  const fg = fgRef.current;
  fg.d3Force("link", forceLink(filteredData.links).distance(40));
}, [filteredData]);
```

…the canvas paints once with no edges, then stops repainting. Tests
that assert canvas dimensions or specific labels start failing in
bulk (8–10 of 12 in our case). Console is silent — no error.

## Fix — modify the existing force instance

Get the force, mutate its properties, return:

```tsx
useEffect(() => {
  const fg = fgRef.current as
    | { d3Force: (name: string, force?: unknown) => unknown }
    | null;
  if (!fg) return;

  // Modify built-ins
  const charge = fg.d3Force("charge") as
    | { strength: (s: number) => unknown; theta?: (t: number) => unknown }
    | undefined;
  if (charge) {
    charge.strength(-160);
    charge.theta?.(0.9);
  }
  const link = fg.d3Force("link") as
    | { distance: (d: number) => unknown; strength: (s: number) => unknown }
    | undefined;
  if (link) {
    link.distance(40);
    link.strength(0.4);
  }

  // Adding *new* forces is fine — only replacement of built-ins breaks
  fg.d3Force("collide", forceCollide().radius(/* … */).iterations(1));
}, [filteredData, /* deps */]);
```

The `react-force-graph` ref's `d3Force(name)` (single arg) returns
the existing force. `d3Force(name, force)` (two args) replaces it.
Use the single-arg form for built-ins and only call the two-arg
form for forces you're adding (`'collide'`, custom `'cluster'`,
etc.).

## Custom 'cluster' force pattern (community attraction)

When the backend already has community detection (Louvain etc.),
nudge same-community nodes together with a custom alpha-aware
function — cheap and visually effective:

```tsx
const clusterForce = (alpha: number) => {
  if (communities.length === 0 || !filteredData) return;
  const centroids = computeCommunityCentroids(filteredData.nodes, communities);
  const strength = 0.05 * alpha; // alpha decays — keeps cooldown smooth
  for (const n of filteredData.nodes) {
    const cid = nodeCommunityIdMap.get(n.id);
    if (cid === undefined || n.x === undefined) continue;
    const c = centroids.get(cid);
    if (!c) continue;
    n.vx = (n.vx ?? 0) + (c.x - n.x) * strength;
    n.vy = (n.vy ?? 0) + (c.y - n.y) * strength;
  }
};
fg.d3Force("cluster", clusterForce);
```

A bare function is a valid d3 force — d3 calls it once per tick
with the current alpha.

## Diagnosis

If you tweaked physics and the graph stopped rendering:

1. Check whether you used `fg.d3Force("link", forceLink(...))` (two
   args, replacement) — that's almost certainly the cause.
2. Restore by removing that line; if the graph repaints, you've
   confirmed it.
3. Switch to the single-arg getter + property mutation pattern.

## What about `nodeId` accessor?

You don't need it when the built-in link force is intact. It auto-
resolves string ids against `nodes[].id`. If you do replace the
link force (rarely a good idea), then yes — `forceLink(...).id(d => d.id)`
mirrors the built-in's behavior. But again: don't.

## See also

- The cooldown / damping defaults (`d3VelocityDecay`,
  `cooldownTicks`, `warmupTicks`) are props on the component — not
  forces. Tune those for stability separately:

  ```tsx
  <ForceGraph2D
    d3VelocityDecay={0.4}   // 0.3 default oscillates with collide
    warmupTicks={60}
    cooldownTicks={120}
  />
  ```

- `forceCollide` is O(n²) per iteration. For 1000+ nodes set
  `iterations: 1` to keep frame rate.
