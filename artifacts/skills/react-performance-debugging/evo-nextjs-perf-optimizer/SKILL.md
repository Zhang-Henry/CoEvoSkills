---
name: evo-nextjs-perf-optimizer
description: "Diagnose and fix common Next.js/React performance issues: sequential API fetches, excessive re-rendering, and bundle bloat. Use when a Next.js app has slow page loads, slow API routes, or sluggish UI interactions."
---

# Next.js Performance Optimizer

This skill fixes three categories of performance problems in Next.js applications:

1. **Sequential API fetches** → Parallel with `Promise.all` + fire-and-forget for non-critical ops
2. **Excessive React re-rendering** → `memo`, `useCallback`, `useMemo`
3. **Bundle bloat** → Direct imports instead of barrel imports + `next/dynamic` for code splitting

## Quick Start

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-nextjs-perf-optimizer/scripts')
from optimizer import run_optimization, validate_optimization

run_optimization('/app')
validate_optimization('/app')
```

## Optimizations Applied

### 1. Server-Side Fetch Parallelization (page.tsx, API routes)

**Problem**: Sequential `await` calls for independent data sources.
**Fix**: Use `Promise.all` for independent fetches.

```typescript
// BEFORE: 400 + 500 + 300 = 1200ms
const user = await fetchUser();
const products = await fetchProducts();
const reviews = await fetchReviews();

// AFTER: max(400, 500, 300) = 500ms
const [user, products, reviews] = await Promise.all([
  fetchUser(), fetchProducts(), fetchReviews()
]);
```

### 2. Dependent Fetch Chaining (checkout route)

When one fetch depends on another, chain the dependent off the prerequisite while running independent fetches in parallel:

```typescript
const userPromise = fetchUser();
const configPromise = fetchConfig();
const profilePromise = userPromise.then(user => fetchProfile(user.id));
const [user, config, profile] = await Promise.all([userPromise, configPromise, profilePromise]);
```

### 3. Fire-and-Forget for Non-Critical Operations

```typescript
// Don't await analytics - it's not needed for the response
logAnalytics(data);
```

### 4. React.memo + useCallback + useMemo

- Wrap list item components in `memo()` to prevent unnecessary re-renders
- Stabilize callbacks with `useCallback` (empty deps + functional updater)
- Pre-compute expensive derived data with `useMemo` (lookup maps, filter/sort chains)

### 5. Direct Lodash Imports

```typescript
// BEFORE: pulls entire lodash library
import { sortBy } from 'lodash';

// AFTER: loads only sortBy function
import sortBy from 'lodash/sortBy';
```

### 6. Dynamic Import for Heavy Components

Extract heavy component to separate file, use `next/dynamic`:
```typescript
const HeavyComponent = dynamic(() => import('@/components/HeavyComponent'), {
  loading: () => <div>Loading...</div>
});
```

## Key Constraints

- Never remove `data-testid` attributes
- Never remove `performance.mark()` calls
- Preserve all existing functionality
