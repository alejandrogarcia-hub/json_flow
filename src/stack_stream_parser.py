from enum import IntEnum
from typing import Any, Optional, Union

from config import logger


class StreamParserJSONDecodeError(ValueError):
    """Base class for JSON parsing errors in the stream parser.

    This is the parent class for all JSON parsing related exceptions
    in the streaming parser implementation.
    """

    pass


class PartialJSON(StreamParserJSONDecodeError):
    """Error indicating incomplete JSON data.

    Raised when the parser encounters the end of input while
    in the middle of a valid JSON structure.
    """

    pass


class MalformedJSON(StreamParserJSONDecodeError):
    """Error indicating invalid JSON format.

    Raised when the parser encounters JSON that violates the
    JSON specification, such as invalid literals or mismatched
    brackets.
    """

    pass


class ParserState(IntEnum):
    """Enum representing different states during JSON parsing.

    Attributes:
        OBJECT_WAITING_KEY: Parser expects a dictionary key.
        OBJECT_WAITING_COLON: Parser expects a colon after key.
        OBJECT_WAITING_VALUE: Parser expects a value in dictionary.
        OBJECT_WAITING_COMMA: Parser expects a comma or end of dictionary.
        ARRAY_WAITING_VALUE: Parser expects a value in array.
        ARRAY_WAITING_COMMA: Parser expects a comma or end of array.
    """

    OBJECT_WAITING_KEY = 1
    OBJECT_WAITING_COLON = 2
    OBJECT_WAITING_VALUE = 3
    OBJECT_WAITING_COMMA = 4
    ARRAY_WAITING_VALUE = 5
    ARRAY_WAITING_COMMA = 6


class Container:
    """Container class for tracking JSON object/array parsing state.

    Args:
        container (Union[dict, list]): The container object (dict or list).
        state (ParserState): Current parsing state for this container.
        last_key (Optional[str]): Last parsed key in dictionary context.
        last_value_partial (Optional[bool]): Whether last value was partial.

    Attributes:
        container (Union[dict, list]): The container object being built.
        state (ParserState): Current parsing state.
        last_key (Optional[str]): Most recently parsed key (for dictionaries).
        last_value_partial (Optional[bool]): Tracks if last value was partial.
    """

    def __init__(
        self,
        container: Union[dict | list],
        state: ParserState,
        last_key: Optional[str],
        last_value_partial: Optional[bool] = False,
    ) -> None:
        """
        container: object or array
        state: current state
        last_key: last key in dictionary
        """
        self.container = container
        self.state = state
        self.last_key = last_key
        self.last_value_partial = last_value_partial


def _find_non_whitespace_index(buffer: [], index: int) -> int:
    """Find the index of the first non-whitespace character.

    Scans the input string starting from the specified index to find
    the first character that is not considered whitespace according to
    the JSON specification (space, horizontal tab, line feed, or carriage return).

    Args:
        buffer: Array of chars
        index: Starting index for the search. Defaults to 0.

    Returns:
        int: Index of the first non-whitespace character. If no non-whitespace
            character is found, returns the length of the string.
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
    """A single-pass, stack-based streaming JSON parser.

    This parser processes JSON data incrementally, maintaining state between chunks
    of input. It uses a stack-based approach to track nested structures and their
    parsing states.

    Attributes:
        buffer (list): Characters that haven't been tokenized yet.
        stack (list[Container]): Stack of containers (dict/list) with their states.
        root (Any): Completed top-level object/array, if one exists.
        last_index (int): Last processed index in the buffer.
        in_string (bool): Whether currently reading a string literal.
        string_delim (str): String delimiter (always " in JSON).
        unicode_esc (bool): Whether parsing a "\\u" escape sequence.
        esc_count (int): Number of hex digits read in unicode escape.
        partial_token (list[str]): Characters of token being processed.
        token_type (Optional[str]): Current token type ('string', 'number', etc.).
        partial_key (Optional[str]): Partially recognized dictionary key.
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
        self.in_string: bool = False  # Are we currently reading a string literal?
        self.string_delim: str = (
            '"'  # Only double quotes in JSON, but left as a variable for clarity
        )
        self.unicode_esc: bool = False  # Are we parsing a "\u" escape?
        self.esc_count: int = 0  # How many hex digits read in a unicode escape
        self.partial_token: list[
            str
        ] = []  # Characters of a token in progress (string, number, etc.)
        self.token_type: Optional[str] = (
            None  # 'string', 'number', 'true', 'false', 'null', or None if not sure
        )

        # For partial recognized name in dictionary
        self.partial_key: Optional[str] = None

    def consume(self, json_str: str) -> None:
        """Consume a chunk of JSON data for streaming parse.

        Args:
            json_str (str): A chunk of JSON data to process.

        Raises:
            MalformedJSON: If the JSON structure is invalid.
            PartialJSON: If the JSON data is incomplete but valid so far.
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
            if self.in_string:
                i, completed = self._read_string(self.buffer, i)
                if completed:
                    self._end_string()
                # we need to update current_char
                continue

            if current_char == '"':
                self._start_string()
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
        if self.in_string:
            # we do accept partial values
            self._commit_partial_value("".join(self.partial_token))

        if self.token_type and self.token_type != "string":
            self._commit_partial_value("".join(self.partial_token))

    def _start_string(self):
        """Initialize string parsing state when encountering a quote.

        Sets up the parser state for processing a string literal, including
        resetting relevant flags and buffers.
        """
        self.in_string = True
        self.token_type = "string"
        self.partial_token = []

    def _end_string(self):
        self.in_string = False
        self._commit_value("".join(self.partial_token))
        self.token_type = None

    def _read_string(self, buffer: str, index: int) -> tuple[int, bool]:
        """Process characters in a string literal.

        Args:
            buffer (str): Input buffer containing the string content.
            index (int): Starting position in the buffer.

        Returns:
            tuple[int, bool]: A tuple containing:
                - The new buffer position after processing
                - Whether the string was completed (True) or partial (False)
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
        """
        obj = {}
        # error case
        if not self.stack:
            if self.root is not None:
                logger.error("invalid object: double root")
                raise MalformedJSON("invalid object: no parent container")

            # normal case, add object and transition to wait for a key
            self.stack.append(Container(obj, ParserState.OBJECT_WAITING_KEY, None))
            return

        # We are in an existing container. We add this new object as a value (or for dict).
        container = self.stack[-1]
        if container.state not in [
            ParserState.OBJECT_WAITING_VALUE,
            ParserState.ARRAY_WAITING_VALUE,
        ]:
            raise MalformedJSON(
                "invalid object: unexpected state, waiting for object value"
            )

        is_an_object = isinstance(container.container, dict)
        if is_an_object:
            container.container[container.last_key] = obj
        else:
            container.container.append(obj)

        self.stack[-1] = Container(
            container.container,
            ParserState.OBJECT_WAITING_COMMA
            if is_an_object
            else ParserState.ARRAY_WAITING_COMMA,
            None,
        )

        self.stack.append(Container(obj, ParserState.OBJECT_WAITING_KEY, None))

    def _dict_colon(self):
        if not self.stack:
            raise MalformedJSON("invalid object: no object parent container")

        container = self.stack[-1]
        if not isinstance(container.container, dict):
            raise MalformedJSON("invalid object: expected dict to close object")

        if container.state != ParserState.OBJECT_WAITING_COLON:
            raise MalformedJSON("invalid object: expected colon after object key")

        self.stack[-1].state = ParserState.OBJECT_WAITING_VALUE

    def _end_object(self):
        if not self.stack:
            raise MalformedJSON("invalid object: no object parent container")

        container = self.stack[-1]
        if not isinstance(container.container, dict):
            raise MalformedJSON("invalid object: expected dict to close object")

        if container.state not in [
            ParserState.OBJECT_WAITING_KEY,
            ParserState.OBJECT_WAITING_VALUE,
            ParserState.OBJECT_WAITING_COMMA,
        ]:
            raise MalformedJSON(
                f"invalid object: expected state to be key or value or comma, but got {container.state}"
            )

        self.stack.pop()
        if not self.stack:
            self.root = container.container

    def _start_array(self):
        arr = []
        # error case
        if not self.stack:
            if self.root is not None:
                logger.error("invalid object: double root")
                raise MalformedJSON("invalid object: no parent container")

            # normal case, add object and transition to wait for a value
            self.stack.append(Container(arr, ParserState.ARRAY_WAITING_VALUE, None))
            return

        container = self.stack[-1]
        if container.state not in [
            ParserState.OBJECT_WAITING_VALUE,
            ParserState.ARRAY_WAITING_VALUE,
        ]:
            raise MalformedJSON(
                "invalid object: unexpected state, waiting for object value"
            )

        is_an_obj = isinstance(container.container, dict)
        if is_an_obj:
            container.container[container.last_key] = arr
        else:
            container.container.append(arr)

        self.stack[-1].state = (
            ParserState.OBJECT_WAITING_COMMA
            if is_an_obj
            else ParserState.ARRAY_WAITING_COMMA
        )

        self.stack.append(Container(arr, ParserState.ARRAY_WAITING_VALUE, None))

    def _end_array(self):
        if not self.stack:
            raise MalformedJSON("invalid object: no array parent container")

        container = self.stack[-1]
        if not isinstance(container.container, list):
            raise MalformedJSON("invalid object: expected list to close array")

        if container.state not in [
            ParserState.ARRAY_WAITING_VALUE,
            ParserState.ARRAY_WAITING_COMMA,
        ]:
            raise MalformedJSON(
                f"invalid object: expected state to be value or comma, but got {container.state}"
            )

        self.stack.pop()
        if not self.stack:
            self.root = container.container

    def _got_comma(self):
        if not self.stack:
            raise MalformedJSON("invalid object: no parent container")

        container = self.stack[-1]
        if container.state not in [
            ParserState.OBJECT_WAITING_COMMA,
            ParserState.ARRAY_WAITING_COMMA,
        ]:
            raise MalformedJSON(
                f"invalid object: expected state to be comma, but got {container.state}"
            )

        self.stack[-1].state = (
            ParserState.OBJECT_WAITING_KEY
            if isinstance(container.container, dict)
            else ParserState.ARRAY_WAITING_VALUE
        )

    def _read_nonstring_char(self, c: str) -> bool:
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
        """
        We have a partial token in self.partial_token, type in self.token_type.
        We'll try to finalize it as a number or true/false/null. Then we attach it.
        Return True if success, False if we cannot finalize it yet (partial).
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
        return False

    def _commit_string(self, value: str):
        if not self.stack:
            raise MalformedJSON("invalid json, string cannot be a root element.")

        container = self.stack[-1]
        if isinstance(container.container, dict):
            if container.state == ParserState.OBJECT_WAITING_KEY:
                self.stack[-1] = Container(
                    container.container, ParserState.OBJECT_WAITING_COLON, value
                )
                return

            if container.state == ParserState.OBJECT_WAITING_VALUE:
                container.container[container.last_key] = value
                self.stack[-1] = Container(
                    container.container, ParserState.OBJECT_WAITING_COMMA, None
                )
                return

            raise MalformedJSON(f"unexpected string in object state: {container.state}")

        if container.state == ParserState.ARRAY_WAITING_VALUE:
            container.container.append(value)
            self.stack[-1] = Container(
                container.container, ParserState.ARRAY_WAITING_COMMA, None
            )
        else:
            raise MalformedJSON(f"unexpected string in array state: {container.state}")

    def _commit_value(self, value: Any):
        if not self.stack:
            raise MalformedJSON("invalid json, any value cannot be a root element.")

        container = self.stack[-1]
        if isinstance(container.container, dict):
            if container.state == ParserState.OBJECT_WAITING_KEY:
                self.stack[-1] = Container(
                    container.container, ParserState.OBJECT_WAITING_COLON, value
                )
                return

            if container.state == ParserState.OBJECT_WAITING_VALUE:
                # if there are partial values, then simply overwrite
                container.container[container.last_key] = value
                container.last_value_partial = False

                self.stack[-1] = Container(
                    container.container, ParserState.OBJECT_WAITING_COMMA, None
                )
                return

            raise MalformedJSON(
                f"not expecting an object value, current state {container.state}"
            )

        if container.state != ParserState.ARRAY_WAITING_VALUE:
            raise MalformedJSON(
                f"not expecting an array value, current state {container.state}"
            )

        if container.last_value_partial and len(container.container) == 0:
            raise StreamJsonParser("we have partial values but no value in array")

        if container.last_value_partial:
            container.container[-1] = value
            container.last_value_partial = False
        else:
            container.container.append(value)

        self.stack[-1] = Container(
            container.container, ParserState.ARRAY_WAITING_COMMA, None
        )

    def _commit_partial_value(self, value: Any):
        if not self.stack:
            raise MalformedJSON("invalid json, any value cannot be a root element.")

        container = self.stack[-1]
        if isinstance(container.container, dict):
            if container.state == ParserState.OBJECT_WAITING_KEY:
                # we do nothing, we dont partially commit a key
                return

            if container.state == ParserState.OBJECT_WAITING_VALUE:
                if (
                    container.last_value_partial
                    and container.last_key in container.container
                ):
                    container.container[container.last_key] += value
                else:
                    container.container[container.last_key] = value

                container.last_value_partial = True
                return

            raise MalformedJSON(
                f"not expecting an object value, current state {container.state}"
            )

        if container.state != ParserState.ARRAY_WAITING_VALUE:
            raise MalformedJSON(
                f"not expecting an array value, current state {container.state}"
            )

        if container.last_value_partial and len(container.container) > 0:
            container.container[-1] += value
        else:
            container.container.append(value)

        container.last_value_partial = True

    def get(self) -> Any:
        """Retrieve the current parse result.

        Returns:
            Any: The parsed JSON structure. Could be:
                - Complete top-level structure if parsing is done
                - Partial structure if parsing is incomplete
                - None if no structure has been recognized yet
        """
        # If we have a finalized root and no stack, that’s a fully closed top-level object/array
        if self.root is not None and not self.stack:
            return self.root

        if not self.stack:
            # no partial structure
            return None

        # Rebuild partial structure from top-level of stack
        # In standard JSON, there's only one top-level container anyway => stack[0]
        top_container = self.stack[0]
        # But the container itself is partially or fully built. Because we hold references,
        # it includes nested partial structures as well. So returning top_container is enough.
        # The only difference: Some key might not be "committed" if we haven't seen a colon, etc.
        # We have *not* stored partial keys => so they're absent in the dict.
        # Partial string values are present in the dict or list.
        return top_container.container


###############################################################################
# Usage Example
###############################################################################

if __name__ == "__main__":
    parser = StreamJsonParser()
    parser.consume('{"foo": "bar')
    print(parser.get())  # => {"foo": "bar"} (partially complete string "bar")
    parser.consume('"}')
    print(parser.get())  # => {"foo": "bar"}
