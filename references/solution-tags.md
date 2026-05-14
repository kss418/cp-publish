# Solution Tags

Use these tags for contest README entries. Infer tags from the submitted solution code, not only from the problem statement or official Codeforces tags.

## Format

- Use English tag names.
- Use `Title_Case` with underscores for multi-word tags.
- Keep common acronyms uppercase, for example `DP`, `BFS`, `DFS`, `DSU`, `LCA`, `MST`, and `SCC`.
- Separate multiple tags with `, `.
- Prefer 1 to 5 tags per solution.
- Order tags by importance: main technique first, supporting techniques after.

Example:

```text
Math, Greedy
DP, Prefix_Sum
Bruteforce, Sorting, Greedy, Bit_Mask
```

If the code does not provide enough evidence to infer tags confidently, ask the user before updating the README.

## Canonical Tags

General:

- `Implementation`
- `Case_Work`
- `Ad_Hoc`
- `Simulation`
- `Constructive`
- `Bruteforce`
- `Greedy`
- `Sorting`
- `Binary_Search`
- `Two_Pointers`
- `Sliding_Window`
- `Prefix_Sum`
- `Difference_Array`

Math:

- `Math`
- `Number_Theory`
- `GCD`
- `Sieve`
- `Prime`
- `Combinatorics`
- `Probability`
- `Game_Theory`
- `Geometry`

Dynamic programming:

- `DP`
- `Bit_Mask`
- `Bitset`
- `Knapsack`

Data structures:

- `Data_Structure`
- `Stack`
- `Queue`
- `Deque`
- `Priority_Queue`
- `Set_Map`
- `Multiset`
- `Fenwick_Tree`
- `Segment_Tree`
- `Lazy_Propagation`
- `Sparse_Table`

Graphs and trees:

- `Graph`
- `Tree`
- `DFS`
- `BFS`
- `Dijkstra`
- `Floyd_Warshall`
- `DSU`
- `MST`
- `Topological_Sort`
- `SCC`
- `LCA`
- `Euler_Tour`

Strings:

- `String`
- `Hashing`
- `Trie`
- `KMP`
- `Z_Function`
- `Manacher`

## Inference Cues

Use `Case_Work` when the solution is mostly branching over small cases, parity, boundaries, or hand-enumerated conditions.

Use `Ad_Hoc` when the solution depends on a custom observation or direct construction that does not fit a standard algorithm tag.

Use `Math` when the core logic is formula manipulation, modular arithmetic, parity, inequalities, counting formulas, or number properties.

Use `Greedy` when the code repeatedly makes locally optimal choices, often after sorting or using a priority queue.

Use `DP` when the code stores transitions over states, memoizes recursion, or builds answer arrays/tables from previous states.

Use `Bruteforce` when the code intentionally enumerates all candidates in a bounded search space.

Use `Sorting` only when sorted order is central to the idea, not merely for output formatting.

Use `Binary_Search` when the solution searches the answer or an index using monotonicity.

Use `Two_Pointers` or `Sliding_Window` when the code maintains moving boundaries over an array/string.

Use `Prefix_Sum` or `Difference_Array` when cumulative arrays or range increment tricks are central.

Use graph/tree tags only when the input is graph-like or the solution builds graph relationships explicitly.

Use string tags only when the solution relies on string-specific algorithms or pattern structure.

When multiple tags are plausible, choose the smallest set that explains the implementation.
