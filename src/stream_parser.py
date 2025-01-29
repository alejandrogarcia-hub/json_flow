import re
from typing import Any, Optional, Union

from config import logger


class StreamParserJSONDecodeError(ValueError):
    """Base class for JSON parsing errors in the stream parser.

    This class serves as the base exception for all JSON parsing related errors
    in the stream parser implementation.

    Args:
        message: The error message describing the parsing failure.

    Note:
        Inherits from ValueError to maintain compatibility with standard JSON decode errors.
    """

    pass


class PartialJSON(StreamParserJSONDecodeError):
    """Error indicating incomplete JSON data.

    Args:
        message: The error message describing the incomplete JSON structure.

    Note:
        Raised when parsing ends with a valid but incomplete JSON structure, such as
        an unclosed object or array, or a partial string/number.
    """

    pass


class MalformedJSON(StreamParserJSONDecodeError):
    """Error indicating invalid JSON format.

    Args:
        message: The error message describing the malformed JSON.

    Note:
        Raised when encountering JSON that violates the specification, including:
        - Invalid literals or numbers
        - Mismatched brackets/braces
        - Missing commas or colons
        - Invalid value types
    """

    pass


# finditer = compile(r'["\[\]{}]').finditer

finditer = re.compile(
    r"""
    "(?:[^"\\]|\\.)*"      # String literals (capture whole string including quotes)
    |                      # OR
    [[\]{}:,]|            # Structural characters and delimiters
    \b(?:null|false|true)\b| # JSON literals
    -?(?:0|[1-9]\d*)        # Integer part
    (?:
        \.\d+                # Decimal part
        (?:[eE][-+]?\d+)?   # Optional scientific notation
        |
        [eE][-+]?\d+        # Scientific notation without decimal
    )?
""",
    re.VERBOSE,
).finditer


def scan(json_string: str):
    return [(match.start(), match.group()) for match in finditer(json_string)]


def _find_non_whitespace_index(buffer: list[str], index: int) -> int:
    """Finds the next non-whitespace character position in the buffer.

    Args:
        buffer: List of characters to scan.
        index: Starting position for the scan.

    Returns:
        Index of the first non-whitespace character, or len(buffer) if none found.

    Note:
        Scans forward from the given index, skipping over JSON whitespace characters
        (space, tab, newline, carriage return).
    """
    while index < len(buffer):
        char = buffer[index]
        # From JSON specs, whitespace is space, horizontal tab, line feed, or carriage return
        is_whitespace = (
            char == " "  # space
            or char == "\t"  # horizontal tab
            or char == "\n"  # line feed
            or char == "\r"  # carriage return
        )
        if not is_whitespace:
            return index

        index += 1

    return index


def is_escaped(index: int, json_string: str):
    """Check if the character at the given index is escaped in the JSON string.

    Args:
        index: The index of the character to check.
        json_string: The JSON string to check.

    Returns:
        True if the character is escaped, False otherwise.
    """
    text_before = json_string[:index]
    count = index - len(text_before.rstrip("\\"))
    return count % 2 == 1


class StreamJsonParser:
    def __init__(self):
        self.stack = []
        self.root = None
        self.in_string = False
        self.last_key = None
        self.last_string_start = -1
        self.last_string_end = -1
        self.state = None
        self.partial = False

    def consume(self, json_str: str) -> None:
        tokens = scan(json_str)
        tokens_len = len(tokens)
        str_len = len(json_str)

        # we handle the case when the whole string is just some value not enclosed in quotes
        # example: "{"key": [ -> hello -> , 12345 -> ]}"
        if tokens_len == 0 and str_len > 0:
            if self.state is None and not self.stack:
                raise MalformedJSON("invalid json, some random value as root is invalid")
            tokens.append((0, json_str))

        # check if there is a partial string after the last token index in json_str
        # if there is a pratial string, then add the `"` and it index to tokens
        has_partial_string = '"' in json_str[tokens[-1][0] + 1 :]
        if has_partial_string:
            # get the index of the partial string
            tokens.append(
                (tokens[-1][0] + 1 + json_str[tokens[-1][0] + 1 :].index('"'), json_str[tokens[-1][0] + 1 :])
            )

        
        i = 0
        while i < tokens_len:
            index, char = tokens[i]
            if char == "{":
                obj = {}
                if not self.stack:
                    if self.root is not None:
                        logger.error("invalid object: double root")
                        raise MalformedJSON("invalid object: no parent container")
                    self.stack.append(obj)
                else:
                    if isinstance(self.stack[-1], dict):
                        if self.state != "value":
                            logger.error(
                                "invalid object: unexpected self.state, waiting for object value"
                            )
                            raise MalformedJSON(
                                "invalid object: unexpected self.state, waiting for object value"
                            )
                        self.stack[-1][self.last_key] = obj
                    else:
                        self.stack[-1].append(obj)

                self.stack.append(obj)
                self.state = "key"
            elif char == "[":
                arr = []
                if not self.stack:
                    if self.root is not None:
                        logger.error("invalid array: double root")
                        raise MalformedJSON("invalid array: no parent container")
                    self.stack.append(arr)
                else:
                    if isinstance(self.stack[-1], dict):
                        if self.state != "value":
                            logger.error(
                                "invalid array: unexpected self.state, waiting for array value"
                            )
                            raise MalformedJSON(
                                "invalid array: unexpected self.state, waiting for array value"
                            )
                        self.stack[-1][self.last_key] = arr
                    else:
                        self.stack[-1].append(arr)

                self.stack.append(arr)
                self.state = "value"
            elif char == "}":
                if not isinstance(self.stack[-1], dict):
                    logger.error("invalid object: expected dict to close object")
                    raise MalformedJSON("invalid object: expected dict to close object")

                container = self.stack.pop()
                if not self.stack:
                    self.root = container
            elif char == "]":
                if not isinstance(self.stack[-1], list):
                    logger.error("invalid array: expected list to close array")
                    raise MalformedJSON("invalid array: expected list to close array")

                container = self.stack.pop()
                if not self.stack:
                    self.root = container
            elif char == ":":
                if self.state == "key" and self.partial:
                    raise MalformedJSON(
                        "invalid object: the object key was not properly closed"
                    )
                self.state = "value"
            elif char == ",":
                self.state = "key" if isinstance(self.stack[-1], dict) else "value"
                if self.state == "key":
                    self.last_key = None
            else:
                if self.state == "key":
                    if self.partial:
                        if char[-1] == '"':
                            self.last_key += json_str[:index]
                            self.partial = False
                        else:
                            if i + 1 >= tokens_len:
                                # case when we keep on having a partial value of the key
                                self.last_key += json_str[:str_len]
                            else:
                                # invalid
                                raise MalformedJSON(
                                    "we are expeting a string, \
                                    it should be closed or keep on partial \
                                    but none are satisfied."
                                )
                    elif char[0] != '"':
                        logger.error("invalid key: expected string")
                        raise MalformedJSON("invalid key: expected string")
                    else:
                        if i + 1 < tokens_len:
                            if tokens[i + 1][1] != '"':
                                raise MalformedJSON(
                                    "invalid key: expected close string"
                                )

                            _to_index = tokens[i + 1][0]
                            self.partial = False
                        else:
                            _to_index = str_len
                            self.partial = True

                        self.last_key = json_str[index + 1 : _to_index]
                        # we skip the next " token
                        i += 1
                elif self.state == "value":
                    if self.partial:
                        current_value = (
                            self.stack[-1][self.last_key]
                            if isinstance(self.stack[-1], dict)
                            else self.stack[-1][-1]
                        )
                        value = current_value + json_str[:index]
                        if value == "null":
                            value = None
                            self.partial = False
                        elif value == "true":
                            value = True
                            self.partial = False
                        elif value == "false":
                            value = False
                            self.partial = False
                        elif value[0] in "0123456789+-.":
                            j = index
                            while j < str_len and json_str[j] in "0123456789+-.eE":
                                j += 1
                            value = current_value + json_str[index:j]
                            try:
                                if "e" in value.lower() or "." in value:
                                    value = float(value)
                                else:
                                    value = int(value)
                                self.partial = False
                            except ValueError:
                                raise MalformedJSON("invalid number")
                        else:
                            # can be a partial string
                            if char != '"':
                                if i + 1 < tokens_len:
                                    raise MalformedJSON("invalid string, unnknown case")

                                value = current_value + json_str[index:str_len]
                            i += 1

                        if isinstance(self.stack[-1], dict):
                            self.stack[-1][self.last_key] = value
                        else:
                            self.stack[-1][-1] = value

                        # at this point the current char can be a state transition char
                        # therefore, do not move forward
                        continue

                    if char == '"':
                        if i + 1 < tokens_len:
                            _to_index = tokens[i + 1][0]
                        else:
                            _to_index = str_len
                            self.partial = True

                        value = json_str[index + 1 : _to_index]
                        i += 1
                    elif char == "null":
                        value = None
                    elif char == "true":
                        value = True
                    elif char == "false":
                        value = False
                    elif char in "0123456789+-.":
                        j = index
                        while j < str_len and json_str[j] in "0123456789+-.eE":
                            j += 1
                        value = json_str[index:j]
                        try:
                            if "e" in value.lower() or "." in value:
                                value = float(value)
                            else:
                                value = int(value)
                        except ValueError:
                            raise MalformedJSON("invalid number")
                    else:
                        # it can be we have a partial value for null, true, false
                        self.partial = True
                        value = char

                    if isinstance(self.stack[-1], dict):
                        self.stack[-1][self.last_key] = value
                    else:
                        self.stack[-1].append(value)

            i += 1

    def get(self):
        if self.root is not None and not self.stack:
            return self.root

        if not self.stack:
            return None

        return self.stack[0]
