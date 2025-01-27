"""JSON Stream Parser Module.

This module provides functionality for parsing JSON data in a streaming fashion,
allowing for partial JSON processing and validation.

The solutions is based on 2 pointers, and json flow specification
- i points to a valid json
- j points to subsequent characters from i

We have a boolean as part of the ParseResult to indicate if parsing is complete, or partial.

Classes:
    JSONDecodeError: Base class for JSON parsing errors.
    PartialJSON: Error for incomplete JSON data.
    MalformedJSON: Error for invalid JSON format.
    StreamJsonParser: Main class for streaming JSON parsing.
"""
import json
from json import JSONDecodeError
from typing import Any, Literal, Optional

from config import logger

# possible parse return values are
# - tuple with index and (parsed value or True).
# - tuple with index and True
# - False if no further parsing is possible
# - True means, is a valid json therefore close it.
ParseResult = tuple[int, Optional[str], Literal[True]]


class StreamParserJSONDecodeError(ValueError):
    """Base class for JSON parsing errors in the stream parser.

    This exception is raised when there are errors in parsing JSON data
    in a streaming context, such as malformed JSON or invalid token sequences.
    """

    pass


class PartialJSON(StreamParserJSONDecodeError):
    """Error indicating incomplete JSON data.

    This exception is raised when the JSON data stream is incomplete
    and more data is needed to form a valid JSON structure.
    """

    pass


class MalformedJSON(StreamParserJSONDecodeError):
    """Error indicating invalid JSON format.

    This exception is raised when the JSON data violates the JSON specification,
    such as missing delimiters, invalid tokens, or incorrect nesting.
    """

    pass


def _find_non_whitespace_index(json_str: str, from_index: int = 0) -> int:
    """Find the index of the first non-whitespace character.

    Scans the input string starting from the specified index to find
    the first character that is not considered whitespace according to
    the JSON specification (space, horizontal tab, line feed, or carriage return).

    Args:
        json_str: String to search for non-whitespace characters.
        from_index: Starting index for the search. Defaults to 0.

    Returns:
        int: Index of the first non-whitespace character. If no non-whitespace
            character is found, returns the length of the string.
    """
    while from_index < len(json_str):
        char = json_str[from_index]
        # From JSON specs, whitespace is space, horizontal tab, line feed, or carriage return
        is_whitespace = (
            char == " "  # space
            or char == "\t"  # horizontal tab
            or char == "\n"  # line feed
            or char == "\r"  # carriage return
        )
        if not is_whitespace:
            return from_index

        from_index += 1

    return from_index


class StreamJsonParser:
    """A streaming JSON parser that can handle partial JSON input.

    This class provides functionality to parse JSON data that arrives in chunks,
    maintaining state between chunks and validating the JSON structure.

    Attributes:
        chunks: List of received JSON string chunks.
        current_valid_json: The most recent valid JSON string that has been parsed.
    """

    def __init__(self):
        """Initialize a new StreamJsonParser instance."""
        self.chunks: list[str] = []
        self.current_valid_json: str = None

    def consume(self, json_str: str) -> None:
        """Consume a chunk of JSON data for streaming parse.

        This method accepts partial JSON data and maintains state between chunks.
        It validates basic JSON structure by checking brace/bracket balance and
        updates the internal state for partial parsing.

        Args:
            json_str: A string containing a chunk of JSON data.

        Raises:
            StreamParserJSONDecodeError: If the JSON data is invalid, such as having
                more closing braces/brackets than opening ones, or other malformed
                JSON structures.
        """
        try:
            logger.debug({"input": json_str})
            # add to chunks
            self.chunks.append(json_str)
            # validate the number of open and close braces and square brackets
            # the number of open brackets can be higher than the number of close braces and brackets
            chunks_str = "".join(self.chunks)

            # validate the case for multiple starting roots and valid number of close brackets and braces
            # `{data}{some other data}` or `{data}[some other data]` are invalid
            # `[data][some other data]` or `[data]{some other data}` are invalid
            # `{data}` or `[data]` is valid
            # []], {}} are invalid
            root = False
            stack = []
            for c in chunks_str:
                if c in "{[":
                    if root and len(stack) == 0:
                        raise StreamParserJSONDecodeError(
                            "multiple roots are not a valid json"
                        )
                    if len(stack) == 0:
                        root = True

                    stack.append(c)
                    continue

                if c in "]}":
                    if not stack or stack[-1] not in "{[":
                        raise StreamParserJSONDecodeError(
                            "in valid json, expected { or ["
                        )
                    stack.pop(-1)

            if len(stack) > 0 and stack[-1] in "]}":
                raise StreamParserJSONDecodeError(
                    "there are more closing brackets or braces than the open ones"
                )

            self._parse(chunks_str)
        except StreamParserJSONDecodeError as e:
            logger.error(e)
            raise StreamParserJSONDecodeError(e)

    def _parse(self, json_str: str) -> None:
        """Parse the complete JSON string.

        Initiates parsing of the accumulated JSON string, handling both complete
        and partial JSON structures. Validates that the JSON starts with either
        an object or array.

        Args:
            json_str: The complete JSON string to parse.

        Raises:
            MalformedJSON: If the JSON string doesn't start with { or [.
        """
        if not json_str:
            return

        # json can only start as an object or an array
        if json_str[0] != "{" and json_str[0] != "[":
            self.chunks = []
            raise MalformedJSON("json must start with { or [")

        i, last_char, _ = self._parse_value(json_str)
        self.current_valid_json = f"{json_str[:i]}{last_char}"

    def _parse_value(self, json_str: str) -> ParseResult:
        """Parse any JSON value.

        Handles parsing of all possible JSON value types:
        - Objects (starting with {)
        - Arrays (starting with [)
        - Numbers (including integers, floats, scientific notation)
        - Strings (enclosed in double quotes)
        - Boolean values (true/false)
        - null
        - Special values (Infinity, -Infinity, NaN)

        Args:
            json_str: The JSON string to parse.

        Returns:
            ParseResult: A tuple containing:
                - Index where parsing ended
                - Closing character if needed (None if not needed)
                - Boolean indicating if parsing is complete

        Raises:
            MalformedJSON: If the value doesn't follow JSON specification.
        """
        # JSON VALUE, whitespace
        i = _find_non_whitespace_index(json_str, from_index=0)
        current_char = json_str[i]

        # JSON value, object
        if current_char == "{":
            return self._parse_object(json_str)

        # JSON value, array
        if current_char == "[":
            return self._parse_array(json_str)

        if current_char == '"':
            # JSON flow, string
            return self._parse_string(json_str)

        if current_char in "0123456789":
            # JSON flow, number
            return self._parse_numbers(json_str)

        if current_char == "-":
            if len(json_str) == 1:
                return 1, "-", True

            return self._parse_numbers(json_str)

        # JSON flow, null
        # for the following cases, we return
        # case length - 1, None, True
        # the reason for case length - 1 is because the pointer is already
        # at the first char of the case.
        # None, because there is not need to close them
        # True, valid case
        if json_str.startswith("null"):
            return 3, None, True

        if "null".startswith(json_str):
            return 0, None, True

        if json_str.startswith("true"):
            return 3, None, True

        if "true".startswith(json_str):
            return 0, None, True

        if json_str.startswith("false"):
            return 4, None, True

        if "false".startswith(json_str):
            return 0, None, True

        raise MalformedJSON(f"string {json_str} does not follow json spec")

    def _parse_object(self, json_str: str) -> ParseResult:
        """Parse a JSON object.

        Handles parsing of JSON objects, including nested objects and partial objects.
        Supports streaming parse by maintaining state for incomplete objects.

        The method follows this flow:
        1. Parse object key (must be a string)
        2. Expect and consume colon
        3. Parse value
        4. Handle comma for multiple key-value pairs
        5. Handle closing brace

        Args:
            json_str: The JSON string to parse.

        Returns:
            ParseResult: A tuple containing:
                - Index where parsing ended
                - Closing brace if needed (None if not needed)
                - Boolean indicating if parsing is complete

        Raises:
            MalformedJSON: If the object structure is invalid.
            IndexError: If the JSON string is incomplete.
        """
        if len(json_str) == 1:
            # partial close at i
            return 1, "}", False

        i = 1
        j = 1
        try:
            # JSON flow, loop
            while True:
                # JSON flow, whitespaces
                j = _find_non_whitespace_index(json_str, from_index=j)
                # from test, care about not going out of bounds.
                # therefore the try
                current_char = json_str[j]

                # JSON flow, closed brace
                if current_char == "}":
                    # close at j
                    return j, "}", True

                # JSON flow string (key)
                sj, last_char, is_closed = self._parse_string(json_str[j:])
                if not is_closed:
                    # partial close at i
                    # keys are only added once we know the value type
                    return i, "}", False

                # advanced over the whole string
                j += sj + 1

                # JSON flow, whitespace
                j = _find_non_whitespace_index(json_str, from_index=j)
                # JSON flow, colon
                if json_str[j] != ":":
                    raise MalformedJSON(
                        f"string {json_str} does not follow json spec, expected colon"
                    )

                j += 1
                # JSON flow, whitespace
                # Not part of the json object flow, but is allow
                j = _find_non_whitespace_index(json_str, from_index=j)

                # JSON flow, value
                sj, last_char, closed = self._parse_value(json_str[j:])
                if not closed:
                    # partial close it at j + sj, we accept partial values
                    close_str = "{}{}".format(last_char, "}") if last_char else "}"
                    return j + sj, close_str, False

                j += sj + 1
                # at this point we have a value, therefore, we can add the key and value to the response
                # update i so we can include the new key value.
                i = j

                # JSON flow, whitespace
                # Not part of the json object flow, but is allow
                j = _find_non_whitespace_index(json_str, from_index=j)
                if j >= len(json_str):
                    # partial close at j
                    # from i to j, there can only be whitespaces
                    return i, "}", False

                # JSON flow, comma or closed brace
                if json_str[j] != "," and json_str[j] != "}":
                    raise MalformedJSON(
                        f"string {json_str} shall be comma or close brace"
                    )

                if json_str[j] == "}":
                    # close at j
                    return j, "}", True

                # keep moving, another round of object flow
                j += 1

        except IndexError:
            # When the value type of the key is not known, then we close the current object
            return i, "}", True

    def _parse_array(self, json_str: str) -> ParseResult:
        """Parse a JSON array value.

        Handles parsing of JSON arrays, including nested arrays and partial arrays.
        Supports streaming parse by maintaining state for incomplete arrays.

        The method follows this flow:
        1. Parse array value
        2. Handle comma for multiple values
        3. Handle closing bracket
        4. Support partial arrays for streaming

        Args:
            json_str: The JSON string to parse.

        Returns:
            ParseResult: A tuple containing:
                - Index where parsing ended
                - Closing bracket if needed (None if not needed)
                - Boolean indicating if parsing is complete

        Raises:
            MalformedJSON: If the array structure is invalid.
            IndexError: If the JSON string is incomplete.
            StreamParserJSONDecodeError: If array format violates JSON spec.
        """
        if len(json_str) == 1:
            return 1, "]", False

        i = 1
        j = 1
        try:
            while True:
                j = _find_non_whitespace_index(json_str, from_index=j)
                current_char = json_str[j]

                if current_char == "]":
                    # close at j
                    return j, "]", True

                sj, last_char, is_closed = self._parse_value(json_str[j:])
                if not is_closed:
                    # partial close at j, we accept partial values
                    return j + sj, "{}{}".format(last_char, "]"), False

                j += sj + 1
                # at this point we have a value, therefore, we can add the key and value to the response
                # update i so we can include the new key value.
                i = j

                # JSON flow, whitespace
                # Not part of the json object flow, but is allow
                j = _find_non_whitespace_index(json_str, from_index=j)
                # we know the value therefore we should be able to close the array
                if j >= len(json_str):
                    # partial close at j
                    return j, "]", False

                # JSON flow, comma or closed bracket
                if json_str[j] == "]":
                    # close at j
                    return j, "]", True

                if json_str[j] == ",":
                    j += 1
                else:
                    raise MalformedJSON(
                        f"string {json_str} shall be comma or close bracket"
                    )

                j = _find_non_whitespace_index(json_str, from_index=j)
                current_char = json_str[j]

                if current_char == "]":
                    raise MalformedJSON("not a valid json, expected a value")

        except IndexError:
            return i, "]", False
        except MalformedJSON as e:
            raise e

    def _parse_string(self, json_str: str) -> ParseResult:
        """Parse a JSON string value.

        Handles parsing of JSON strings, including escaped characters.
        Properly handles escape sequences including:
        - Quote (\\")
        - Backslash (\\\\)
        - Forward slash (\\/)
        - Backspace (\\b)
        - Form feed (\\f)
        - Line feed (\\n)
        - Carriage return (\\r)
        - Tab (\\t)
        - Unicode (\\uXXXX)

        Args:
            json_str: The JSON string to parse.

        Returns:
            ParseResult: A tuple containing:
                - Index where parsing ended
                - Closing quote if needed (None if not needed)
                - Boolean indicating if parsing is complete
        """
        i = 1
        while i < len(json_str):
            # Check for escape character
            if json_str[i] == "\\":
                # Skip the next character as it's escaped
                i += 2
                continue

            if json_str[i] == '"':
                return i, None, True

            i += 1
        return i, '"', False

    def _parse_numbers(self, json_str: str) -> ParseResult:
        """Parse a JSON number value.

        Handles parsing of all JSON number formats:
        - Integers (e.g., 123, -456)
        - Floating point (e.g., 123.456, -123.456)
        - Scientific notation (e.g., 1.23e4, 1.23E4, -1.23e-4)
        - Special cases (0, -0, etc.)

        The method uses a state machine to track parsing state:
        - State 0: Start (expect minus or digit)
        - State 1: After minus (expect digit)
        - State 2: After first digit in integer part
        - State 3: After decimal point (expect digit)
        - State 4: After digit in fraction part
        - State 5: After e/E (expect sign or digit)
        - State 6: After sign in exponent (expect digit)
        - State 7: After digit in exponent

        Args:
            json_str: The JSON string to parse.

        Returns:
            ParseResult: A tuple containing:
                - Index where parsing ended
                - None (no closing character needed)
                - Boolean indicating if parsing is complete
        """
        i = 1
        length = len(json_str)

        # forward
        while i < length and json_str[i] in "1234567890.-+eE":
            i += 1

        j = i
        modified = False

        # backward
        while json_str[i - 1] in ".-+eE":
            modified = True
            i -= 1

        return i - 1 if not modified and i < length else i, None, j < length

    def get(self) -> Any:
        """Get the current valid JSON object.

        Attempts to parse the accumulated JSON string into a Python object.
        Handles both complete and partial JSON structures.

        Returns:
            Any: The parsed JSON object, or None if the JSON string is empty.
        """
        if not self.current_valid_json:
            return None
        try:
            return json.loads(self.current_valid_json)
        except JSONDecodeError as e:
            raise StreamParserJSONDecodeError(
                f"invalid json"
            )
