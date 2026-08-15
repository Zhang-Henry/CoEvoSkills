# Translating Python to Idiomatic Scala

This document provides background on the key language differences and design patterns that arise when translating a Python codebase to Scala 2.13, with emphasis on the type system, functional programming idioms, and Scala conventions that a proficient developer would expect.

## Type System Mapping: From Dynamic to Static

Python and Scala sit at opposite ends of the type-safety spectrum. Python's type annotations (via the typing module) are advisory and not enforced at runtime, whereas Scala's type system is checked at compile time and plays a central role in program design.

### Enumerations

Python uses enum.Enum with string or integer values. In Scala 2.13, the idiomatic equivalent is a **sealed trait** with **case objects** for each variant. Each case object can carry a value field that mirrors the string value of the Python enum member. A companion object conventionally provides a collection of all values and a lookup method (such as fromString). Scala 3 introduced enum syntax, but Scala 2.13 code should use the sealed trait pattern.

### Union and Sum Types

Python freely uses Union[A, B] type hints and runtime isinstance checks to dispatch on types. Scala 2.13 has no built-in union type (Scala 3 adds A | B), so the standard approach is an **algebraic data type (ADT)**: a sealed trait with case class variants for each member of the union. Pattern matching then provides exhaustive, compile-time-checked dispatch. This is a structural change -- a single Python parameter that accepts multiple types becomes a sealed trait hierarchy with explicit wrapper case classes and pattern matching at the call site.

### Optional Values

Python uses Optional[T] (which is Union[T, None]) and checks for None at runtime. In Scala, the equivalent is Option[T] -- a sealed type with two subtypes, Some[T] and None. Idiomatic Scala code avoids null references entirely; it wraps nullable values in Option and processes them with map, flatMap, getOrElse, or pattern matching. Using null in Scala code is considered an anti-pattern and defeats the purpose of the type system.

### Type Variables and Generics

Python's TypeVar maps to Scala's type parameters. Key considerations:

- **Covariance** (a covariant TypeVar in Python) becomes [+A] in Scala. A covariant container means that Container[Cat] is a subtype of Container[Animal] when Cat is a subtype of Animal. Covariant type parameters can only appear in return ("out") positions.
- **Contravariance** (a contravariant TypeVar in Python) becomes [-A]. A contravariant consumer means that Sink[Animal] is a subtype of Sink[Cat]. Contravariant type parameters can only appear in argument ("in") positions.
- **Invariance** (a plain TypeVar) becomes [A] with no annotation. The type must match exactly.
- **Bounded type variables** (a TypeVar constrained to specific types like int, float, Decimal) become either sealed trait ADTs or context bounds in Scala, depending on whether the constraint is a fixed set of types or a capability requirement.

### Protocols and Type Classes

Python's Protocol classes provide structural ("duck") typing: any object with matching method signatures satisfies the protocol, checked optionally at runtime via isinstance. Scala's equivalent is the **type class pattern**: a trait parameterized by the type it operates on (e.g., trait Tokenizable[A]), with implicit instances provided for each supported type. A companion object conventionally holds default instances and syntax extensions. This is a fundamental design shift -- Python relies on runtime structural matching, while Scala uses compile-time implicit resolution.

## Functional Programming Idioms

Scala is a hybrid language that strongly favors functional programming. A direct line-by-line translation of Python code will produce non-idiomatic Scala. Proficient Scala developers expect these patterns:

### Immutability by Default

Scala distinguishes val (immutable binding) from var (mutable binding). Idiomatic Scala uses val wherever possible. Case classes are immutable by default, and the copy method is used to create modified versions. The ratio of val to var in a codebase is a quick signal of functional style -- high var usage suggests imperative translation rather than idiomatic Scala.

### Collections

Python's list, dict, and set are mutable. Scala's default collection imports (List, Map, Set, Vector) are **immutable**. Mutable collections exist in scala.collection.mutable but should only be used when there is a clear reason (e.g., performance-critical accumulation in a builder). When mutability is needed, the choice is made explicit by importing from mutable and using mutable.ListBuffer, mutable.Map, etc.

### Pattern Matching

Scala's match expression replaces Python's chains of isinstance checks. Pattern matching on sealed trait hierarchies is exhaustive -- the compiler warns if a case is missed. This is one of the most important translation steps: converting runtime type dispatch into compile-time verified pattern matches.

### Higher-Order Functions and Collection Operations

Python list comprehensions map to Scala's map, filter, flatMap, and for/yield comprehensions. Generators (yield in Python) correspond to Scala's Iterator with lazy evaluation. A Python for loop that accumulates results into a list is expressed in Scala as a map or flatMap call.

### Error Handling

Python uses exceptions (try/except). Scala provides functional alternatives: Try[T] (wraps a computation that may throw), Either[L, R] (explicit success/failure without exceptions), and Option[T] (presence/absence). Throwing exceptions is legal in Scala but considered a last resort. Idiomatic code uses Try or Either and composes error-handling logic with map, flatMap, and recover.

## Scala Naming and Structural Conventions

Scala has well-established naming conventions that differ from Python:

- **Classes, traits, objects**: PascalCase (TokenizerBuilder, BaseTokenizer)
- **Methods and values**: camelCase (tokenize, tokenizeBatch, withMetadata)
- **Constants**: can be PascalCase or UPPER_SNAKE_CASE depending on convention, but case object members of sealed traits are typically PascalCase
- **Packages**: all lowercase, dot-separated (tokenizer, com.example.tokenizer)
- **Indentation**: 2 spaces (not 4 as in Python)

A Python method named with underscores (e.g., tokenize_batch) becomes camelCase in Scala (tokenizeBatch). Python's snake_case convention for methods and variables becomes camelCase for methods/vals and PascalCase for types.

### Scaladoc

Python uses docstrings (triple-quoted strings). Scala uses Scaladoc comments (delimited by /** and */). Public APIs should be documented with Scaladoc, including @param, @return, and @throws tags where relevant. Inline comments use //.

### Access Modifiers

Python uses underscore conventions for visibility (_private, __mangled). Scala has proper access modifiers: private, protected, and package-scoped private. These are used explicitly rather than relying on naming conventions.

## Translating Design Patterns

### Abstract Base Classes to Abstract Classes and Traits

Python's ABC with abstractmethod decorators maps to Scala abstract class or trait with abstract method declarations (methods with no body). Traits are preferred when multiple inheritance is needed. If the base type takes a generic parameter, the Scala equivalent is an abstract class or trait with a type parameter.

### Dataclasses to Case Classes

Python's dataclass decorator maps directly to Scala's case class. Key differences:

- frozen=True is the default in Scala case classes (all fields are val by default)
- A field with a default factory for an empty dictionary becomes a default parameter with an empty immutable Map
- The copy method is auto-generated and replaces manual construction of modified instances

### Builder Pattern

Python fluent builders that return self translate naturally, but there is a subtlety with mutable default arguments. Python allows (though it is an anti-pattern) mutable default arguments in constructors. Scala does not share state across invocations, so the equivalent is simply a default parameter with an immutable collection -- the immutable collection eliminates the shared-state bug entirely.

### Companion Objects and Factory Methods

Python uses classmethod for alternative constructors. Scala uses **companion objects** -- an object with the same name as a class, defined in the same file. The companion can hold factory methods (apply), implicit instances, and utility functions. The apply method in a companion object enables construction without the new keyword.

### Implicit Conversions

When Python code relies on duck typing to accept multiple types seamlessly, Scala can use implicit conversions to achieve similar ergonomics. These are defined in companion objects of the target type and allow automatic wrapping at call sites. However, implicit conversions should be used judiciously -- they are powerful but can make code harder to follow if overused.

## Working with External Libraries

### JSON Handling

Python's json module is dynamic -- it accepts any JSON-compatible Python object and produces a string. Scala's ecosystem provides type-safe JSON libraries. **Circe** is the most common for Scala 2.13. Key differences:

- JSON values are represented by a dedicated Json type (not raw Scala collections)
- Parsing returns an Either with a failure or a Json value rather than raising exceptions
- Pretty-printing and compact printing are separate methods on the Json type
- Object access uses chained method calls on the Json type rather than dictionary indexing
- Circe requires explicit codec derivation or manual encoder/decoder definitions for custom types

### Date and Time

Python uses datetime.datetime and datetime.date. Scala on the JVM uses java.time.LocalDateTime and java.time.LocalDate. Formatting uses DateTimeFormatter with pattern strings rather than strftime-style format strings, though the pattern letters are similar (yyyy-MM-dd'T'HH:mm:ss vs %Y-%m-%dT%H:%M:%S).

### Numeric Precision

Python has decimal.Decimal for arbitrary-precision decimals. Scala has BigDecimal (wrapping java.math.BigDecimal). Formatting with a specific number of decimal places uses setScale with a rounding mode or string formatting methods.

## Key Distinctions in Practice

### Idiomatic Restructuring vs. Literal Translation

Effective Python-to-Scala translation requires restructuring, not line-by-line transposition. A for loop with isinstance checks, a mutable accumulator list, and None checks is expressed in Scala as a pattern match over a sealed trait hierarchy using map/flatMap with Option. Idiomatic Scala code reflects the language's functional paradigm rather than mirroring Python's imperative patterns.

### Option as the Standard Null-Safety Mechanism

In Scala, the Option type is the standard mechanism for representing the presence or absence of a value. Every Python None translates to Option.empty or the Scala None (the Option subtype), and conditional checks for None become Option.map or pattern matching on Option. The null reference exists in Scala for JVM compatibility but is not used in idiomatic code.

### The Role of Sealed in ADT Hierarchies

When encoding Python enums or union types as Scala ADTs, the sealed keyword on the base trait is essential. Sealing the trait allows the compiler to perform exhaustiveness checking on pattern matches, which is the primary advantage of the ADT encoding. Without it, the compiler cannot verify that all cases are handled.

### Immutable Collections as the Default

Scala's standard library defaults to immutable collections. Many Python mutation patterns (appending to lists, updating dictionaries) have clean immutable equivalents in Scala: appending an element to a list, adding a key-value pair to a map, or building with foldLeft. Mutable collections are reserved for internal builder state or performance-critical paths, with immutable types exposed in public APIs.

### Variance Annotations and the Compiler

In Python, covariant and contravariant TypeVars are rarely enforced at runtime. In Scala, variance annotations (+A for covariance, -A for contravariance) are enforced by the compiler. If a container is conceptually covariant (it only produces values of type A), it must be annotated [+A] -- and the compiler will reject code that places A in a contravariant position. Correct variance annotations require understanding which positions are "in" (method parameters) vs. "out" (return types).

### Companion Objects as Organizational Units

Python classes often have classmethod factory methods or class-level constants. In Scala, companion objects serve this role -- they are where factory methods (apply), implicit definitions, default type class instances, and alternative constructors reside. They are a fundamental organizational unit in Scala that has no direct Python equivalent.

### Naming Convention Alignment

Python's snake_case methods (tokenize_batch, to_token, with_metadata) become camelCase in Scala (tokenizeBatch, toToken, withMetadata). This is a universal convention in the Scala ecosystem -- the standard library and all major libraries use camelCase for methods and vals, and PascalCase for types.

## sbt Project Structure and Compilation

sbt (Scala Build Tool) is the standard build tool for Scala projects.
Understanding its conventional source layout and dependency scoping is useful
when validating a translation, but the required deliverable path and the build
entry point must be taken from the task environment.

### Directory Layout

sbt follows the Maven/Gradle convention:

```
project-root/
├── build.sbt                          # Build definition
├── project/
│   └── build.properties               # sbt version (optional)
├── src/
│   ├── main/scala/                    # Main source files
│   │   └── packagename/
│   │       └── MyCode.scala
│   └── test/scala/                    # Test source files
│       └── packagename/
│           └── MyCodeSpec.scala
```

By default, sbt discovers main sources under `src/main/scala` and test sources
under `src/test/scala`.  A standalone source file requested as a deliverable is
not automatically part of an unrelated sbt project; inspect the available build
or validation command to determine how that file is compiled.

### Dependency Scoping: `% Test`

In `build.sbt`, dependencies marked with `% Test` are available only to the
`Test` configuration.  Keep validation-only code in the test source set when
using a conventional sbt project.  Do not invent duplicate file placement,
symlinks, source-directory overrides, or a particular project scaffold unless
the actual environment requires them; they are build decisions rather than
part of Python-to-Scala translation knowledge.

### Writing Scala Code Directly

When translating Python to Scala, **write the Scala source file directly** rather than generating it programmatically through string templates or code generation scripts. Generating Scala code inside Python strings (especially f-strings or format strings) introduces multi-layer escaping problems:

- Scala regex patterns like `"\\."` and `"\\s+"` require double backslashes in Scala string literals.
- Embedding these inside Python strings adds another escaping layer (`"\\\\."`).
- Python f-strings add yet another layer for curly braces (`{{` and `}}`).
- Character literals like `'\''` (apostrophe) are particularly error-prone across layers.

These compounding escaping issues are a common source of hard-to-debug compilation failures. Writing Scala directly avoids this entire class of problems.
