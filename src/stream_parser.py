"""Stream parser module for JSON processing.

This module provides a streaming JSON parser implementation that can process JSON data
incrementally. It includes custom exception classes and utility functions for parsing
and tokenizing JSON strings.
"""

from typing import Any, Union

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


def scan(json_string: str) -> list[tuple[int, str]]:
    """Tokenizes a JSON-like string with emphasis on structural characters.

    This function breaks down a JSON string into tokens, giving precedence to structural
    characters ([]{}:,) as delimiters. It handles strings, numbers, and JSON literals
    while preserving their positions in the input.

    Args:
        json_string: The input string to be tokenized.

    Returns:
        A list of tuples where each tuple contains:
            - Position (int): The starting index of the token in the input string
            - Token (str): The actual token string

    Examples:
        >>> scan('u": "val')
        [(0, 'u"'), (2, ':'), (4, '"val')]
        >>> scan('{ "key')
        [(0, '{'), (1, ' "key')]
    """
    tokens = []
    i = 0
    length = len(json_string)

    # Structural delimiters
    structural = set("[]{}:,")

    def is_structural(ch):
        return ch in structural

    # Helper: consume a string (assuming current char is the opening quote).
    # Returns the substring (including both quotes if we find a closing one),
    # or from the opening quote to end-of-string if not closed.
    def consume_string(start_idx):
        # start_idx should point to the opening quote '"'
        escaped = False
        idx = start_idx + 1  # move past the opening quote
        while idx < length:
            c = json_string[idx]
            if escaped:
                escaped = False
                idx += 1
            else:
                if c == "\\":
                    escaped = True
                    idx += 1
                elif c == '"':
                    # Found matching closing quote
                    idx += 1
                    return json_string[start_idx:idx], idx
                else:
                    idx += 1
        # If we get here, we never found a closing quote
        return json_string[start_idx:length], length

    # Helper: consume a "word" (letters) or partial text until whitespace/structural
    def consume_text(start_idx):
        idx = start_idx
        while idx < length:
            # Stop if we hit structural or whitespace
            if is_structural(json_string[idx]) or json_string[idx].isspace():
                break
            idx += 1
        return json_string[start_idx:idx], idx

    # Helper: consume a number (starting with +, -, or digit)
    def consume_number(start_idx):
        idx = start_idx
        # We already know json_string[idx] is +, -, or digit
        idx += 1  # consume that sign or first digit

        # forward
        while idx < length and json_string[idx] in "1234567890.-+eE":
            idx += 1

        return json_string[start_idx:idx], idx

    while i < length:
        c = json_string[i]

        # Skip whitespace
        if c.isspace():
            i += 1
            continue

        # If it's a structural character, that is always a separate token
        if is_structural(c):
            tokens.append((i, c))
            i += 1
            continue

        # If chunk starts with a quote, parse as a string
        if c == '"':
            text, next_pos = consume_string(i)
            tokens.append((i, text))
            i = next_pos
            continue

        # Otherwise, let's see if it might be a number
        if c in "+-0123456789":
            num_text, next_pos = consume_number(i)
            tokens.append((i, num_text))
            i = next_pos
            continue

        # Otherwise, consume text up to next structural or whitespace
        text, next_pos = consume_text(i)

        # If the resulting text is exactly one of the JSON literals,
        # then record it as such.
        if text in ("true", "false", "null"):
            tokens.append((i, text))
        else:
            tokens.append((i, text))

        i = next_pos

    return tokens


class StreamJsonParser:
    """A streaming parser for JSON data that processes input incrementally.

    This class implements a streaming JSON parser that can handle partial JSON input,
    making it suitable for processing large JSON documents or streaming data sources.
    It maintains internal state to track parsing progress and can detect both partial
    and malformed JSON.

    Attributes:
        stack (list): Tracks nested structures during parsing.
        root: The root of the parsed JSON structure.
        in_string (bool): Indicates if currently parsing a string.
        last_key: The last parsed key in an object.
        last_string_start (int): Starting position of the current string.
        last_string_end (int): Ending position of the current string.
        state: Current parser state.
        partial (bool): Indicates if the parsed JSON is incomplete.
    """

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
        if not len(json_str):
            return None

        tokens = scan(json_str)
        tokens_len = len(tokens)
        str_len = len(json_str)

        # we handle the case when the whole string is just some value not enclosed in quotes
        # example: "{"key": [ -> hello -> , 12345 -> ]}"
        if tokens_len == 0 and str_len > 0:
            if self.state is None and not self.stack:
                raise MalformedJSON(
                    "invalid json, some random value as root is invalid"
                )
            tokens.append((0, json_str))

        # check if there is a partial string after the last token index in json_str
        # if there is a pratial string, then add the `"` and it index to tokens
        has_partial_string = '"' in json_str[tokens[-1][0] + len(tokens[-1][1]) :]
        if has_partial_string:
            # get the index of the partial string
            quote_index = tokens[-1][0] + 1 + json_str[tokens[-1][0] + 1 :].index('"')
            tokens.append((quote_index, json_str[quote_index:]))
            tokens_len += 1

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
                if not self.stack or not isinstance(self.stack[-1], dict):
                    logger.error("invalid object: expected dict to close object")
                    raise MalformedJSON("invalid object: expected dict to close object")

                container = self.stack.pop()
                if not self.stack:
                    self.root = container
            elif char == "]":
                if not self.stack or not isinstance(self.stack[-1], list):
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
                if not self.partial and self.state != "comma":
                    raise MalformedJSON("invalid object: no value processed")

                self.state = "key" if isinstance(self.stack[-1], dict) else "value"
                if self.state == "key":
                    self.last_key = None
            else:
                if self.state == "key":
                    if self.partial:
                        self.partial = not char[-1] == '"'
                        self.last_key += char[:-1]
                    elif char[0] != '"':
                        logger.error("invalid key: expected string")
                        raise MalformedJSON("invalid key: expected string")
                    else:
                        self.partial = not (
                            char[0] == '"' and len(char) > 1 and char[-1] == '"'
                        )
                        if len(char) > 1:
                            self.last_key = char[1:] if self.partial else char[1:-1]
                        else:
                            self.last_key = ""

                elif self.state == "value":
                    if self.partial:
                        current_value = (
                            self.stack[-1][self.last_key]
                            if isinstance(self.stack[-1], dict)
                            else self.stack[-1][-1]
                        )
                        value = current_value + char
                        if value in ["null", "true", "false"]:
                            self.partial = False
                            if value in "null":
                                value = None
                            elif value == "true":
                                value = True
                            elif value == "false":
                                value = False
                        elif value[0] in "0123456789+-.":
                            try:
                                value = (
                                    float(value)
                                    if "e" in value.lower() or "." in value
                                    else int(value)
                                )
                                self.partial = False
                            except ValueError:
                                raise MalformedJSON("invalid number")
                        else:
                            # can be a partial string
                            self.partial = not char[-1] == '"'
                            value = char[:-1] if char[-1] == '"' else char

                        if isinstance(self.stack[-1], dict):
                            self.stack[-1][self.last_key] = (
                                self.stack[-1][self.last_key] + value
                            )
                        else:
                            self.stack[-1][-1] = self.stack[-1][-1] + value

                        # at this point the current char can be a state transition char
                        # therefore, do not move forward
                        if not self.partial:
                            self.state = "comma"

                        i += 1
                        continue

                    if char[0] == '"':
                        if len(char) < 2 or char[-1] != '"':
                            self.partial = True
                        if len(char) > 1:
                            value = char[1:] if self.partial else char[1:-1]
                        else:
                            value = ""
                    elif char == "null":
                        value = None
                    elif char == "true":
                        value = True
                    elif char == "false":
                        value = False
                    elif char[0] in "0123456789+-.":
                        try:
                            value = (
                                float(char)
                                if "e" in char.lower() or "." in char
                                else int(char)
                            )
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

                    if not self.partial:
                        self.state = "comma"
            i += 1

    def get(self) -> Union[dict[Any], list[Any], None]:
        """Returns the parsed JSON object or None if no valid JSON has been parsed.

        Returns:
            Union[dict[Any], list[Any], None]: The parsed JSON object or None if no valid JSON has been parsed.
        """
        if self.root is not None and not self.stack:
            return self.root

        if not self.stack:
            return None

        return self.stack[0]
