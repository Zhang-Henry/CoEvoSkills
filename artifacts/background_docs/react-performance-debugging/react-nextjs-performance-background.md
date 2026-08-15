# React and Next.js Performance Optimization

This document provides background on common performance problems in React and Next.js applications, focusing on three categories of issues: server-side data fetching inefficiencies, excessive client-side re-rendering, and JavaScript bundle bloat.

## Sequential vs. Parallel Asynchronous Data Fetching

When a server component or API route handler needs data from multiple independent sources, the order in which those requests are dispatched has a direct impact on total response time.

**Sequential (waterfall) fetching** occurs when each asynchronous call must
resolve before the next one begins. For independent calls with latencies
`a`, `b`, and `c`, sequential execution takes approximately `a + b + c`.
This pattern emerges naturally when developers write a series of awaited
statements one after another. Each line blocks until its promise resolves,
preventing subsequent fetches from starting.

**Parallel fetching** dispatches all independent requests simultaneously using
concurrent promise resolution. Ignoring shared overhead, independent calls then
complete in approximately `max(a, b, c)`. The key insight is that invoking all
three functions immediately creates three in-flight promises, and waiting for
all of them to settle means the total wall-clock time follows the slowest call
rather than the sum.

However, not all fetches are truly independent. When one call depends on the result of another (for example, fetching a user profile requires the user ID returned by a prior authentication call), the dependent call cannot be parallelized with its prerequisite. The correct strategy is to start the prerequisite and all independent calls concurrently, then chain the dependent call off the prerequisite's result:

Start the user fetch and config fetch concurrently by initiating their promises immediately. Then chain the profile fetch off the user promise so it starts as soon as the user result is available. Finally, await all three promises together and destructure the results. This pattern ensures that the config fetch runs concurrently with the user fetch, and the profile fetch starts as soon as the user result is available, without waiting for config. The total time is the maximum of (user fetch duration + profile fetch duration) and config fetch duration.

### Critical-path budgeting and response contracts

Represent asynchronous work as a dependency graph and calculate the longest
dependency chain after parallelization.  `Promise.all` cannot shorten a genuine
prerequisite chain; framework startup, serialization, connection setup, and
scheduling add further end-to-end overhead.  Measure the complete route more
than once and distinguish cold-start overhead from steady-state service time.

If the critical path is still too long, inspect the response contract and its
consumers.  Data required for correctness must remain on the critical path.
Optional enrichment that is not part of the contract may be deferred, fetched
by a later endpoint, or scheduled as non-blocking work with explicit failure
handling.  Other legitimate architectural remedies include a batched upstream
API or changing an upstream response so a dependent lookup is unnecessary.
Do not hard-code an identifier, fabricate a response field, or remove required
data merely to make a timing check pass.

## Fire-and-Forget for Non-Critical Operations

Some operations like analytics logging or telemetry are side effects that do not produce data needed by the response. Awaiting these calls adds their latency to the request path for no benefit to the user.

The fire-and-forget pattern calls the async function but does not await its result. In JavaScript/TypeScript, invoking the operation without assigning or awaiting the returned promise starts the operation in the background. The response can be sent immediately.

This is safe only when the caller genuinely does not need the result and when a failure in the background operation is acceptable (for example, a dropped analytics event is not user-facing). Operations that affect correctness (like writing to a database that the response depends on) must still be awaited.

## React Component Re-rendering and Memoization

React re-renders a component whenever its parent re-renders, even if the child's props have not changed. In a list of many items, a state change in the parent (such as updating a shopping cart counter) triggers a re-render of every child in the list. If the list has 50 items, a single cart addition causes 50 re-renders, most of which produce identical output.

### React.memo

React.memo is a higher-order component that wraps a function component and performs a shallow comparison of its props before re-rendering. If all props are referentially equal to the previous render, the wrapped component skips rendering entirely. This is the primary tool for preventing unnecessary re-renders of list items.

For React.memo to be effective, the props passed to the memoized component must be **referentially stable** across renders. If a parent creates new object or function references on every render, the shallow comparison will always find differences and memoization will have no effect.

### useCallback

The useCallback hook returns a memoized version of a callback function that only changes when one of the dependencies changes. Without useCallback, a function defined inside a component body (like an event handler) creates a brand-new function reference on every render. Passing this unstable reference as a prop to a memo-wrapped child defeats the memoization because the prop appears to have changed.

A common pattern is to define event handlers with useCallback and an empty dependency array (when the handler only uses a functional state updater, which is referentially stable):

For example, define the add-to-cart handler using useCallback with an empty dependency array. Inside the callback, use a functional state updater so the callback does not depend on the current cart value and can remain referentially stable across renders.

### useMemo

The useMemo hook caches the result of an expensive computation and only recomputes it when dependencies change. This is useful for derived data that is computed on every render, such as filtering and sorting a product list. Without useMemo, every parent re-render recomputes the filtering and sorting even when the underlying data has not changed.

useMemo is also useful for precomputing lookup structures. If a component needs to look up review counts by product ID, building a map once with useMemo (keyed on the reviews array) is far more efficient than performing a linear search inside a loop for every product on every render.

### How These Work Together

The three mechanisms form a coherent system:
1. useMemo stabilizes derived data and expensive computations so they do not recalculate unnecessarily.
2. useCallback stabilizes function references passed as props.
3. React.memo on child components uses the stable props from (1) and (2) to skip re-rendering when nothing has actually changed.

All three must be applied together. Using React.memo without useCallback on handler props is ineffective. Using useCallback without React.memo on the child is pointless because the child re-renders regardless.

## JavaScript Bundle Size and Code Splitting

When a page imports a JavaScript module, that module and all of its transitive dependencies are included in the page's bundle. Users must download and parse this entire bundle before the page becomes interactive. Large bundles directly increase page load time.

### Barrel Imports vs. Direct Imports

Many libraries expose a "barrel" module that re-exports everything from a
single entry point. Importing one function through a barrel can retain far more
code than the requested function, particularly when the package format or
side-effect declarations prevent reliable tree shaking.

Direct (or "cherry-picked") imports bypass the barrel:

When a package officially exports a function-level module path, importing that
public subpath can load only the requested function and its dependencies.

This pattern loads only the specific function and its internal dependencies, drastically reducing bundle contribution.

Direct imports are valid only when the dependency actually exposes that
subpath. Before rewriting an import, inspect the installed package's
`package.json` exports map, module layout, and published type declarations, or
probe the candidate specifier with the project's own resolver. Then run the
real production build. A plausible-looking filesystem path is not necessarily
a public import path, especially when package exports intentionally hide
internal modules.

If a dependency does not publish stable function-level subpaths, keep a legal
public entry point. To prevent that dependency from entering the initial page
bundle, move the heavy consumer into a separate module and load that module at
an appropriate dynamic boundary. This preserves the package contract while
still enabling code splitting; replacing a legal barrel import with a broken
private subpath is not a performance optimization.

### Dynamic Imports and Code Splitting

Next.js supports dynamic imports through its dynamic loading function (a wrapper around React.lazy with SSR support). A dynamically imported component is not included in the initial page bundle. Instead, its code is loaded on demand when the component is first rendered.

This is particularly effective for content behind user interaction. If a page has tabs and one tab uses a heavy library (like a statistics or charting library), making that tab's component a dynamic import means the library is only downloaded when the user clicks the tab. The initial page load stays fast because it only includes the code for the default view.

The dynamically loaded component is created by calling the dynamic loading function with an import callback and an optional loading placeholder that provides feedback while the chunk loads.

The loading placeholder provides a visual indicator while the chunk loads. The component must be in a separate file (not defined in the same module) for the code splitting to take effect, because the split boundary is at the module level.

### Identifying Bundle Size Problems

Library size varies enormously. Measure the application's actual route chunks
with the framework's build output or a bundle analyzer. Large optional modules
that are absent from the initial user path are candidates for a legal dynamic
import boundary; small or already tree-shaken dependencies may not benefit.

The general principle is: if a library is large and not needed for the initial render, it should be dynamically imported. If only a few functions from a large library are used, prefer direct imports over barrel imports.

## Server-Side Rendering and Data Fetching in Next.js

Next.js App Router components are server components by default. Server components can be async and fetch data directly during rendering, which runs on the server. This means sequential fetch waterfalls in server components add directly to the Time to First Byte (TTFB) experienced by the user.

API route handlers similarly run on the server. The same principles of parallel fetching and fire-and-forget apply. A route handler that sequentially awaits three service calls will be three times slower than necessary if those calls are independent.

Disabling response caching ensures each request hits the actual data sources. This is important in scenarios where data freshness matters, but it also means that every request pays the full cost of all fetches, making optimization of the fetch pattern even more critical.

## Practical Considerations

**Memoization requires stabilizing all props, including callbacks.** Wrapping a component in React.memo while passing a newly created function reference as a prop on every render defeats the memoization, because the shallow comparison detects a new reference each time. For memoization to be effective, function props must be stabilized with useCallback or otherwise made referentially stable across renders.

**Dependent fetches require explicit chaining.** When one fetch depends on the result of another, the dependency must be explicitly modeled through promise chaining or sequential awaiting. Placing a dependent fetch into a concurrent group alongside its prerequisite causes the dependent call to receive undefined instead of the prerequisite's result, producing a runtime error.

**Tree-shaking effectiveness depends on module format.** CommonJS modules cannot be statically analyzed for tree-shaking. Even with a modern bundler, importing from a CommonJS library's barrel may pull in the entire library. Direct path imports are the standard approach for libraries that do not ship ES modules, ensuring only the needed functions are included in the bundle.

**Code splitting requires separate module files.** Dynamic importing or lazy loading works by creating a new code split point at the module boundary. If the heavy component is defined in the same file as the page that attempts to dynamically import it, no split occurs. The heavy code must reside in a separate module file for the code split to take effect.

**Performance instrumentation serves an observability purpose.** Code such as performance marks is intentionally placed for render tracking and diagnostics. These markers reveal where performance problems occur. Performance optimization addresses the root cause (excessive renders, large bundles, slow fetches) rather than removing the instruments that reveal the problem.

**API response caching involves correctness tradeoffs.** While caching can speed up repeated requests, it can also mask actual service call latency and produce stale data. In systems where correctness requires real-time service calls (for example, a checkout flow that must verify user identity in real time), caching the response would be a correctness violation. Caching is appropriate only when staleness is acceptable and the API contract permits it.

**Structural validators are not performance tests.** Confirming that source
code contains `Promise.all`, memoization, or a dynamic import does not prove the
critical path is short.  Pair structural checks with end-to-end measurements
and fail validation when the measured route still behaves like a waterfall.
