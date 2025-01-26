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

    def test_initialization(self):
        """Test that parser initializes with empty stack and no current stream"""
        self.assertIsNone(self.parser.get())

    def test_empty_string(self):
        """Test consuming an empty string"""
        self.parser.consume("")
        self.assertIsNone(self.parser.get())

    def test_empty_object(self):
        """Test consuming an empty object"""
        self.parser.consume("{}")
        self.assertEqual(self.parser.get(), {})

    def test_invalid_root_value(self):
        """Test consuming and invalid JSON root value"""
        with self.assertRaises(StreamParserJSONDecodeError):
            self.parser.consume('""')

    def test_object_one_chunk(self):
        """Test consuming a simple JSON object"""
        self.parser.consume('{"key": "value"}')
        result = self.parser.get()
        self.assertEqual(result, {"key": "value"})

    def test_object_partial_key(self):
        """Test consuming JSON with incomplete key"""
        self.parser.consume('{"key')
        result = self.parser.get()
        self.assertEqual(result, {})

    def test_object_partial_key_extended(self):
        """Test consuming JSON with incomplete key"""
        self.parser.consume('{"key": "value"')
        self.parser.consume(',"new')
        result = self.parser.get()
        self.assertEqual(result, {"key": "value"})

    def test_object_value_type_known(self):
        """Test consuming JSON with not known value type"""
        self.parser.consume('{"key":')
        result = self.parser.get()
        self.assertEqual(result, {})

    def test_object_value_type_known_partial(self):
        """Test consuming JSON with incomplete value but known value type"""
        self.parser.consume('{"key": "')
        result = self.parser.get()
        self.assertEqual(result, {"key": ""})

    def test_object_value_type_known_partial_value(self):
        """Test consuming JSON with incomplete value but String value can be incomple"""
        self.parser.consume('{"key": "val')
        result = self.parser.get()
        self.assertEqual(result, {"key": "val"})

    def test_object_in_chunks(self):
        """Test consuming JSON in multiple parts"""
        self.parser.consume('{"key')
        self.parser.consume('": "val')
        self.parser.consume('ue"}')
        result = self.parser.get()
        self.assertEqual(result, {"key": "value"})

    def test_object_malformed(self):
        """Test consuming JSON in multiple parts"""
        self.parser.consume('{"key')
        with self.assertRaises(StreamParserJSONDecodeError):
            # string is missing a closing quote in the key
            self.parser.consume(': "val')

    def test_object_nested_object(self):
        """Test consuming nested JSON objects"""
        self.parser.consume('{"outer": {"inner": "value"}}')
        result = self.parser.get()
        self.assertEqual(result, {"outer": {"inner": "value"}})

    def test_object_nested_partial_key(self):
        """Test consuming nested JSON objects"""
        self.parser.consume('{"outer": {"inner')
        result = self.parser.get()
        self.assertEqual(result, {"outer": {}})

    def test_object_nested_partial_value(self):
        """Test consuming nested JSON objects"""
        self.parser.consume('{"outer": {"inner": "val')
        result = self.parser.get()
        self.assertEqual(result, {"outer": {"inner": "val"}})

    def test_object_whitespace_before_key(self):
        """Test object with various whitespace before key."""
        self.parser.consume('{\n\t  "key": "value"}')
        result = self.parser.get()
        self.assertEqual(result, {"key": "value"})

    def test_object_whitespace_after_key(self):
        """Test object with various whitespace after key."""
        self.parser.consume('{"key"\r\n\t : "value"}')
        result = self.parser.get()
        self.assertEqual(result, {"key": "value"})

    def test_object_whitespace_before_value(self):
        """Test object with various whitespace before value."""
        self.parser.consume('{"key":\n\r\t  "value"}')
        result = self.parser.get()
        self.assertEqual(result, {"key": "value"})

    def test_object_whitespace_after_value(self):
        """Test object with various whitespace after value."""
        self.parser.consume('{"key": "value"\n\t\r  }')
        result = self.parser.get()
        self.assertEqual(result, {"key": "value"})

    def test_object_whitespace_between_pairs(self):
        """Test object with various whitespace between key-value pairs."""
        self.parser.consume('{"key1": "value1"\n\t\r  ,\n\t  "key2": "value2"}')
        result = self.parser.get()
        self.assertEqual(result, {"key1": "value1", "key2": "value2"})

    def test_object_partial_whitespace(self):
        """Test partial object with whitespace in chunks."""
        self.parser.consume('{\n\t  "key1"')
        result = self.parser.get()
        self.assertEqual(result, {})

        self.parser.consume("\r\n\t  :  \n\t")
        result = self.parser.get()
        self.assertEqual(result, {})

        self.parser.consume('"value1"\n\r\t  }')
        result = self.parser.get()
        self.assertEqual(result, {"key1": "value1"})

    def test_object_empty_with_whitespace(self):
        """Test empty object with various whitespace."""
        self.parser.consume("{\n\t\r  }")
        result = self.parser.get()
        self.assertEqual(result, {})

    def test_object_nested_with_whitespace(self):
        """Test nested object with various whitespace."""
        self.parser.consume('{\n  "outer"\t: {\r\n\t  "inner": "value"\n\t  }\r\n}')
        result = self.parser.get()
        self.assertEqual(result, {"outer": {"inner": "value"}})

    def test_object_corner_case_unicode_escape(self):
        """Test object with Unicode escape sequences in key and value."""
        self.parser.consume('{"\\u006B\\u0065')  # "key": "val"
        self.parser.consume('\\u0079": "\\u0076')
        self.parser.consume('\\u0061\\u006C"}')
        result = self.parser.get()
        self.assertEqual(result, {"key": "val"})

    def test_object_corner_case_escaped_quotes(self):
        """Test object with escaped quotes in key and value."""
        self.parser.consume('{"key\\"name": "value\\"text"}')
        result = self.parser.get()
        self.assertEqual(result, {'key"name': 'value"text'})

    def test_object_corner_case_escaped_special(self):
        """Test object with escaped special characters."""
        self.parser.consume('{"key\\n\\t": "value\\r\\n"}')
        result = self.parser.get()
        self.assertEqual(result, {"key\n\t": "value\r\n"})

    def test_object_corner_case_max_nesting(self):
        """Test object with deep nesting."""
        deep_json = (
            "{"
            + "".join([f'"k{i}": {{' for i in range(20)])
            + '"value": "deep"'
            + "}" * 20
        )
        self.parser.consume(deep_json)
        result = self.parser.get()
        # Verify the deepest value
        current = result
        for i in range(20):
            self.assertIn(f"k{i}", current)
            current = current[f"k{i}"]
        self.assertEqual(current["value"], "deep")

    def test_object_corner_case_long_key_value(self):
        """Test object with very long key and value."""
        long_str = "x" * 1000
        self.parser.consume(f'{{"{long_str}": "{long_str}"}}')
        result = self.parser.get()
        self.assertEqual(result, {long_str: long_str})

    def test_object_corner_case_empty_key_value(self):
        """Test object with empty key and value."""
        self.parser.consume('{"": ""}')
        result = self.parser.get()
        self.assertEqual(result, {"": ""})

    def test_empty_array(self):
        """Test parsing an empty array."""
        self.parser.consume("[]")
        result = self.parser.get()
        self.assertEqual(result, [])

    def test_array_with_single_value(self):
        """Test parsing an array with a single string value."""
        self.parser.consume('["test"]')
        result = self.parser.get()
        self.assertEqual(result, ["test"])

    def test_array_with_multiple_values(self):
        """Test parsing an array with multiple string values."""
        self.parser.consume('["test1", "test2", "test3"]')
        result = self.parser.get()
        self.assertEqual(result, ["test1", "test2", "test3"])

    def test_array_with_partial_input(self):
        """Test parsing an array with partial input in multiple chunks."""
        self.parser.consume('["test1"')
        result = self.parser.get()
        self.assertEqual(result, ["test1"])

        self.parser.consume(', "test2"')
        result = self.parser.get()
        self.assertEqual(result, ["test1", "test2"])

        self.parser.consume("]")
        result = self.parser.get()
        self.assertEqual(result, ["test1", "test2"])

    def test_nested_array_in_object(self):
        """Test parsing an object containing an array."""
        self.parser.consume('{"values": ["test1", "test2"]}')
        result = self.parser.get()
        self.assertEqual(result, {"values": ["test1", "test2"]})

    def test_array_in_object_partial(self):
        """Test parsing an object with array using partial input."""
        self.parser.consume('{"values": [')
        result = self.parser.get()
        self.assertEqual(result, {"values": []})

        self.parser.consume('"test1", ')
        result = self.parser.get()
        self.assertEqual(result, {"values": ["test1"]})

        self.parser.consume('"test2"]}')
        result = self.parser.get()
        self.assertEqual(result, {"values": ["test1", "test2"]})

    def test_object_number_integer(self):
        """Test object with integer values."""
        self.parser.consume('{"key": 123}')
        result = self.parser.get()
        self.assertEqual(result, {"key": 123})

    def test_object_number_negative(self):
        """Test object with negative numbers."""
        self.parser.consume('{"key": -456}')
        result = self.parser.get()
        self.assertEqual(result, {"key": -456})

    def test_object_number_float(self):
        """Test object with floating point numbers."""
        self.parser.consume('{"key": 123.456}')
        result = self.parser.get()
        self.assertEqual(result, {"key": 123.456})

    def test_object_number_negative_float(self):
        """Test object with negative floating point numbers."""
        self.parser.consume('{"key": -123.456}')
        result = self.parser.get()
        self.assertEqual(result, {"key": -123.456})

    def test_object_number_scientific(self):
        """Test object with scientific notation numbers."""
        test_cases = [
            ('{"key": 1.23e4}', {"key": 1.23e4}),
            ('{"key": 1.23E4}', {"key": 1.23e4}),
            ('{"key": -1.23e-4}', {"key": -1.23e-4}),
            ('{"key": 1.23e+4}', {"key": 1.23e4}),
        ]
        for json_input, expected in test_cases:
            self.parser = StreamJsonParser()  # Reset parser for each case
            self.parser.consume(json_input)
            result = self.parser.get()
            self.assertEqual(result, expected)

    def test_object_number_corner_cases(self):
        """Test object with number corner cases."""
        test_cases = [
            ('{"key": 0}', {"key": 0}),
            ('{"key": -0}', {"key": -0}),
            ('{"key": 0.0}', {"key": 0.0}),
            ('{"key": 1e0}', {"key": 1e0}),
            ('{"key": 1E-0}', {"key": 1e-0}),
        ]
        for json_input, expected in test_cases:
            self.parser = StreamJsonParser()  # Reset parser for each case
            self.parser.consume(json_input)
            result = self.parser.get()
            self.assertEqual(result, expected)

    def test_object_number_partial(self):
        """Test object with partial number input."""
        # Test partial integer
        self.parser.consume('{"key": 12')
        result = self.parser.get()
        self.assertEqual(result, {"key": 12})

        # Test partial float
        self.parser = StreamJsonParser()
        self.parser.consume('{"key": 12.')
        result = self.parser.get()
        self.assertEqual(result, {"key": 12})

        # Test partial scientific notation
        self.parser = StreamJsonParser()
        self.parser.consume('{"key": 1.2e')
        result = self.parser.get()
        self.assertEqual(result, {"key": 1.2})

    def test_object_number_malformed(self):
        """Test object with malformed numbers."""
        invalid_cases = [
            '{"key": 12..34}',  # Double decimal
            '{"key": 12.34.56}',  # Multiple decimals
            '{"key": 12ee4}',  # Double exponent
            '{"key": --123}',  # Double negative
            '{"key": 12e4.5}',  # Decimal in exponent
        ]
        for json_input in invalid_cases:
            self.parser = StreamJsonParser()
            with self.assertRaises(StreamParserJSONDecodeError):
                self.parser.consume(json_input)
                self.parser.get()

    def test_array_mixed_types(self):
        """Test array with different types of values."""
        self.parser.consume('[1, "string", true, null, 3.14, -42]')
        result = self.parser.get()
        self.assertEqual(result, [1, "string", True, None, 3.14, -42])

    def test_array_nested_arrays(self):
        """Test array containing other arrays."""
        self.parser.consume("[[1, 2], [3, 4], []]")
        result = self.parser.get()
        self.assertEqual(result, [[1, 2], [3, 4], []])

    def test_array_nested_objects(self):
        """Test array containing objects."""
        self.parser.consume('[{"a": 1}, {"b": 2}, {}]')
        result = self.parser.get()
        self.assertEqual(result, [{"a": 1}, {"b": 2}, {}])

    def test_array_complex_nesting(self):
        """Test array with complex nesting of arrays and objects."""
        self.parser.consume('[{"arr": [1, 2, {"x": [3, 4]}]}, [5, {"y": 6}]]')
        result = self.parser.get()
        self.assertEqual(result, [{"arr": [1, 2, {"x": [3, 4]}]}, [5, {"y": 6}]])

    def test_array_whitespace(self):
        """Test array with various whitespace patterns."""
        test_cases = [
            ("[  1  ,  2  ]", [1, 2]),
            ("[\n1,\n2\n]", [1, 2]),
            ("[\r1,\t2\r\n]", [1, 2]),
            ("[ ]", []),
        ]
        for json_input, expected in test_cases:
            self.parser = StreamJsonParser()
            self.parser.consume(json_input)
            result = self.parser.get()
            self.assertEqual(result, expected)

    def test_array_partial_complex(self):
        """Test partial parsing of complex array structures."""
        # Start with empty array in object
        self.parser.consume('{"data": [')
        result = self.parser.get()
        self.assertEqual(result, {"data": []})

        # Add nested object
        self.parser.consume('{"nested": [1, 2]}')
        result = self.parser.get()
        self.assertEqual(result, {"data": [{"nested": [1, 2]}]})

        # Add comma and start new item
        self.parser.consume(', {"more": {')
        result = self.parser.get()
        self.assertEqual(result, {"data": [{"nested": [1, 2]}, {"more": {}}]})

        # Complete the structure
        self.parser.consume('"x": 3}}]}')
        result = self.parser.get()
        self.assertEqual(result, {"data": [{"nested": [1, 2]}, {"more": {"x": 3}}]})

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

    def test_array_streaming_edge_cases(self):
        """Test edge cases in streaming array parsing."""
        # Test extremely small chunks
        self.parser.consume("[")
        result = self.parser.get()
        self.assertEqual(result, [])

        self.parser.consume('"')
        self.parser.consume("t")
        self.parser.consume("e")
        self.parser.consume("s")
        self.parser.consume("t")
        self.parser.consume('"')
        result = self.parser.get()
        self.assertEqual(result, ["test"])

        # Test multiple commas in chunks
        self.parser.consume(", ")
        self.parser.consume("1, ")
        self.parser.consume("true, ")
        self.parser.consume("null]")
        result = self.parser.get()
        self.assertEqual(result, ["test", 1, True, None])


if __name__ == "__main__":
    unittest.main()
