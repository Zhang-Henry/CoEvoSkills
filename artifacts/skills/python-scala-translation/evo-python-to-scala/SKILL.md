---
name: evo-python-to-scala
description: "Translate Python code to idiomatic Scala 2.13. Handles type system mapping (enums to sealed traits, Union to ADTs, Optional to Option), naming conventions (snake_case to camelCase), Protocol to type class pattern, dataclass to case class, and compilation validation via sbt."
---

# Python to Scala Translation Skill

This skill provides utilities for translating Python code to idiomatic Scala 2.13.

## Key Translation Patterns

1. **Enums** → sealed trait + case objects
2. **Union types** → sealed trait ADT with case class variants
3. **Optional** → Option[T]
4. **Protocol** → type class trait with implicit instances
5. **dataclass** → case class (immutable by default)
6. **ABC/abstractmethod** → abstract class/trait with abstract methods
7. **isinstance chains** → pattern matching
8. **Mutable defaults** → immutable defaults (Map.empty, etc.)
9. **snake_case** → camelCase for methods/vals
10. **TypeVar covariant/contravariant** → [+A]/[-A] variance annotations
11. **datetime** → java.time.LocalDateTime/LocalDate
12. **Decimal** → BigDecimal
13. **json** → circe (Json type, spaces2/noSpaces)
14. **Generators/yield** → Iterator with lazy evaluation
15. **Builder pattern** → fluent methods returning this

## Compilation Notes

- sbt picks up .scala files from root AND src/main/scala, causing duplicates
- Temporarily rename root-level .scala file during sbt compile
- Need project/build.properties with sbt version
- Package name must match directory structure under src/main/scala/

## Usage Example

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-python-to-scala/scripts')
from utils import (
    run_end_to_end,
    validate_deliverable,
    compile_scala,
    validate_required_elements,
    snake_to_camel
)

# Define required elements from task
required = [
    'TokenType', 'Token', 'BaseTokenizer', 'StringTokenizer',
    'NumericTokenizer', 'TemporalTokenizer', 'UniversalTokenizer',
    'WhitespaceTokenizer', 'TokenizerBuilder', 'tokenize',
    'tokenizeBatch', 'toToken', 'withMetadata'
]

# Validate the deliverable
result = validate_deliverable(
    scala_output='/root/Tokenizer.scala',
    package_name='tokenizer',
    required_names=required
)
print(f"Valid: {result['valid']}")
print(f"Issues: {result['issues']}")
print(f"Found: {result['found_elements']}")

# Full end-to-end (compile + validate)
result = run_end_to_end(
    python_file='/root/Tokenizer.py',
    scala_output='/root/Tokenizer.scala',
    package_name='tokenizer',
    required_names=required,
    root_dir='/root'
)
print(f"Success: {result['success']}")
for step in result['steps']:
    print(f"  {step}")
```
