# JSON Flow

A streaming JSON parser that handles partial and incomplete JSON data.

## Features

- Streaming parse of JSON data
- Support for partial and incomplete JSON structures
- Comprehensive error handling
- Support for arrays, objects, and nested structures
- Handles whitespace and special characters
- Unicode support

## Algorithm Complexity

The JSON stream parser's complexity can be analyzed by its key operations:

### Time Complexity

1. **Consume Operation**: O(n)
   - Appending to chunks: O(1) amortized
   - Validation of brace/bracket count: O(n)
   - Parsing operation: O(n)

2. **Get Operation**: O(1)
   - return the string parsed

### Space Complexity

1. **Instance Storage**: O(n)
   - chunks list: O(n) for storing partial JSON strings
   - current_valid_json: O(n) for the latest valid JSON string

2. **Parsing Operations**: O(1)
   - All parsing operations use constant extra space

### Recursion

The parser uses recursion to handle nested structures. The depth of the recursion is determined by the depth of the JSON structure being parsed. For deep nested json files, it might raise a stack overflow runtime error.

## Installation

JSON Flow requires Python 3.11 or later. The project uses `uv` for dependency management.

### uv

```bash
# Create a virtual environment and install dependencies
uv venv
source .venv/bin/activate
uv sync
```

### venv
```bash
python -m venv .venv
pip install -r requirements-dev.txt
```
```bash
# For development, install additional dependencies
pip install -r requirements-dev.txt
```

## Usage

```python
from stream_parser import StreamJsonParser

# Create a parser instance
parser = StreamJsonParser()

# Feed partial JSON data
parser.consume('{"key": ')
parser.consume('"value"}')

# Get the parsed result
result = parser.get()  # Returns {"key": "value"}
```

### Handling Partial Data

The parser can handle incomplete JSON structures:

```python
parser = StreamJsonParser()

# Feed incomplete data
parser.consume('{"outer": {"inner')
result = parser.get()  # Returns {}

# Feed more data
parser.consume('": "value"}}')
result = parser.get()  # Returns {"outer": {"inner": "value"}}
```

## Development

### Running Tests

#### pytest

```bash
# Run all tests
pytest

# Run tests with coverage
pytest --cov=src
```

#### uv

```bash
# Run linter
uv run pytest
```

### Code Style

The project uses `ruff` for code formatting and linting:

```bash
make format
make lint
make lint_fix
```

## Project Structure

- `src/stream_parser.py`: Main parser implementation
- `src/config.py`: Configuration and logging setup
- `src/logger.py`: Logger configuration
- `tests/`: Test suite with comprehensive test cases

## Dependencies

- `pydantic`: Data validation using Python type annotations
- `pydantic-settings`: Settings management
- `python-dotenv`: Environment variable management
- `python-json-logger`: JSON-formatted logging

### Development Dependencies

- `pytest`: Testing framework
- `ruff`: Code formatting and linting

## Error Handling

The parser provides detailed error handling through custom exceptions:

- `StreamParserJSONDecodeError`: Base class for JSON parsing errors
- `PartialJSON`: Indicates incomplete JSON data
- `MalformedJSON`: Indicates invalid JSON format
