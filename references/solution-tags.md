# Solution Tags

Use these tags for contest README entries. Infer tags from the submitted solution code, not only from the problem statement, Codeforces tags, or solved.ac tags.

The allowed README tags are the values in `references/solvedac-tag-map.json`. Use that JSON as the source of truth; solved.ac keys may be converted through the map, but tags outside the map must not be invented or written.

## Format

- Use English tag names.
- Use `Title_Case` with underscores for multi-word tags.
- Keep common acronyms uppercase, for example `DP`, `BFS`, `DFS`, `DSU`, `LCA`, `MST`, `SCC`, and `FFT`.
- Use only tag names that appear as values in `references/solvedac-tag-map.json`.
- Separate multiple tags with `, `.
- Prefer 1 to 5 tags per solution.
- Order tags by importance: main technique first, supporting techniques after.

Examples:

```text
Math, Greedy
DP, Prefix_Sum
Bruteforce, Sorting, Greedy, Bit_Mask
```

If the code does not provide enough evidence to infer tags confidently, ask the user before updating the README.

## Common Tags

Prefer broad tags unless a specific tag materially explains the implementation.

General:

- `Implementation`
- `Case_Work`
- `Ad_Hoc`
- `Simulation`
- `Constructive`
- `Bruteforce`
- `Greedy`
- `Sorting`
- `Sweeping`
- `Binary_Search`
- `Parametric_Search`
- `Two_Pointers`
- `Sliding_Window`
- `Prefix_Sum`
- `Difference_Array`
- `Coordinate_Compression`
- `Offline_Queries`

Math:

- `Math`
- `Number_Theory`
- `Sieve`
- `Prime_Factorization`
- `Modular_Inverse`
- `Combinatorics`
- `Probability`
- `Game_Theory`
- `Geometry`
- `Linear_Algebra`
- `FFT`

Dynamic programming:

- `DP`
- `Tree_DP`
- `Rerooting`
- `Bit_Mask`
- `Bitset`
- `Knapsack`
- `Digit_DP`
- `Deque_DP`
- `Divide_And_Conquer_Optimization`

Data structures:

- `Data_Structure`
- `Stack`
- `Queue`
- `Deque`
- `Priority_Queue`
- `Set`
- `Hash_Set`
- `Segment_Tree`
- `Lazy_Propagation`
- `Sparse_Table`
- `Sqrt_Decomposition`
- `Mo`

Graphs and trees:

- `Graph`
- `Tree`
- `Graph_Traversal`
- `DFS`
- `BFS`
- `0_1_BFS`
- `Dijkstra`
- `Floyd_Warshall`
- `Shortest_Path`
- `DSU`
- `MST`
- `Topological_Sort`
- `DAG`
- `SCC`
- `BCC`
- `LCA`
- `Euler_Tour`
- `Bipartite_Graph`
- `Bipartite_Matching`
- `Max_Flow`
- `Min_Cost_Max_Flow`
- `HLD`
- `Centroid_Decomposition`

Strings:

- `String`
- `Hashing`
- `Trie`
- `KMP`
- `Z_Function`
- `Manacher`
- `Aho_Corasick`
- `Suffix_Array`

## solved.ac Mapping

Use `references/solvedac-tag-map.json` for the full solved.ac key-to-README tag mapping. If a solved.ac-style key is not listed in the JSON, ask the user for a mapped tag instead of normalizing it yourself.

Common examples:

```text
dp -> DP
bruteforcing -> Bruteforce
ad_hoc -> Ad_Hoc
case_work -> Case_Work
bitmask -> Bit_Mask
prefix_sum -> Prefix_Sum
binary_search -> Binary_Search
disjoint_set -> DSU
segtree -> Segment_Tree
lazyprop -> Lazy_Propagation
mcmf -> Min_Cost_Max_Flow
aho_corasick -> Aho_Corasick
```

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
