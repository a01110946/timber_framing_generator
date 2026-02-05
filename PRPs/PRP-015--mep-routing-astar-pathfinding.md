# PRP-015: MEP Routing A* Pathfinding

## Overview

**Feature**: A* pathfinding for single source-to-target MEP routing
**Branch**: `feature/mep-routing-phase5-astar`
**Issue**: #33 - MEP Routing Solver: OAHS Implementation Plan (Phase 5)

## Problem Statement

After MST determines the overall routing topology, A* pathfinding computes
the actual path for each source-target pair. This phase implements:

1. **A* Algorithm**: Optimal single-path finding with weighted edges
2. **Obstacle-Aware Heuristic**: Admissible heuristic considering obstacles
3. **Cross-Domain Routing**: Paths that traverse multiple routing domains
4. **Path Reconstruction**: Convert node sequence to RouteSegments

## Background: A* Algorithm

A* finds the shortest path from source to target using:
- `g(n)`: Cost from start to node n (exact)
- `h(n)`: Estimated cost from n to goal (heuristic)
- `f(n) = g(n) + h(n)`: Priority for node selection

For admissibility (guaranteed optimality), h(n) must never overestimate
the true cost. Manhattan distance is admissible for rectilinear routing.

## Solution Design

### 1. AStarPathfinder Class

```python
class AStarPathfinder:
    """
    A* pathfinding for MEP routing.

    Finds optimal paths through routing graphs considering:
    - Edge weights (base cost + penetration penalties)
    - Cross-domain transitions
    - Occupancy conflicts
    """

    def __init__(
        self,
        graph: nx.Graph,
        heuristic: Optional[Callable] = None
    ):
        self.graph = graph
        self.heuristic = heuristic or self._manhattan_heuristic

    def find_path(
        self,
        source: int,
        target: int,
        blocked_nodes: Optional[Set[int]] = None
    ) -> Optional[List[int]]:
        """Find optimal path from source to target."""

    def find_path_with_cost(
        self,
        source: int,
        target: int
    ) -> Tuple[Optional[List[int]], float]:
        """Find path and return total cost."""
```

### 2. PathReconstructor Class

```python
class PathReconstructor:
    """
    Converts node paths to RouteSegments.

    Handles:
    - Coordinate extraction from graph nodes
    - Direction assignment
    - Domain transitions
    """

    def __init__(self, graph: nx.Graph):
        self.graph = graph

    def reconstruct(
        self,
        node_path: List[int],
        route_id: str,
        system_type: str
    ) -> Route:
        """Convert node sequence to Route with segments."""

    def extract_transitions(
        self,
        node_path: List[int]
    ) -> List[Tuple[str, str]]:
        """Extract domain transitions from path."""
```

### 3. MultiDomainPathfinder Class

```python
class MultiDomainPathfinder:
    """
    Pathfinding across multiple routing domains.

    Uses the unified graph to find paths that may cross
    wall-to-floor or wall-to-wall transitions.
    """

    def __init__(self, mdg: MultiDomainGraph):
        self.mdg = mdg
        self._pathfinder: Optional[AStarPathfinder] = None

    def find_path(
        self,
        source_domain: str,
        source_location: Tuple[float, float],
        target_domain: str,
        target_location: Tuple[float, float]
    ) -> Optional[Route]:
        """Find path between points in different domains."""

    def find_nearest_node(
        self,
        domain_id: str,
        location: Tuple[float, float]
    ) -> Optional[int]:
        """Find graph node nearest to a location."""
```

## File Structure

```
src/timber_framing_generator/mep/routing/
    __init__.py              # Add new exports
    pathfinding.py           # AStarPathfinder, PathReconstructor
    multi_domain_pathfinder.py  # MultiDomainPathfinder

tests/mep/routing/
    test_pathfinding.py      # Unit tests
```

## Implementation Steps

### Step 1: A* Core Algorithm
- Priority queue implementation
- Path reconstruction
- Cost tracking

### Step 2: Heuristics
- Manhattan distance heuristic
- Domain-aware heuristic
- Transition cost estimation

### Step 3: Path Reconstruction
- Node path to coordinates
- RouteSegment creation
- Direction assignment

### Step 4: Multi-Domain Support
- Unified graph pathfinding
- Transition handling
- Domain boundary crossing

### Step 5: Tests
- Single domain paths
- Cross-domain paths
- Obstacle avoidance
- Edge cases

## Algorithm Details

### A* Implementation

```python
def find_path(self, source: int, target: int) -> Optional[List[int]]:
    # Priority queue: (f_score, g_score, node, path)
    open_set = [(0, 0, source, [source])]
    g_scores = {source: 0}
    visited = set()

    while open_set:
        f, g, current, path = heapq.heappop(open_set)

        if current == target:
            return path

        if current in visited:
            continue
        visited.add(current)

        for neighbor in self.graph.neighbors(current):
            if neighbor in visited:
                continue

            edge_cost = self.graph[current][neighbor].get('weight', 1.0)
            tentative_g = g + edge_cost

            if tentative_g < g_scores.get(neighbor, float('inf')):
                g_scores[neighbor] = tentative_g
                h = self.heuristic(neighbor, target)
                f = tentative_g + h
                heapq.heappush(open_set, (f, tentative_g, neighbor, path + [neighbor]))

    return None  # No path found
```

### Heuristic Functions

| Heuristic | Formula | Properties |
|-----------|---------|------------|
| Manhattan | `|x1-x2| + |y1-y2|` | Admissible, consistent |
| Weighted Manhattan | `w × (|x1-x2| + |y1-y2|)` | Admissible if w ≤ 1 |
| Zero | `0` | Admissible (degrades to Dijkstra) |

## Test Cases

### Single Domain
1. Direct path - no obstacles
2. Path around obstacle
3. Path through penetration (high cost)
4. No path exists (blocked)

### Cross-Domain
1. Wall-to-floor path
2. Wall-to-wall via corner
3. Multi-hop transitions

### Edge Cases
1. Source equals target
2. Unreachable target
3. Single node graph
4. Disconnected components

## Exit Criteria

- [ ] A* algorithm implementation
- [ ] Admissible heuristic
- [ ] Path reconstruction to RouteSegments
- [ ] Multi-domain pathfinding
- [ ] All unit tests passing
- [ ] Integration with Phase 4 (HananMST)

## Dependencies

- Phase 3: Graph construction (MultiDomainGraph)
- Phase 4: Route segment structures
- networkx (for graph operations)
