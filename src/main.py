import json
from typing import Any, Literal, Optional, Union

from config import logger

# possible parse return values are
# - tuple with index and (parsed value or True).
# - tuple with index and True
# - False if no further parsing is possible
# - True means, is a valid json therefore close it.
ParseResult = Union[tuple[int, Optional[str], Literal[True]], Literal[False]]


class JSONDecodeError(ValueError):
    pass


class PartialJSON(JSONDecodeError):
    pass


class MalformedJSON(JSONDecodeError):
    pass


def _find_non_whitespace_index(json_str: str, from_index: int = 0) -> int:
    while from_index < len(json_str):
        char = json_str[from_index]
        # From JSON sepcs,whitespace is space, horizontal tab, line feed, or carriage return
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
    def __init__(self):
        self.chunks: list[str] = []
        self.current_valid_json: str = ""

    def consume(self, json_str: str) -> None:
        """
        Requirements:
            - handle objects and strings
            - handle partial data
            - handle nested objects
            - An object is form once the key value is partial
        Tests:
            - { | {}-> {} - Done
            - {"key": "value"} -> {"key": "value"}
            - {"key": "value", "new": "va"} -> {"key": "value"}
            - {"key": "value", "new": "value"} -> {"key": "value"}
            - {"key": "value", "new"} -> {"key": "value"}
            - {"key": "value", {} -> {"key": "value", {}}
        """
        try:
            logger.debug({"input": json_str})
            # add to chunks
            self.chunks.append(json_str)
            self._parse("".join(self.chunks))
        except JSONDecodeError as e:
            logger.error(e)
            raise JSONDecodeError(e)

    def _parse(self, json_str: str) -> None:
        """Parse the json string"""
        if not json_str:
            return

        if json_str[0] != "{" and json_str[0] != "[":
            self.chunks = []
            raise MalformedJSON("json must start with { or [")

        i, last_char, close = self._parse_value(json_str)
        if close:
            self.current_valid_json = f"{json_str[:i]}{last_char}"
            return

        if not close and last_char:
            self.current_valid_json = f"{json_str[:i]}{last_char}"

    def _parse_value(self, json_str: str) -> ParseResult:
        """Is the object json flow
        JSON has two root level starts: object, array
        """
        # JSON VALUE, whitespace
        i = _find_non_whitespace_index(json_str, from_index=0)
        current_char = json_str[i]

        # JSON value, object
        if current_char == "{":
            return self._parse_object(json_str)

        # JSON value, array
        if current_char == "[":
            # @todo implement for array
            pass

        if current_char == '"':
            # JSON flow, string
            return self._parse_string(json_str)

        raise MalformedJSON(f"string {json_str} does not follow json spec")

    def _parse_object(self, json_str: str) -> ParseResult:
        """to check
        - is it closed?
        - if it closed return
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
                    return j, None, True

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
                sj, last_char, is_closed = self._parse_value(json_str[j:])
                if not is_closed:
                    # we can have impartial values
                    return j + sj, "{}{}".format(last_char, "}"), False

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
                    return i, "}", True

                # keep moving, another round of object flow
                j += 1

        except IndexError:
            # When the value type of the key is not known, then we close the current object
            return i, "}", True

        return i, None, False

    def _parse_string(self, json_str: str) -> ParseResult:
        """@TODO
        - Add check, we have not check for escaped string values to be valid! (\\uXXXX)
        """
        i = 1
        while i < len(json_str):
            if json_str[i] == '"':
                return i, None, True

            i += 1
        return i, '"', False

    def get(self) -> Optional[dict[str, Any]]:
        """Returns the current valid JSON string"""
        if not self.current_valid_json:
            return None
        return json.loads(self.current_valid_json)


if __name__ == "__main__":
    logger.info("starting JsonFlow ...")
    parser = StreamJsonParser()
    try:
        parser.consume('""')
        logger.debug(parser.get())
    except JSONDecodeError:
        pass
    parser = StreamJsonParser()
    parser.consume('{"key":')
    logger.debug(parser.get())

    parser = StreamJsonParser()
    parser.consume('{"key": "')
    logger.debug(parser.get())

    parser = StreamJsonParser()
    parser.consume('{"')
    logger.debug(parser.get())
    parser.consume('key')
    logger.debug(parser.get())
    parser.consume('": ')
    parser.consume('"val')
    parser.consume('ue"}')
    logger.debug(parser.get())

    parser = StreamJsonParser()
    parser.consume('{"key": "val')
    logger.debug(parser.get())

    parser = StreamJsonParser()
    parser.consume('{"outer": {"inner')
    logger.debug(parser.get())
    logger.info("done ...")
