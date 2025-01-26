"""JSON Stream Parser Module.

This module provides functionality for parsing JSON data in a streaming fashion,
allowing for partial JSON processing and validation.

The solutions is based on 2 pointers, and json flow specification
- i points to a valid json
- j points to subsequent characters from i

Classes:
    JSONDecodeError: Base class for JSON parsing errors.
    PartialJSON: Error for incomplete JSON data.
    MalformedJSON: Error for invalid JSON format.
    StreamJsonParser: Main class for streaming JSON parsing.
"""

import json
from typing import Any, Literal, Optional, Union

from config import logger

# possible parse return values are
# - tuple with index and (parsed value or True).
# - tuple with index and True
# - False if no further parsing is possible
# - True means, is a valid json therefore close it.
ParseResult = Union[tuple[int, Optional[str], Literal[True]], Literal[False]]


class StreamParserJSONDecodeError(ValueError):
    """Base class for JSON parsing errors."""
    pass


class PartialJSON(StreamParserJSONDecodeError):
    """Error for incomplete JSON data."""
    pass


class MalformedJSON(StreamParserJSONDecodeError):
    """Error for invalid JSON format."""
    pass


def _find_non_whitespace_index(json_str: str, from_index: int = 0) -> int:
    """Find the index of the first non-whitespace character.

    Args:
        json_str: String to search for non-whitespace characters.
        from_index: Starting index for the search (default: 0).

    Returns:
        int: Index of the first non-whitespace character.
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
        self.current_valid_json: str = ""

    def consume(self, json_str: str) -> None:
        """Consume a chunk of JSON data.

        Args:
            json_str: A string containing a chunk of JSON data.

        Raises:
            JSONDecodeError: If the JSON data is invalid or malformed.
        """
        try:
            logger.debug({"input": json_str})
            # add to chunks
            self.chunks.append(json_str)
            self._parse("".join(self.chunks))
        except StreamParserJSONDecodeError as e:
            logger.error(e)
            raise StreamParserJSONDecodeError(e)

    def _parse(self, json_str: str) -> None:
        """Parse the complete JSON string.

        Args:
            json_str: The complete JSON string to parse.

        Raises:
            MalformedJSON: If the JSON string doesn't start with { or [.
        """
        if not json_str:
            return

        if json_str[0] != "{" and json_str[0] != "[":
            self.chunks = []
            raise MalformedJSON("json must start with { or [")

        i, last_char, _ = self._parse_value(json_str)
        self.current_valid_json = f"{json_str[:i]}{last_char}"

    def _parse_value(self, json_str: str) -> ParseResult:
        """Parse a JSON value.

        Args:
            json_str: The JSON string to parse.

        Returns:
            ParseResult: A tuple containing the parsing result:
                - If parsing is complete: (index, None, True)
                - If parsing is partial: (index, closing_char, False)
                - If parsing failed: False

        Raises:
            MalformedJSON: If the JSON string doesn't follow JSON specification.
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

        if current_char in "0123456789-":
            # JSON flow, number
            return self._parse_numbers(json_str)

        raise MalformedJSON(f"string {json_str} does not follow json spec")

    def _parse_object(self, json_str: str) -> ParseResult:
        """Parse a JSON object.

        Args:
            json_str: The JSON string to parse.

        Returns:
            ParseResult: A tuple containing the parsing result:
                - If parsing is complete: (index, None, True)
                - If parsing is partial: (index, closing_chars, False)
                - If parsing failed: False

        Raises:
            MalformedJSON: If the JSON string doesn't follow JSON specification.
            IndexError: If the JSON string is incomplete.
        """
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
                    # we close the current object
                    return j, "}", True

                # JSON flow string (key)
                sj, last_char, is_closed = self._parse_string(json_str[j:])
                if not is_closed:
                    # close it from i, meaning, forget all that comes after i
                    return i, "}", False

                # advanced over the whole string
                j += sj + 1

                # JSON flow, whitespace
                j = _find_non_whitespace_index(json_str, from_index=j)
                # JSON flow, colon
                if json_str[j] != ":":
                    raise MalformedJSON(f"string {json_str} does not follow json spec")

                j += 1
                # JSON flow, whitespace
                j = _find_non_whitespace_index(json_str, from_index=j)

                # JSON flow, value
                sj, last_char, closed = self._parse_value(json_str[j:])
                if not closed:
                    # we can have impartial values
                    close_str = "{}{}".format(last_char, "}") if last_char else "}"
                    return j + sj, close_str, False

                j += sj + 1
                # at this point we have a value, therefore, we can add the key and value to the response
                # update i so we can include the new key value.
                i = j

                # JSON flow, whitespace
                j = _find_non_whitespace_index(json_str, from_index=j)
                # JSON flow, comma or closed brace
                if json_str[j] != "," and json_str[j] != "}":
                    raise MalformedJSON(
                        f"string {json_str} shall be comma or close brace"
                    )

                if json_str[j] == "}":
                    return j, "}", True

                # keep moving, another round of object flow
                j += 1

        except IndexError:
            # When the value type of the key is not known, then we close the current object
            return i, "}", True

    def _parse_array(self, json_str: str) -> ParseResult:
        """Parse a JSON array value.
        
        This method handles parsing of JSON arrays, including partial arrays.
        It supports both complete and incomplete array inputs, maintaining
        state between partial inputs.

        Args:
            json_str: The JSON string to parse.

        Returns:
            ParseResult: A tuple containing the parsing result:
                - If parsing is complete: (index, closing_chars, True)
                - If parsing is partial: (index, closing_chars, False)
                - If parsing failed: False

        Raises:
            MalformedJSON: If the JSON string doesn't follow JSON specification.
            IndexError: If the JSON string is incomplete.
        """
        i = 1
        j = 1
        try:
            while True:
                j = _find_non_whitespace_index(json_str, from_index=j)
                current_char = json_str[j]

                if current_char == "]":
                    return j, "]", True

                sj, last_char, is_closed = self._parse_value(json_str[j:])
                if not is_closed:
                    return j + sj, "{}{}".format(last_char, "]"), False

                j += sj + 1
                # at this point we have a value, therefore, we can add the key and value to the response
                # update i so we can include the new key value.
                i = j

                # JSON flow, whitespace
                j = _find_non_whitespace_index(json_str, from_index=j)
                # JSON flow, comma or closed bracket
                if json_str[j] == "]":
                    return i, "]", True

                if json_str[j] == ",":
                    j += 1
                else:
                    raise MalformedJSON(
                        f"string {json_str} shall be comma or close bracket"
                    )
        
        except IndexError:
            return i, "]", False

    def _parse_string(self, json_str: str) -> ParseResult:
        """Parse a JSON string value.

        This method handles parsing of JSON string values, including escaped characters
        like \n, \t, \r, \", etc. It properly skips over escaped characters when
        looking for the string terminator.

        Args:
            json_str: The JSON string to parse.

        Returns:
            ParseResult: A tuple containing the parsing result:
                - If parsing is complete: (index, None, True)
                - If parsing is partial: (index, '"', False)
                - If parsing failed: False

        Todo:
            * Add validation for escaped string values (\\uXXXX)
        """
        i = 1
        while i < len(json_str):
            # Check for escape character
            if json_str[i] == '\\':
                # Skip the next character as it's escaped
                i += 2
                continue
            
            if json_str[i] == '"':
                return i, None, True

            i += 1
        return i, '"', False

    def _parse_numbers(self, json_str: str) -> ParseResult:
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

    def get(self) -> Optional[dict[str, Any]]:
        """Get the current valid JSON object.

        Returns:
            Optional[dict[str, Any]]: The parsed JSON object if available,
                None otherwise.
        """
        if not self.current_valid_json:
            return None
        try:
            return json.loads(self.current_valid_json)
        except json.decoder.JSONDecodeError as e:
            msg = "we received an invlaid json from the stream"
            logger.error(msg)
            raise StreamParserJSONDecodeError(msg)
