"""Stack-based streaming JSON parser module.

This module provides a streaming JSON parser that can process data incrementally,
making it suitable for parsing large JSON documents or streaming JSON data.
The parser maintains state between chunks of input and supports partial parsing
of JSON structures.
"""

from enum import IntEnum
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


class ParserState(IntEnum):
    """States for tracking JSON parsing context.

    This enum defines the possible states of the parser during JSON processing.
    Used to maintain the parser's position within nested JSON structures and
    determine valid next tokens.

    Attributes:
        OBJECT_WAITING_KEY: Expecting a string key in an object.
        OBJECT_WAITING_COLON: Expecting a colon after an object key.
        OBJECT_WAITING_VALUE: Expecting a value after a colon in an object.
        OBJECT_WAITING_COMMA: Expecting a comma or closing brace after a value.
        ARRAY_WAITING_VALUE: Expecting any value in an array.
        ARRAY_WAITING_COMMA: Expecting a comma or closing bracket after a value.
    """

    OBJECT_WAITING_KEY = 1
    OBJECT_WAITING_COLON = 2
    OBJECT_WAITING_VALUE = 3
    OBJECT_WAITING_COMMA = 4
    ARRAY_WAITING_VALUE = 5
    ARRAY_WAITING_COMMA = 6


Container = tuple[Union[dict, list], ParserState, Optional[str], bool]
"""Type alias for parser container state.

A tuple containing:
    - container (Union[dict, list]): The current container being parsed
    - state (ParserState): Current parsing state
    - key (Optional[str]): Current object key being processed
    - is_partial (bool): Whether the current value is partial
"""


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


class StreamJsonParser:
    """Incremental JSON parser that processes data in chunks.

    A streaming parser that can handle JSON data fed in multiple chunks, maintaining
    state between calls. Supports partial values and nested structures.

    The parser uses a stack-based approach to track nested objects and arrays,
    allowing for incremental processing of arbitrarily complex JSON structures.

    Attributes:
        buffer: Unprocessed characters from input chunks.
        stack: Stack tracking nested structures and their states.
        root: Completed top-level JSON structure, if parsing is complete.
        last_index: Position of last processed character in buffer.
        partial_token: Characters of the current token being built.
        token_type: Type of token being parsed ('string', 'number', 'literal', or None).

    Example:
        >>> parser = StreamJsonParser()
        >>> parser.consume('{"name": "Jo')
        >>> print(parser.get())  # {'name': 'Jo'}
        >>> parser.consume('hn"}')
        >>> print(parser.get())  # {'name': 'John'}
    """

    def __init__(self):
        """Initialize a new StreamJsonParser instance."""
        # The buffer of characters that haven't been tokenized yet
        self.buffer = []
        # The stack: each element is (container, context_state, last_key).
        #   - container: either a dict or a list
        #   - context_state: e.g. DICT_WAITING_KEY, LIST_WAITING_VALUE, ...
        #   - last_key: if we're in a dict and have read a key but not yet assigned the value
        self.stack: list[Container] = []
        # If we have recognized one complete top-level object/array, store it here.
        self.root = None
        self.last_index = 0
        # For partial tokens
        self.partial_token: list[
            str
        ] = []  # Characters of a token in progress (string, number, etc.)
        self.token_type: Optional[str] = (
            None  # 'string', 'number', 'true', 'false', 'null', or None if not sure
        )

    def consume(self, json_str: str) -> None:
        """Consume a chunk of JSON data for streaming parse.

        Args:
            json_str: A chunk of JSON data to process.

        Raises:
            MalformedJSON: If the JSON structure is invalid.
            PartialJSON: If the JSON data is incomplete but valid so far.

        Note:
            This method processes the input chunk and updates the internal parser state.
            It can be called multiple times with consecutive chunks of JSON data.
        """
        try:
            logger.debug({"input": json_str})
            # add to chunks
            self.buffer.extend(json_str)
            self._parse()
        except StreamParserJSONDecodeError as e:
            logger.error(e)
            raise StreamParserJSONDecodeError(e)

    def _parse(self):
        """Parse the complete JSON string in the buffer.

        This method processes the buffer character by character, handling different
        JSON elements and maintaining the parser state.

        Raises:
            MalformedJSON: If the JSON structure is invalid.
            PartialJSON: If the JSON data is incomplete but valid so far.

        Note:
            This is an internal method that implements the core parsing logic.
            It processes characters in the buffer until either:
            - The buffer is exhausted
            - A partial token is encountered
            - An error occurs
        """
        i = self.last_index
        while i < len(self.buffer):
            i = _find_non_whitespace_index(self.buffer, i)
            if i >= len(self.buffer):
                break
            current_char = self.buffer[i]

            # these are the state transition chars
            if current_char in "{[}]:,":
                # if we were processing some esle then commit
                # case for true, false, null, numbers
                if self.token_type is not None and not self._commit_token():
                    logger.error("invalid partial token before state transition")
                    raise MalformedJSON("invalid partial token before state transition")

                if current_char == "{":
                    self._start_object()
                elif current_char == "[":
                    self._start_array()
                elif current_char == "}":
                    self._end_object()
                elif current_char == "]":
                    self._end_array()
                elif current_char == ":":
                    self._dict_colon()
                else:
                    self._got_comma()

                i += 1
                continue

            # we are parsing a string
            if self.token_type == "string":
                i, completed = self._read_string(self.buffer, i)
                if completed:
                    self._commit_value("".join(self.partial_token))
                    self.token_type = None
                # we need to update current_char
                continue

            if current_char == '"':
                self.token_type = "string"
                self.partial_token = []
                i += 1
            else:
                # Possibly part of a number or 'true', 'false', 'null'
                if self.token_type is None:
                    # We need to decide the token type
                    if current_char in "-0123456789":
                        self.token_type = "number"
                        self.partial_token = []
                        continue

                    if current_char in "tfn":  # t->true, f->false, n->null
                        # We'll guess based on first letter
                        self.token_type = "literal"
                        self.partial_token = []
                        continue

                    # unrecognized start
                    raise MalformedJSON(
                        f"unrecognized start character '{current_char}'"
                    )

                completed = self._read_nonstring_char(current_char)
                if not completed:
                    # Means we cannot proceed - partial token
                    break

                i += 1

        self.last_index = i
        if self.token_type == "string":
            # we do accept partial values
            self._commit_partial_value("".join(self.partial_token))

        if self.token_type and self.token_type != "string":
            self._commit_partial_value("".join(self.partial_token))

    def _read_string(self, buffer: str, index: int) -> tuple[int, bool]:
        """Process characters in a string literal.

        Args:
            buffer: Input buffer containing the string content.
            index: Starting position in the buffer.

        Returns:
            A tuple containing:
                - The new buffer position after processing
                - Whether the string was completed (True) or partial (False)

        Note:
            Handles escape sequences and string delimiters according to JSON spec.
        """
        i = index
        while i < len(buffer):
            if buffer[i] == "\\":
                # Skip the next character as it's escaped
                self.partial_token.append(buffer[i])
                self.partial_token.append(buffer[i + 1])
                i += 2
                # we continue because we need to check for i < len(buffer)
                continue

            if buffer[i] == '"':
                return i + 1, True

            self.partial_token.append(buffer[i])
            i += 1

        return i, False

    def _start_object(self):
        """Initialize object parsing state when encountering '{'.

        Creates a new dictionary container and pushes it onto the stack.
        Updates the parser state to expect an object key or handle empty objects.

        Raises:
            MalformedJSON: If starting an object in an invalid context.
        """
        obj = {}
        # error case
        if not self.stack:
            if self.root is not None:
                logger.error("invalid object: double root")
                raise MalformedJSON("invalid object: no parent container")

            # normal case, add object and transition to wait for a key
            self.stack.append((obj, ParserState.OBJECT_WAITING_KEY, None, False))
            return

        # We are in an existing container. We add this new object as a value (or for dict).
        container, state, last_key, _ = self.stack[-1]
        if state not in [
            ParserState.OBJECT_WAITING_VALUE,
            ParserState.ARRAY_WAITING_VALUE,
        ]:
            logger.error("invalid object: unexpected state, waiting for object value")
            raise MalformedJSON(
                "invalid object: unexpected state, waiting for object value"
            )

        is_an_object = isinstance(container, dict)
        if is_an_object:
            container[last_key] = obj
        else:
            container.append(obj)

        self.stack[-1] = (
            container,
            (
                ParserState.OBJECT_WAITING_COMMA
                if is_an_object
                else ParserState.ARRAY_WAITING_COMMA
            ),
            None,
            False,
        )

        self.stack.append((obj, ParserState.OBJECT_WAITING_KEY, None, False))

    def _dict_colon(self):
        """Process a colon token in a dictionary context.

        Updates parser state after encountering a colon between key and value.

        Raises:
            MalformedJSON: If colon appears in invalid context or state.
        """
        if not self.stack:
            logger.error("invalid object: no object parent container")
            raise MalformedJSON("invalid object: no object parent container")

        container, state, last_key, is_value_partial = self.stack[-1]
        if not isinstance(container, dict):
            logger.error("invalid object: expected dict to close object")
            raise MalformedJSON("invalid object: expected dict to close object")

        if state != ParserState.OBJECT_WAITING_COLON:
            logger.error("invalid object: expected colon after object key")
            raise MalformedJSON("invalid object: expected colon after object key")

        self.stack[-1] = (
            container,
            ParserState.OBJECT_WAITING_VALUE,
            last_key,
            is_value_partial,
        )

    def _end_object(self):
        """Process the end of an object when encountering '}'.

        Validates object closure and updates parser state.

        Raises:
            MalformedJSON: If closing an object in invalid context or state.
        """
        if not self.stack:
            logger.error("invalid object: no object parent container")
            raise MalformedJSON("invalid object: no object parent container")

        container, state, _, _ = self.stack[-1]
        if not isinstance(container, dict):
            logger.error("invalid object: expected dict to close object")
            raise MalformedJSON("invalid object: expected dict to close object")

        if state not in [
            ParserState.OBJECT_WAITING_KEY,
            ParserState.OBJECT_WAITING_VALUE,
            ParserState.OBJECT_WAITING_COMMA,
        ]:
            logger.error(
                f"invalid object: expected state to be key or value or comma, but got {state}"
            )
            raise MalformedJSON(
                f"invalid object: expected state to be key or value or comma, but got {state}"
            )

        self.stack.pop()
        if not self.stack:
            self.root = container

    def _start_array(self):
        """Initialize array parsing state when encountering '['.

        Creates a new list container and pushes it onto the stack.
        Updates parser state to expect array values or handle empty arrays.

        Raises:
            MalformedJSON: If starting an array in an invalid context.
        """
        arr = []
        # error case
        if not self.stack:
            if self.root is not None:
                logger.error("invalid object: no parent container")
                raise MalformedJSON("invalid object: no parent container")

            # normal case, add object and transition to wait for a value
            self.stack.append((arr, ParserState.ARRAY_WAITING_VALUE, None, False))
            return

        container, state, last_key, _ = self.stack[-1]
        if state not in [
            ParserState.OBJECT_WAITING_VALUE,
            ParserState.ARRAY_WAITING_VALUE,
        ]:
            logger.error("invalid object: unexpected state, waiting for object value")
            raise MalformedJSON(
                "invalid object: unexpected state, waiting for object value"
            )

        is_an_obj = isinstance(container, dict)
        if is_an_obj:
            container[last_key] = arr
        else:
            container.append(arr)

        self.stack[-1] = (
            container,
            (
                ParserState.OBJECT_WAITING_COMMA
                if is_an_obj
                else ParserState.ARRAY_WAITING_COMMA
            ),
            last_key,
            False,
        )

        self.stack.append((arr, ParserState.ARRAY_WAITING_VALUE, None, False))

    def _end_array(self):
        """Process the end of an array when encountering ']'.

        Validates array closure and updates parser state.

        Raises:
            MalformedJSON: If closing an array in invalid context or state.
        """
        if not self.stack:
            logger.error("invalid object: no array parent container")
            raise MalformedJSON("invalid object: no array parent container")

        container, state, _, _ = self.stack[-1]
        if not isinstance(container, list):
            logger.error("invalid object: expected list to close array")
            raise MalformedJSON("invalid object: expected list to close array")

        if state not in [
            ParserState.ARRAY_WAITING_VALUE,
            ParserState.ARRAY_WAITING_COMMA,
        ]:
            logger.error(
                f"invalid object: expected state to be value or comma, but got {state}"
            )
            raise MalformedJSON(
                f"invalid object: expected state to be value or comma, but got {state}"
            )

        self.stack.pop()
        if not self.stack:
            self.root = container

    def _got_comma(self):
        """Process a comma token in current container context.

        Updates parser state after encountering a comma between values.

        Raises:
            MalformedJSON: If comma appears in invalid context or state.
        """
        if not self.stack:
            logger.error("invalid object: no parent container")
            raise MalformedJSON("invalid object: no parent container")

        container, state, last_key, is_value_partial = self.stack[-1]
        if state not in [
            ParserState.OBJECT_WAITING_COMMA,
            ParserState.ARRAY_WAITING_COMMA,
        ]:
            logger.error(f"invalid object: expected state to be comma, but got {state}")
            raise MalformedJSON(
                f"invalid object: expected state to be comma, but got {state}"
            )

        self.stack[-1] = (
            container,
            (
                ParserState.OBJECT_WAITING_KEY
                if isinstance(container, dict)
                else ParserState.ARRAY_WAITING_VALUE
            ),
            last_key,
            is_value_partial,
        )

    def _read_nonstring_char(self, c: str) -> bool:
        """Process a character in a non-string token context.

        Args:
            c: The character to process.

        Returns:
            bool: True if character was processed, False if token is complete.

        Raises:
            MalformedJSON: If character is invalid for current token type.

        Note:
            Handles numeric literals and JSON keywords (true, false, null).
        """
        if self.token_type == "number":
            # If it's a valid number char
            if c in "0123456789+-.eE":
                self.partial_token.append(c)

            return True

        if self.token_type == "literal":
            # possibly true/false/null
            self.partial_token.append(c)
            # Check if we definitely recognized or definitely invalid
            st = "".join(self.partial_token)
            if st in ("true", "false", "null"):
                return True  # We'll finalize in next step if we see a structural delimiter.

            # checks if the current partial token (st) could potentially become one of the valid literals.
            if not any(lit.startswith(st) for lit in ("true", "false", "null")):
                # definitely invalid
                logger.error("invalid literal: " + st)
                raise MalformedJSON("invalid literal: " + st)

            # else it might still be partial
            return True

        # unknown
        return False

    def _commit_token(self) -> bool:
        """Attempt to finalize the current partial token.

        Returns:
            bool: True if token was successfully committed, False if still partial.

        Raises:
            MalformedJSON: If token is malformed or invalid.

        Note:
            Converts string representation to appropriate Python type and
            updates the container structure with the final value.
        """
        if self.token_type == "number":
            # try to parse
            value = "".join(self.partial_token)
            # Let Python's float/int parse handle it, but watch for partial forms
            # If st is something like "12e", Python float parse fails => we call that partial or malformed?
            # We'll do a small check to see if it looks like a valid final number.
            # Easiest approach: try float(st). If it fails => malformed number, or partial?
            try:
                # Check if it's scientific notation or has decimal point
                if "e" in value.lower() or "." in value:
                    val = float(value)
                else:
                    val = int(value)
            except ValueError:
                # It's either partial or malformed. We'll treat no exponent digits, etc., as partial.
                # For the sake of demonstration, let's treat it as partial => return False => wait for more data.
                return False

            # If parse worked, we commit it as a value
            self._commit_value(val)
            self.token_type = None
            self.partial_token = []
            return True

        if self.token_type == "literal":
            value = "".join(self.partial_token)
            if value in ("true", "false", "null"):
                if value == "true":
                    val = True
                elif value == "false":
                    val = False
                else:
                    val = None
                self._commit_value(val)
                self.token_type = None
                self.partial_token = []
                return True

            # Possibly partial
            # e.g. st='fals' => partial for 'false'
            return False

        # unknown or 'string' shouldn't come here
        logger.warning(f"unknown token type {self.token_type}")
        return False

    def _commit_value(self, value: Any):
        """Add a complete value to the current container.

        Args:
            value: The Python value to add to current container.

        Raises:
            MalformedJSON: If value cannot be added in current context.

        Note:
            Updates container and parser state after adding the value.
        """
        if not self.stack:
            logger.error("invalid json, any value cannot be a root element.")
            raise MalformedJSON("invalid json, any value cannot be a root element.")

        container, state, last_key, is_value_partial = self.stack[-1]
        if isinstance(container, dict):
            if state == ParserState.OBJECT_WAITING_KEY:
                self.stack[-1] = (
                    container,
                    ParserState.OBJECT_WAITING_COLON,
                    value,
                    False,
                )
                return

            if state == ParserState.OBJECT_WAITING_VALUE:
                # if there are partial values, then simply overwrite
                container[last_key] = value
                self.stack[-1] = (
                    container,
                    ParserState.OBJECT_WAITING_COMMA,
                    None,
                    False,
                )
                return

            logger.error(f"not expecting an object value, current state {state}")
            raise MalformedJSON(f"not expecting an object value, current state {state}")

        if state != ParserState.ARRAY_WAITING_VALUE:
            logger.error(f"not expecting an array value, current state {state}")
            raise MalformedJSON(f"not expecting an array value, current state {state}")

        if is_value_partial and len(container) == 0:
            logger.error("we have partial values but no values in array")
            raise StreamJsonParser("we have partial values but no values in array")

        if is_value_partial:
            container[-1] = value
        else:
            container.append(value)

        self.stack[-1] = (container, ParserState.ARRAY_WAITING_COMMA, None, False)

    def _commit_partial_value(self, value: Any):
        """Add or update a partial value in the current container.

        Args:
            value: The partial Python value to add/update.

        Raises:
            MalformedJSON: If value cannot be added in current context.

        Note:
            Handles string concatenation for partial string values and
            maintains partial state for container.
        """
        if not self.stack:
            logger.error("invalid json, any value cannot be a root element.")
            raise MalformedJSON("invalid json, any value cannot be a root element.")

        container, state, last_key, is_value_partial = self.stack[-1]
        if isinstance(container, dict):
            if state == ParserState.OBJECT_WAITING_KEY:
                # we do nothing, we dont partially commit a key
                return

            if state == ParserState.OBJECT_WAITING_VALUE:
                if is_value_partial and last_key in container:
                    container[last_key] += value
                else:
                    container[last_key] = value

                # update is_value_partial
                self.stack[-1] = (container, state, last_key, True)
                return

            logger.error(f"not expecting an object value, current state {state}")
            raise MalformedJSON(f"not expecting an object value, current state {state}")

        if state != ParserState.ARRAY_WAITING_VALUE:
            logger.error(f"not expecting an array value, current state {state}")
            raise MalformedJSON(f"not expecting an array value, current state {state}")

        if is_value_partial and len(container) > 0:
            container[-1] += value
        else:
            container.append(value)

        # update is_value_partial
        self.stack[-1] = (container, state, last_key, True)

    def get(self) -> Any:
        """Retrieve the current parse result.

        Returns:
            The parsed JSON structure, which could be:
                - Complete top-level structure if parsing is done
                - Partial structure if parsing is incomplete
                - None if no structure has been recognized yet

        Note:
            The returned structure may contain partial values if parsing
            is incomplete. Partial values are represented as they were
            received in the input chunks.
        """
        # If we have a finalized root and no stack, that's a fully closed top-level object/array
        if self.root is not None and not self.stack:
            return self.root

        if not self.stack:
            # no partial structure
            return None

        # Rebuild partial structure from top-level of stack
        # In standard JSON, there's only one top-level container anyway => stack[0]
        top_container, _, _, _ = self.stack[0]
        # But the container itself is partially or fully built. Because we hold references,
        # it includes nested partial structures as well. So returning top_container is enough.
        # The only difference: Some key might not be "committed" if we haven't seen a colon, etc.
        # We have *not* stored partial keys => so they're absent in the dict.
        # Partial string values are present in the dict or list.
        return top_container
