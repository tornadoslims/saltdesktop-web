---
name: optimize
description: Analyze and optimize code performance
user-invocable: true
---
# Optimize Performance

Analyze and improve code performance:

1. Identify the target: specific function, module, or the whole project
2. Profile the code:
   - Python: `python -m cProfile` or `py-spy`
   - Node.js: `node --prof` or Chrome DevTools
   - General: measure execution time of key paths
3. Analyze bottlenecks:
   - Hot loops and O(n^2) algorithms
   - Unnecessary allocations or copies
   - Blocking I/O that could be async
   - N+1 query patterns in database access
   - Missing indexes for frequent queries
4. Apply optimizations:
   - Replace inefficient data structures (list -> set/dict for lookups)
   - Add caching where appropriate (functools.lru_cache, memoization)
   - Batch I/O operations
   - Use generators instead of materializing large lists
5. Benchmark before and after to verify improvement
6. Ensure tests still pass after changes
7. Document the optimization and its impact
