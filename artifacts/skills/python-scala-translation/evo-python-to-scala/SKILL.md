---
name: evo-python-to-scala
description: "Translate Python code to idiomatic Scala 2.13. Use when the task requires converting a Python module to Scala following best practices: sealed traits for enums/unions, case classes for data, type classes for protocols, Option for nullability, camelCase naming, and proper variance annotations. Provides analysis, validation, compilation, and testing utilities."
---

# Python to Idiomatic Scala 2.13 Translation

This skill provides utilities and patterns for translating Python code to
idiomatic Scala 2.13. It covers analysis of Python source, validation of
Scala output, compilation testing, and a comprehensive translation pattern
reference.

## Quick Start

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-python-to-scala/scripts')
from translate import (
    extract_python_classes,
    extract_class_methods,
    snake_to_camel,
    check_translation_patterns,
    translate_and_validate
)
from validate import full_validation

# Step 1: Analyze the Python source
with open('/root/Tokenizer.py', 'r') as f:
    py_source = f.read()

py_classes = extract_python_classes(py_source)
print(f"Python classes to translate: {py_classes}")

# Step 2: Write the Scala translation directly to the output path.
# The Scala file must be written by the agent following the translation
# patterns below. This is a creative task - the skill provides the
# pattern reference and validation, not code generation.
#
# Write /root/Tokenizer.scala following the patterns in this SKILL.md.

# Step 3: Validate the translation
results = translate_and_validate(
    python_input_path='/root/Tokenizer.py',
    scala_output_path='/root/Tokenizer.scala',
    localtest_dir='/root/localtest',
    required_classes=['TokenType', 'Token', 'BaseTokenizer', 'StringTokenizer',
                      'NumericTokenizer', 'TemporalTokenizer', 'UniversalTokenizer',
                      'WhitespaceTokenizer', 'TokenizerBuilder'],
    required_methods=['tokenize', 'tokenizeBatch', 'toToken', 'withMetadata']
)
print(f"Translation success: {results['success']}")
print(f"Pattern checks: {results['validation'].get('patterns', {})}")
if results['tests']:
    print(f"Tests: {results['tests']['passed']} passed, {results['tests']['failed']} failed")

# Step 4: Full validation
val_results = full_validation(
    scala_path='/root/Tokenizer.scala',
    localtest_dir='/root/localtest',
    required_classes=['TokenType', 'Token', 'BaseTokenizer', 'StringTokenizer',
                      'NumericTokenizer', 'TemporalTokenizer', 'UniversalTokenizer',
                      'WhitespaceTokenizer', 'TokenizerBuilder'],
    required_methods=['tokenize', 'tokenizeBatch', 'toToken', 'withMetadata']
)
print(f"Overall success: {val_results['overall_success']}")
```

## Translation Pattern Reference

### 1. Enumerations: `Enum` → Sealed Trait + Case Objects

Python:
```python
class TokenType(Enum):
    STRING = "string"
    NUMERIC = "numeric"
```

Scala:
```scala
sealed trait TokenType {
  def value: String
}
object TokenType {
  case object STRING extends TokenType { val value = "string" }
  case object NUMERIC extends TokenType { val value = "numeric" }
  val values: Seq[TokenType] = Seq(STRING, NUMERIC)
  def fromString(s: String): Option[TokenType] = values.find(_.value == s)
}
```

### 2. Dataclasses → Case Classes

Python:
```python
@dataclass(frozen=True)
class Token:
    value: str
    token_type: TokenType
    metadata: dict[str, Any] = field(default_factory=dict)
```

Scala:
```scala
final case class Token(
  value: String,
  tokenType: TokenType,
  metadata: Map[String, Any] = Map.empty
) {
  def withMetadata(newMeta: (String, Any)*): Token =
    copy(metadata = metadata ++ newMeta.toMap)
}
```

### 3. Protocols → Type Classes

Python:
```python
@runtime_checkable
class Tokenizable(Protocol):
    def to_token(self) -> str: ...
```

Scala:
```scala
trait Tokenizable[A] {
  def toToken(a: A): String
}
object Tokenizable {
  implicit class TokenizableOps[A](val a: A) extends AnyVal {
    def toToken(implicit ev: Tokenizable[A]): String = ev.toToken(a)
  }
  // Default instances
  implicit val stringTokenizable: Tokenizable[String] = (a: String) => a
}
```

### 4. Union Types → Sealed Trait ADTs

Python:
```python
StrOrBytes = TypeVar("StrOrBytes", str, bytes)
```

Scala:
```scala
sealed trait StrOrBytes {
  def asString(encoding: String): String
}
object StrOrBytes {
  final case class Str(value: String) extends StrOrBytes { ... }
  final case class Bytes(value: Array[Byte]) extends StrOrBytes { ... }
  implicit def fromString(s: String): StrOrBytes = Str(s)
  implicit def fromBytes(b: Array[Byte]): StrOrBytes = Bytes(b)
}
```

### 5. ABC → Abstract Class/Trait

Python:
```python
class BaseTokenizer(ABC, Generic[T]):
    @abstractmethod
    def tokenize(self, value: T) -> Token: ...
    def tokenize_batch(self, values: Iterable[T]) -> Iterator[Token]: ...
```

Scala:
```scala
abstract class BaseTokenizer[A] {
  def tokenize(value: A): Token
  def tokenizeBatch(values: Iterable[A]): Iterator[Token] =
    values.iterator.map(tokenize)
}
```

### 6. Generic Variance

- Python `TypeVar("T_co", covariant=True)` → Scala `[+A]`
- Python `TypeVar("T_contra", contravariant=True)` → Scala `[-A]`
- Python `TypeVar("T")` (plain) → Scala `[A]` (invariant)

### 7. Optional → Option

- Python `Optional[T]` / `T | None` → Scala `Option[T]`
- Python `None` → Scala `None` (the Option subtype) or `Option.empty`
- Python `if x is not None` → Scala `x.map(...)`, `x.getOrElse(...)`, or pattern match

### 8. Mutable Default Arguments

Python anti-pattern:
```python
def __init__(self, format_options: dict[str, Any] = {}):  # shared mutable!
```

Scala (no shared state):
```scala
class NumericTokenizer(formatOptions: Map[String, Any] = Map.empty)
```

### 9. Naming Conventions

- Methods: `snake_case` → `camelCase` (tokenize_batch → tokenizeBatch)
- Classes/Traits: `PascalCase` (same in both)
- Constants: case objects in sealed traits use `PascalCase`
- Packages: all lowercase

### 10. JSON Handling

- Python `json` module → Circe library
- `json.dumps(value)` → `value.noSpaces`
- `json.dumps(value, indent=2)` → `value.spaces2`
- `json.loads(s)` → `io.circe.parser.parse(s)` returns `Either[ParsingFailure, Json]`

### 11. DateTime

- Python `datetime.datetime` → `java.time.LocalDateTime`
- Python `datetime.date` → `java.time.LocalDate`
- Python `strftime("%Y-%m-%dT%H:%M:%S")` → `DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss")`

### 12. Builder Pattern

- Fluent interface with `this` return for method chaining
- Use `mutable.ListBuffer` internally, expose immutable in `build()`
- Companion object with `apply()` factory method

### 13. Error Handling

- Python `raise ValueError(...)` → Scala `throw new IllegalArgumentException(...)`
- Python `raise RuntimeError(...)` → Scala `throw new RuntimeException(...)`
- Python `try/except` → Scala `Try`/`Either`/pattern matching
- Return `Either[Error, Result]` or `Option[Result]` instead of raising

## Key Checklist for Translation

1. [ ] Package declaration at top
2. [ ] All imports (java.time, circe, scala.collection.mutable)
3. [ ] Enums as sealed traits with case objects and companion
4. [ ] Data classes as case classes with default Map.empty
5. [ ] Protocols as type classes with implicit instances
6. [ ] Union types as sealed trait ADTs
7. [ ] Variance annotations on generic containers (+A, -A)
8. [ ] snake_case → camelCase for all methods
9. [ ] Option instead of null/None
10. [ ] Immutable collections by default
11. [ ] Companion objects for factory methods
12. [ ] Scaladoc comments (/** ... */)
13. [ ] No mutable default argument sharing
14. [ ] Proper access modifiers (private, protected)

## Scripts

- `scripts/translate.py`: Python AST analysis, pattern checking, end-to-end pipeline
- `scripts/validate.py`: Static validation, compilation testing, test execution
