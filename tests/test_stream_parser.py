import json
import unittest

import pytest

from config import logger
from stream_parser import StreamJsonParser, StreamParserJSONDecodeError


@pytest.fixture(autouse=True)
def disable_logging():
    logger.disabled = True
    yield
    logger.disabled = False


class TestStreamJsonParser(unittest.TestCase):
    def setUp(self):
        self.parser = StreamJsonParser()

    @pytest.fixture
    def validate_json(self):
        yield
        try:
            json.loads(self.actual)
        except json.decoder.JSONDecodeError as e:
            pytest.fail(f"Invalid JSON: {self.actual}\nError: {e}")

    def test_initialization(self):
        """Test that parser initializes with empty stack and no current stream"""
        self.assertIsNone(self.parser.get())

    def test_empty_string(self):
        """Test consuming an empty string"""
        self.parser.consume("")
        self.assertIsNone(self.parser.get())

    @pytest.mark.usefixtures("validate_json")
    def test_empty_object(self):
        """Test consuming an empty object"""
        self.parser.consume("{}")
        self.actual = self.parser.get()
        self.assertEqual(self.actual, "{}")

    def test_invalid_multiple_roots(self):
        """Test consuming JSON with multiple roots"""
        invalid_cases = [
            "{}{}",
            "{}[]",
            "[][]",
            "[]{}",
        ]
        for json_input in invalid_cases:
            self.parser = StreamJsonParser()
            with self.assertRaises(StreamParserJSONDecodeError):
                self.parser.consume(json_input)

    def test_invalid_root_value(self):
        """Test consuming and invalid JSON root value"""
        with self.assertRaises(StreamParserJSONDecodeError):
            self.parser.consume('""')

    @pytest.mark.usefixtures("validate_json")
    def test_object_one_chunk(self):
        """Test consuming a simple JSON object"""
        self.parser.consume('{"key": "value"}')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '{"key": "value"}')

    @pytest.mark.usefixtures("validate_json")
    def test_object_partial_key(self):
        """Test consuming JSON with incomplete key"""
        self.parser.consume('{"key')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, "{}")

    @pytest.mark.usefixtures("validate_json")
    def test_object_partial_key_extended(self):
        """Test consuming JSON with incomplete key"""
        self.parser.consume('{"key": "value"')
        self.parser.consume(',"new')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '{"key": "value"}')

    @pytest.mark.usefixtures("validate_json")
    def test_object_value_type_known(self):
        """Test consuming JSON with not known value type"""
        self.parser.consume('{"key":')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, "{}")

    @pytest.mark.usefixtures("validate_json")
    def test_object_value_type_known_partial(self):
        """Test consuming JSON with incomplete value but known value type"""
        self.parser.consume('{"key": "')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '{"key": ""}')

    @pytest.mark.usefixtures("validate_json")
    def test_object_value_type_known_partial_value(self):
        """Test consuming JSON with incomplete value but String value can be incomple"""
        self.parser.consume('{"key": "val')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '{"key": "val"}')

    @pytest.mark.usefixtures("validate_json")
    def test_object_in_chunks(self):
        """Test consuming JSON in multiple parts"""
        self.parser.consume('{"key')
        self.parser.consume('": "val')
        self.parser.consume('ue"}')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '{"key": "value"}')

    def test_object_malformed(self):
        """Test consuming JSON in multiple parts"""
        self.parser.consume('{"key')
        with self.assertRaises(StreamParserJSONDecodeError):
            # string is missing a closing quote in the key
            self.parser.consume(': "val')

    @pytest.mark.usefixtures("validate_json")
    def test_object_nested_object(self):
        """Test consuming nested JSON objects"""
        self.parser.consume('{"outer": {"inner": "value"}}')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '{"outer": {"inner": "value"}}')

    @pytest.mark.usefixtures("validate_json")
    def test_object_nested_partial_key(self):
        """Test consuming nested JSON objects"""
        self.parser.consume('{"outer": {"inner')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '{"outer": {}}')

    @pytest.mark.usefixtures("validate_json")
    def test_object_nested_partial_value(self):
        """Test consuming nested JSON objects"""
        self.parser.consume('{"outer": {"inner": "val')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '{"outer": {"inner": "val"}}')

    @pytest.mark.usefixtures("validate_json")
    def test_object_whitespace_before_key(self):
        """Test object with various whitespace before key."""
        self.parser.consume('{\n\t  "key": "value"}')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '{\n\t  "key": "value"}')

    @pytest.mark.usefixtures("validate_json")
    def test_object_whitespace_after_key(self):
        """Test object with various whitespace after key."""
        self.parser.consume('{"key"\r\n\t : "value"}')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '{"key"\r\n\t : "value"}')

    @pytest.mark.usefixtures("validate_json")
    def test_object_whitespace_before_value(self):
        """Test object with various whitespace before value."""
        self.parser.consume('{"key":\n\r\t  "value"}')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '{"key":\n\r\t  "value"}')

    @pytest.mark.usefixtures("validate_json")
    def test_object_whitespace_after_value(self):
        """Test object with various whitespace after value."""
        self.parser.consume('{"key": "value"\n\t\r  }')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '{"key": "value"\n\t\r  }')

    @pytest.mark.usefixtures("validate_json")
    def test_object_whitespace_between_pairs(self):
        """Test object with various whitespace between key-value pairs."""
        self.parser.consume('{"key1": "value1"\n\t\r  ,\n\t  "key2": "value2"}')
        self.actual = self.parser.get()
        self.assertEqual(
            self.actual, '{"key1": "value1"\n\t\r  ,\n\t  "key2": "value2"}'
        )

    @pytest.mark.usefixtures("validate_json")
    def test_object_partial_whitespace(self):
        """Test partial object with whitespace in chunks."""
        self.parser.consume('{\n\t  "key1"')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, "{}")

        self.parser.consume("\r\n\t  :  \n\t")
        self.actual = self.parser.get()
        self.assertEqual(self.actual, "{}")

        self.parser.consume('"value1"\n\r\t  }')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '{\n\t  "key1"\r\n\t  :  \n\t"value1"\n\r\t  }')

    @pytest.mark.usefixtures("validate_json")
    def test_object_empty_with_whitespace(self):
        """Test empty object with various whitespace."""
        self.parser.consume("{\n\t\r  }")
        self.actual = self.parser.get()
        self.assertEqual(self.actual, "{\n\t\r  }")

    @pytest.mark.usefixtures("validate_json")
    def test_object_nested_with_whitespace(self):
        """Test nested object with various whitespace."""
        self.parser.consume('{\n  "outer"\t: {\r\n\t  "inner": "value"\n\t  }\r\n}')
        self.actual = self.parser.get()
        self.assertEqual(
            self.actual, '{\n  "outer"\t: {\r\n\t  "inner": "value"\n\t  }\r\n}'
        )

    @pytest.mark.usefixtures("validate_json")
    def test_object_corner_case_unicode_escape(self):
        """Test object with Unicode escape sequences in key and value."""
        self.parser.consume('{"\\u006B\\u0065')  # "key": "val"
        self.parser.consume('\\u0079": "\\u0076')
        self.parser.consume('\\u0061\\u006C"}')
        self.actual = self.parser.get()
        self.assertEqual(
            self.actual, '{"\\u006B\\u0065\\u0079": "\\u0076\\u0061\\u006C"}'
        )

    @pytest.mark.usefixtures("validate_json")
    def test_object_corner_case_escaped_quotes(self):
        """Test object with escaped quotes in key and value."""
        self.parser.consume('{"key\\"name": "value\\"text"}')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '{"key\\"name": "value\\"text"}')

    @pytest.mark.usefixtures("validate_json")
    def test_object_corner_case_escaped_special(self):
        """Test object with escaped special characters."""
        self.parser.consume('{"key\\n\\t": "value\\r\\n"}')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '{"key\\n\\t": "value\\r\\n"}')

    @pytest.mark.usefixtures("validate_json")
    def test_object_corner_case_max_nesting(self):
        """Test object with deep nesting."""
        deep_json = (
            "{"
            + "".join([f'"k{i}": {{' for i in range(20)])
            + '"value": "deep"'
            + "}" * 21
        )
        self.parser.consume(deep_json)
        self.actual = self.parser.get()
        self.assertEqual(self.actual, deep_json)

    @pytest.mark.usefixtures("validate_json")
    def test_object_corner_case_long_key_value(self):
        """Test object with very long key and value."""
        long_str = "x" * 1000
        self.parser.consume(f'{{"{long_str}": "{long_str}"}}')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, f'{{"{long_str}": "{long_str}"}}')

    @pytest.mark.usefixtures("validate_json")
    def test_object_corner_case_empty_key_value(self):
        """Test object with empty key and value."""
        self.parser.consume('{"": ""}')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '{"": ""}')

    @pytest.mark.usefixtures("validate_json")
    def test_empty_array(self):
        """Test parsing an empty array."""
        self.parser.consume("[]")
        self.actual = self.parser.get()
        self.assertEqual(self.actual, "[]")

    @pytest.mark.usefixtures("validate_json")
    def test_array_with_single_value(self):
        """Test parsing an array with a single string value."""
        self.parser.consume('["test"]')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '["test"]')

    @pytest.mark.usefixtures("validate_json")
    def test_array_with_multiple_values(self):
        """Test parsing an array with multiple string values."""
        self.parser.consume('["test1", "test2", "test3"]')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '["test1", "test2", "test3"]')

    @pytest.mark.usefixtures("validate_json")
    def test_array_with_partial_input(self):
        """Test parsing an array with partial input in multiple chunks."""
        self.parser.consume('["test1"')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '["test1"]')

        self.parser.consume(', "test2"')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '["test1", "test2"]')

        self.parser.consume("]")
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '["test1", "test2"]')

    @pytest.mark.usefixtures("validate_json")
    def test_nested_array_in_object(self):
        """Test parsing an object containing an array."""
        self.parser.consume('{"values": ["test1", "test2"]}')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '{"values": ["test1", "test2"]}')

    @pytest.mark.usefixtures("validate_json")
    def test_array_in_object_partial(self):
        """Test parsing an object with array using partial input."""
        self.parser.consume('{"values": [')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '{"values": []}')

        self.parser.consume('"test1", ')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '{"values": ["test1"]}')

        self.parser.consume('"test2"]}')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '{"values": ["test1", "test2"]}')

    @pytest.mark.usefixtures("validate_json")
    def test_object_number_integer(self):
        """Test object with integer values."""
        self.parser.consume('{"key": 123}')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '{"key": 123}')

    @pytest.mark.usefixtures("validate_json")
    def test_object_number_negative(self):
        """Test object with negative numbers."""
        self.parser.consume('{"key": -456}')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '{"key": -456}')

    @pytest.mark.usefixtures("validate_json")
    def test_object_number_float(self):
        """Test object with floating point numbers."""
        self.parser.consume('{"key": 123.456}')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '{"key": 123.456}')

    @pytest.mark.usefixtures("validate_json")
    def test_object_number_negative_float(self):
        """Test object with negative floating point numbers."""
        self.parser.consume('{"key": -123.456}')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '{"key": -123.456}')

    @pytest.mark.usefixtures("validate_json")
    def test_object_number_scientific(self):
        """Test object with scientific notation numbers."""
        test_cases = [
            '{"key": 1.23e4}',
            '{"key": -1.23e-4}',
            '{"key": 1.23e+4}',
        ]
        for json_input in test_cases:
            self.parser = StreamJsonParser()  # Reset parser for each case
            self.parser.consume(json_input)
            self.actual = self.parser.get()
            self.assertEqual(self.actual, json_input)

    @pytest.mark.usefixtures("validate_json")
    def test_object_number_corner_cases(self):
        """Test object with number corner cases."""
        test_cases = [
            '{"key": 0}',
            '{"key": -0}',
            '{"key": 0.0}',
            '{"key": 1e0}',
            '{"key": 1E-0}',
        ]
        for json_input in test_cases:
            self.parser = StreamJsonParser()  # Reset parser for each case
            self.parser.consume(json_input)
            self.actual = self.parser.get()
            self.assertEqual(self.actual, json_input)

    @pytest.mark.usefixtures("validate_json")
    def test_object_number_partial(self):
        """Test object with partial number input."""
        # Test partial integer
        self.parser.consume('{"key": 12')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '{"key": 12}')

        # Test partial float
        self.parser = StreamJsonParser()
        self.parser.consume('{"key": 12.')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '{"key": 12}')

        # Test partial scientific notation
        self.parser = StreamJsonParser()
        self.parser.consume('{"key": 1.2e')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '{"key": 1.2}')

    def test_object_number_malformed(self):
        """Test object with malformed numbers."""
        invalid_cases = [
            '{"key": 12..34}',  # Double decimal
            '{"key": 12.34.56}',  # Multiple decimals
            '{"key": 12ee4}',  # Double exponent
            '{"key": --123}',  # Double negative
            '{"key": 12e4.5}',  # Decimal in exponent
        ]
        # Verify no exception is raised
        # we are not validating the validity of the LLM outputs
        for json_input in invalid_cases:
            self.parser = StreamJsonParser()
            try:
                self.parser.consume(json_input)
                self.parser.get()
            except Exception as e:
                self.fail(f"consume() raised {type(e).__name__} unexpectedly!")

    @pytest.mark.usefixtures("validate_json")
    def test_array_mixed_types(self):
        """Test array with different types of values."""
        self.parser.consume('[1, "string", true, null, 3.14, -42]')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '[1, "string", true, null, 3.14, -42]')

    @pytest.mark.usefixtures("validate_json")
    def test_array_nested_arrays(self):
        """Test array containing other arrays."""
        self.parser.consume("[[1, 2], [3, 4], []]")
        self.actual = self.parser.get()
        self.assertEqual(self.actual, "[[1, 2], [3, 4], []]")

    @pytest.mark.usefixtures("validate_json")
    def test_array_nested_objects(self):
        """Test array containing objects."""
        self.parser.consume('[{"a": 1}, {"b": 2}, {}]')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '[{"a": 1}, {"b": 2}, {}]')

    @pytest.mark.usefixtures("validate_json")
    def test_array_complex_nesting(self):
        """Test array with complex nesting of arrays and objects."""
        self.parser.consume('[{"arr": [1, 2, {"x": [3, 4]}]}, [5, {"y": 6}]]')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '[{"arr": [1, 2, {"x": [3, 4]}]}, [5, {"y": 6}]]')

    @pytest.mark.usefixtures("validate_json")
    def test_array_partial_complex(self):
        """Test partial parsing of complex array structures."""
        # Start with empty array in object
        self.parser.consume('{"data": [')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '{"data": []}')

        # Add nested object
        self.parser.consume('{"nested": [1, 2]}')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '{"data": [{"nested": [1, 2]}]}')

        # Add comma and start new item
        self.parser.consume(', {"more": {')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '{"data": [{"nested": [1, 2]}, {"more": {}}]}')

        # Complete the structure
        self.parser.consume('"x": 3}}]}')
        self.actual = self.parser.get()
        self.assertEqual(
            self.actual, '{"data": [{"nested": [1, 2]}, {"more": {"x": 3}}]}'
        )

    def test_array_malformed(self):
        """Test malformed array inputs."""
        invalid_cases = [
            "[,]",  # Empty element
            "[1, , 2]",  # Missing element
            "[1, 2,]",  # Trailing comma
            "[1, 2]]",  # Extra closing bracket
        ]
        for json_input in invalid_cases:
            self.parser = StreamJsonParser()
            with self.assertRaises(StreamParserJSONDecodeError):
                self.parser.consume(json_input)
                self.parser.get()

    @pytest.mark.usefixtures("validate_json")
    def test_array_streaming_edge_cases(self):
        """Test edge cases in streaming array parsing."""
        # Test extremely small chunks
        self.parser.consume("[")
        self.actual = self.parser.get()
        self.assertEqual(self.actual, "[]")

        self.parser.consume('"')
        self.parser.consume("t")
        self.parser.consume("e")
        self.parser.consume("s")
        self.parser.consume("t")
        self.parser.consume('"')
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '["test"]')

        # Test multiple commas in chunks
        self.parser.consume(", ")
        self.parser.consume("1, ")
        self.parser.consume("true, ")
        self.parser.consume("null]")
        self.actual = self.parser.get()
        self.assertEqual(self.actual, '["test", 1, true, null]')


if __name__ == "__main__":
    unittest.main()
