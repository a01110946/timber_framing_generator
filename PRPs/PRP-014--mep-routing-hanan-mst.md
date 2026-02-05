# PRP-014: MEP Routing Hanan Grid MST Algorithm

## Overview

**Feature**: Hanan Grid construction and Minimum Spanning Tree for MEP routing
**Branch**: `feature/mep-routing-phase4-hanan`
**Issue**: #33 - MEP Routing Solver: OAHS Implementation Plan (Phase 4)

## Problem Statement

The MEP routing solver needs to compute optimal multi-terminal routing using the
Hanan Grid approach. This phase implements:

1. **Hanan Grid Construction**: Generate grid from terminal coordinates
2. **Obstacle-Aware Filtering**: Remove blocked grid intersections
3. **MST Computation**: Find minimum spanning tree connecting terminals
4. **Steiner Point Pruning**: Remove unnecessary junction points
5. **Tree-to-Route Conversion**: Convert MST to directed flow paths

## Background: Hanan Grid

The Hanan Grid is formed by drawing horizontal and vertical lines through each
terminal point. For N terminals, this creates at most N² intersection points.
The Rectilinear Steiner Tree (RST) problem has an optimal solution that uses
only Hanan Grid points (Hanan's theorem).

```
Terminals: A(1,1), B(4,1), C(2,3)

    |   |   |
  3 +---C---+     Hanan intersections: 9 points
    |   |   |     Grid lines through x={1,2,4} and y={1,3}
  1 A---+---B
    1   2   4
```

## Solution Design

### 1. HananGrid Class

```python
@dataclass
class HananGrid:
    """
    Hanan Grid for rectilinear Steiner tree construction.

    Attributes:
        terminals: List of terminal points (x, y)
        x_coords: Sorted unique X coordinates
        y_coords: Sorted unique Y coordinates
        points: All grid intersection points
        blocked: Set of blocked point indices
    """
    terminals: List[Tuple[float, float]]
    x_coords: List[float]
    y_coords: List[float]
    points: List[Tuple[float, float]]
    blocked: Set[int]

    @classmethod
    def from_terminals(
        cls,
        terminals: List[Tuple[float, float]],
        obstacles: Optional[List[Obstacle]] = None
    ) -> 'HananGrid':
        """Construct Hanan grid from terminal points."""

    def get_neighbors(self, point_idx: int) -> List[int]:
        """Get adjacent grid points (up, down, left, right)."""

    def get_edge_cost(
        self,
        from_idx: int,
        to_idx: int,
        cost_map: Optional[Dict] = None
    ) -> float:
        """Get edge cost between adjacent points."""
```

### 2. HananMST Class

```python
class HananMST:
    """
    Minimum Spanning Tree computation on Hanan Grid.

    Uses Kruskal's algorithm with Union-Find for efficiency.
    """

    def __init__(self, grid: HananGrid):
        self.grid = grid
        self._parent: Dict[int, int] = {}
        self._rank: Dict[int, int] = {}

    def compute_mst(
        self,
        terminal_indices: List[int],
        cost_map: Optional[Dict] = None
    ) -> List[Tuple[int, int, float]]:
        """
        Compute MST connecting terminal points.

        Returns:
            List of (from_idx, to_idx, cost) edges
        """

    def _find(self, x: int) -> int:
        """Union-Find: find with path compression."""

    def _union(self, x: int, y: int) -> bool:
        """Union-Find: union by rank."""
```

### 3. SteinerTreeBuilder Class

```python
class SteinerTreeBuilder:
    """
    Builds Steiner trees from Hanan Grid MST.

    Handles:
    - Steiner point identification
    - Unnecessary point pruning
    - Tree-to-route conversion
    """

    def __init__(self, grid: HananGrid, mst_edges: List[Tuple[int, int, float]]):
        self.grid = grid
        self.mst_edges = mst_edges

    def prune_steiner_points(self) -> List[Tuple[int, int, float]]:
        """Remove degree-2 Steiner points (pass-through nodes)."""

    def to_route_segments(
        self,
        source_idx: int
    ) -> List[RouteSegment]:
        """Convert tree to directed route segments from source."""

    def get_steiner_points(self) -> List[Tuple[float, float]]:
        """Get coordinates of Steiner points (non-terminal junctions)."""
```

### 4. RouteSegment Dataclass

```python
@dataclass
class RouteSegment:
    """
    A single segment in an MEP route.

    Attributes:
        start: Start point (x, y)
        end: End point (x, y)
        direction: 'horizontal' or 'vertical'
        length: Segment length
        cost: Routing cost (includes penetrations)
        is_steiner: Whether this connects to a Steiner point
    """
    start: Tuple[float, float]
    end: Tuple[float, float]
    direction: str
    length: float
    cost: float
    is_steiner: bool = False
```

## File Structure

```
src/timber_framing_generator/mep/routing/
    __init__.py              # Add new exports
    hanan_grid.py            # HananGrid, HananMST, SteinerTreeBuilder
    route_segment.py         # RouteSegment dataclass

tests/mep/routing/
    test_hanan_grid.py       # Unit tests
```

## Implementation Steps

### Step 1: Core Data Structures
- RouteSegment dataclass
- HananGrid construction from terminals

### Step 2: Obstacle-Aware Filtering
- Mark blocked intersections
- Handle partial blockages (high cost vs blocked)

### Step 3: MST Algorithm
- Kruskal's with Union-Find
- Edge cost computation

### Step 4: Steiner Point Handling
- Identify Steiner vs terminal points
- Prune unnecessary junctions

### Step 5: Tree-to-Route Conversion
- BFS/DFS from source
- Assign directions
- Generate RouteSegment list

### Step 6: Tests
- Grid construction tests
- MST computation tests
- Pruning tests
- Integration tests

## Algorithm Details

### Kruskal's MST Algorithm

```
1. Create edge list with costs
2. Sort edges by cost (ascending)
3. Initialize Union-Find with each point as separate set
4. For each edge (u, v, cost) in sorted order:
   a. If find(u) != find(v):  # Different components
      - Add edge to MST
      - union(u, v)
5. Stop when all terminals connected
```

### Steiner Point Pruning

```
1. Build adjacency from MST edges
2. Identify terminal nodes
3. For each non-terminal node with degree 2:
   a. If neighbors are collinear:
      - Remove node, connect neighbors directly
4. Repeat until no more prunable nodes
```

### Tree-to-Route Conversion (BFS)

```
1. Start BFS from source terminal
2. For each node:
   a. Record direction from parent
   b. Add children to queue
3. Convert parent-child pairs to RouteSegments
```

## Edge Cost Calculation

| Edge Type | Cost Formula |
|-----------|--------------|
| Clear path | Manhattan distance |
| Through stud | distance × 5.0 |
| Through joist | distance × 3.0 |
| Blocked | infinity (not traversable) |

## Test Cases

### Grid Construction
1. Two terminals - simple 4-point grid
2. Three collinear terminals - line grid
3. Four corner terminals - 16-point grid
4. Duplicate coordinates - deduplicated grid

### MST Computation
1. Two terminals - single edge
2. Three terminals L-shape - 2 edges
3. Square terminals - 3 edges (not 4)
4. With obstacles - path around

### Pruning
1. No Steiner points - unchanged
2. Single pass-through - removed
3. Junction point - kept
4. Multiple prunable - all removed

### Integration
1. Single domain routing
2. Cost-weighted routing
3. Obstacle avoidance

## Exit Criteria

- [ ] HananGrid construction from terminals
- [ ] Obstacle marking in grid
- [ ] MST computation with Kruskal's
- [ ] Steiner point pruning
- [ ] Tree-to-route conversion
- [ ] Unit tests passing
- [ ] Integration with MultiDomainGraph

## Dependencies

- Phase 1: Core structures (Obstacle, Point2D)
- Phase 3: Graph construction (for cost maps)
- networkx (optional, for validation)
