import pytest

from config import logger
from stream_parser import StreamJsonParser, StreamParserJSONDecodeError


@pytest.fixture(autouse=True)
def disable_logging():
    logger.disabled = True
    yield
    logger.disabled = False


@pytest.fixture
def numbers():
    return [
        "1",
        "-1",
        "0.0",
        "3.14",
        "-2.5",
        "1e5",
        "-1e-5",
        "1.23e+4",
        "-4.56e-2",
    ]


@pytest.fixture
def partial_numbers():
    return [
        ("12e", 2),
        ("-12e", 3),
        ("12e-", 2),
        ("-12e-", 3),
        ("12.", 2),
        ("-12.", 3),
    ]


@pytest.fixture
def parser():
    """Fixture that provides a StreamJsonParser instance."""
    return StreamJsonParser()


class TestStreamJsonParser:
    """Test class for StreamJsonParser."""

    def test_initialization(self, parser):
        """Test that parser initializes with empty stack and no current stream"""
        assert parser.get() is None

    def test_empty_string(self, parser):
        """Test consuming an empty string"""
        parser.consume("")
        assert parser.get() is None

    def test_empty_object(self, parser):
        """Test consuming an empty object"""
        parser.consume("{}")
        assert parser.get() == {}

    def test_invalid_root_value(self, parser):
        """Test consuming and invalid JSON root value"""
        parser.consume('""')
        assert parser.get() is None

    def test_object_one_chunk(self, parser):
        """Test consuming a simple JSON object"""
        parser.consume('{"key": "value"}')
        actual = parser.get()
        assert actual == {"key": "value"}

    def test_object_partial_key(self, parser):
        """Test consuming JSON with incomplete key"""
        parser.consume('{"key')
        actual = parser.get()
        assert actual == {}

    def test_object_partial_key_extended(self, parser):
        """Test consuming JSON with incomplete key"""
        parser.consume('{"key": "value"')
        parser.consume(',"new')
        actual = parser.get()
        assert actual == {"key": "value"}

    def test_object_value_type_known(self, parser):
        """Test consuming JSON with not known value type"""
        parser.consume('{"key":')
        actual = parser.get()
        assert actual == {}

    def test_object_value_type_known_partial(self, parser):
        """Test consuming JSON with incomplete value but known value type"""
        parser.consume('{"key": "')
        actual = parser.get()
        assert actual == {"key": ""}

    def test_object_value_type_known_partial_value(self, parser):
        """Test consuming JSON with incomplete value but String value can be incomple"""
        parser.consume('{"key": "val')
        actual = parser.get()
        assert actual == {"key": "val"}

    def test_object_in_chunks(self, parser):
        """Test consuming JSON in multiple parts"""
        parser.consume('{"key')
        parser.consume('u": "val')
        parser.consume('ue"}')
        actual = parser.get()
        assert actual == {"keyu": "value"}

    def test_object_in_chunks_with_single_tokens(self, parser):
        """Test consuming JSON in multiple parts"""
        parser.consume('{"key"')
        parser.consume(":")
        parser.consume('"')
        parser.consume("value")
        parser.consume('"')
        actual = parser.get()
        assert actual == {"key": "value"}

    def test_object_malformed(self, parser):
        """Test consuming JSON in multiple parts"""
        parser.consume('{"key')
        with pytest.raises(StreamParserJSONDecodeError):
            # string is missing a closing quote in the key
            parser.consume(': "val')

    def test_object_nested_object(self, parser):
        """Test consuming nested JSON objects"""
        parser.consume('{"outer": {"inner": "value"}}')
        actual = parser.get()
        assert actual == {"outer": {"inner": "value"}}

    def test_object_nested_partial_key(self, parser):
        """Test consuming nested JSON objects"""
        parser.consume('{"outer": {"inner')
        actual = parser.get()
        assert actual == {"outer": {}}

    def test_object_nested_partial_value(self, parser):
        """Test consuming nested JSON objects"""
        parser.consume('{"outer": {"inner": "val')
        actual = parser.get()
        assert actual == {"outer": {"inner": "val"}}

    def test_object_whitespace_before_key(self, parser):
        """Test object with various whitespace before key."""
        parser.consume('{\n\t  "key": "value"}')
        actual = parser.get()
        assert actual == {"key": "value"}

    def test_object_whitespace_after_key(self, parser):
        """Test object with various whitespace after key."""
        parser.consume('{"key"\r\n\t : "value"}')
        actual = parser.get()
        assert actual == {"key": "value"}

    def test_object_whitespace_before_value(self, parser):
        """Test object with various whitespace before value."""
        parser.consume('{"key":\n\r\t  "value"}')
        actual = parser.get()
        assert actual == {"key": "value"}

    def test_object_whitespace_after_value(self, parser):
        """Test object with various whitespace after value."""
        parser.consume('{"key": "value"\n\t\r  }')
        actual = parser.get()
        assert actual == {"key": "value"}

    def test_object_whitespace_between_pairs(self, parser):
        """Test object with various whitespace between key-value pairs."""
        parser.consume('{"key1": "value1"\n\t\r  ,\n\t  "key2": "value2"}')
        actual = parser.get()
        assert actual == {"key1": "value1", "key2": "value2"}

    def test_object_partial_whitespace(self, parser):
        """Test partial object with whitespace in chunks."""
        parser.consume('{\n\t  "key1"')
        actual = parser.get()
        assert actual == {}

        parser.consume("\r\n\t  :  \n\t")
        actual = parser.get()
        assert actual == {}

        parser.consume('"value1"\n\r\t  }')
        actual = parser.get()
        assert actual == {"key1": "value1"}

    def test_object_empty_with_whitespace(self, parser):
        """Test empty object with various whitespace."""
        parser.consume("{\n\t\r  }")
        actual = parser.get()
        assert actual == {}

    def test_object_nested_with_whitespace(self, parser):
        """Test nested object with various whitespace."""
        parser.consume('{\n  "outer"\t: {\r\n\t  "inner": "value"\n\t  }\r\n}')
        actual = parser.get()
        assert actual == {"outer": {"inner": "value"}}

    def test_object_corner_case_unicode_escape(self, parser):
        """Test object with Unicode escape sequences in key and value."""
        parser.consume('{"\\u006B\\u0065')  # "key": "val"
        parser.consume('\\u0079": "\\u0076')
        parser.consume('\\u0061\\u006C"}')
        actual = parser.get()
        assert actual == {"\\u006B\\u0065\\u0079": "\\u0076\\u0061\\u006C"}

    def test_object_corner_case_escaped_quotes(self, parser):
        """Test object with escaped quotes in key and value."""
        parser.consume('{"key\\"name": "value\\"text"}')
        actual = parser.get()
        assert actual == {'key\\"name': 'value\\"text'}

    def test_object_corner_case_escaped_special(self, parser):
        """Test object with escaped special characters."""
        parser.consume('{"key\\n\\t": "value\\r\\n"}')
        actual = parser.get()
        assert actual == {"key\\n\\t": "value\\r\\n"}

    def test_object_corner_case_max_nesting(self, parser):
        """Test object with deep nesting."""
        deep_json = (
            "{"
            + "".join([f'"k{i}": {{' for i in range(20)])
            + '"value": "deep"'
            + "}" * 20
        )
        parser.consume(deep_json)
        actual = parser.get()
        # Verify the deepest value
        current = actual
        for i in range(20):
            assert f"k{i}" in current
            current = current[f"k{i}"]
        assert current["value"] == "deep"

    def test_object_corner_case_long_key_value(self, parser):
        """Test object with very long key and value."""
        long_str = "x" * 1000
        parser.consume(f'{{"{long_str}": "{long_str}"}}')
        actual = parser.get()
        assert actual == {long_str: long_str}

    def test_object_corner_case_empty_key_value(self, parser):
        """Test object with empty key and value."""
        parser.consume('{"": ""}')
        actual = parser.get()
        assert actual == {"": ""}

    def test_empty_array(self, parser):
        """Test parsing an empty array."""
        parser.consume("[]")
        actual = parser.get()
        assert actual == []

    def test_array_with_single_value(self, parser):
        """Test parsing an array with a single string value."""
        parser.consume('["test"]')
        actual = parser.get()
        assert actual == ["test"]

    def test_array_with_multiple_values(self, parser):
        """Test parsing an array with multiple string values."""
        parser.consume('["test1", "test2", "test3"]')
        actual = parser.get()
        assert actual == ["test1", "test2", "test3"]

    def test_array_with_partial_input(self, parser):
        """Test parsing an array with partial input in multiple chunks."""
        parser.consume('["test1"')
        actual = parser.get()
        assert actual == ["test1"]

        parser.consume(', "test2"')
        actual = parser.get()
        assert actual == ["test1", "test2"]

        parser.consume("]")
        actual = parser.get()
        assert actual == ["test1", "test2"]

    def test_nested_array_in_object(self, parser):
        """Test parsing an object containing an array."""
        parser.consume('{"values": ["test1", "test2"]}')
        actual = parser.get()
        assert actual == {"values": ["test1", "test2"]}

    def test_array_in_object_partial(self, parser):
        """Test parsing an object with array using partial input."""
        parser.consume('{"values": [')
        actual = parser.get()
        assert actual == {"values": []}

        parser.consume('"test1", ')
        actual = parser.get()
        assert actual == {"values": ["test1"]}

        parser.consume('"test2"]}')
        actual = parser.get()
        assert actual == {"values": ["test1", "test2"]}

    def test_object_number_integer(self, parser):
        """Test object with integer values."""
        parser.consume('{"key": 123}')
        actual = parser.get()
        assert actual == {"key": 123}

    def test_object_number_single_tokens(self, parser):
        """Test object with negative numbers."""
        parser.consume('{"key": ')
        parser.consume("-456")
        parser.consume("}")
        actual = parser.get()
        assert actual == {"key": -456}

    def test_object_number_negative(self, parser):
        """Test object with negative numbers."""
        parser.consume('{"key": -456}')
        actual = parser.get()
        assert actual == {"key": -456}

    def test_object_number_float(self, parser):
        """Test object with floating point numbers."""
        parser.consume('{"key": 123.456}')
        actual = parser.get()
        assert actual == {"key": 123.456}

    def test_object_number_negative_float(self, parser):
        """Test object with negative floating point numbers."""
        parser.consume('{"key": -123.456}')
        actual = parser.get()
        assert actual == {"key": -123.456}

    def test_object_number_scientific(self, parser):
        """Test object with scientific notation numbers."""
        test_cases = [
            ('{"key": 1.23e4}', {"key": 1.23e4}),
            ('{"key": 1.23E4}', {"key": 1.23e4}),
            ('{"key": -1.23e-4}', {"key": -1.23e-4}),
            ('{"key": 1.23e+4}', {"key": 1.23e4}),
        ]
        for json_input, expected in test_cases:
            parser = StreamJsonParser()  # Reset parser for each case
            parser.consume(json_input)
            actual = parser.get()
            assert actual == expected

    def test_object_number_corner_cases(self, parser):
        """Test object with number corner cases."""
        test_cases = [
            ('{"key": 0}', {"key": 0}),
            ('{"key": -0}', {"key": -0}),
            ('{"key": 0.0}', {"key": 0.0}),
            ('{"key": 1e0}', {"key": 1e0}),
            ('{"key": 1E-0}', {"key": 1e-0}),
        ]
        for json_input, expected in test_cases:
            parser = StreamJsonParser()  # Reset parser for each case
            parser.consume(json_input)
            actual = parser.get()
            assert actual == expected

    def test_object_number_partial(self, parser):
        """Test object with partial number input."""
        # Test partial integer
        parser.consume('{"key": 12')
        actual = parser.get()
        assert actual == {"key": 12}

        # Test partial float
        parser = StreamJsonParser()
        parser.consume('{"key": 12.')
        actual = parser.get()
        assert actual == {"key": 12.0}

        # Test partial scientific notation
        parser = StreamJsonParser()
        parser.consume('{"key": 1.2e0')
        actual = parser.get()
        assert actual == {"key": 1.2e0}

    def test_object_number_malformed(self, parser):
        """Test object with malformed numbers."""
        invalid_cases = [
            '{"key": 12..34}',  # Double decimal
            '{"key": 12.34.56}',  # Multiple decimals
            '{"key": 12ee4}',  # Double exponent
            '{"key": --123}',  # Double negative
            '{"key": 12e4.5}',  # Decimal in exponent
            '{"key": 12e}',  # No exp value
        ]
        for json_input in invalid_cases:
            parser = StreamJsonParser()
            with pytest.raises(StreamParserJSONDecodeError):
                parser.consume(json_input)
                parser.get()

    def test_array_mixed_types(self, parser):
        """Test array with different types of values."""
        parser.consume('[1, "string", true, null, 3.14, -42]')
        actual = parser.get()
        assert actual == [1, "string", True, None, 3.14, -42]

    def test_array_nested_arrays(self, parser):
        """Test array containing other arrays."""
        parser.consume("[[1, 2], [3, 4], []]")
        actual = parser.get()
        assert actual == [[1, 2], [3, 4], []]

    def test_array_nested_objects(self, parser):
        """Test array containing objects."""
        parser.consume('[{"a": 1}, {"b": 2}, {}]')
        actual = parser.get()
        assert actual == [{"a": 1}, {"b": 2}, {}]

    def test_array_complex_nesting(self, parser):
        """Test array with complex nesting of arrays and objects."""
        parser.consume('[{"arr": [1, 2, {"x": [3, 4]}]}, [5, {"y": 6}]]')
        actual = parser.get()
        assert actual == [{"arr": [1, 2, {"x": [3, 4]}]}, [5, {"y": 6}]]

    def test_array_whitespace(self, parser):
        """Test array with various whitespace patterns."""
        test_cases = [
            ("[  1  ,  2  ]", [1, 2]),
            ("[\n1,\n2\n]", [1, 2]),
            ("[\r1,\t2\r\n]", [1, 2]),
            ("[ ]", []),
        ]
        for json_input, expected in test_cases:
            parser = StreamJsonParser()
            parser.consume(json_input)
            actual = parser.get()
            assert actual == expected

    def test_array_partial_complex(self, parser):
        """Test partial parsing of complex array structures."""
        # Start with empty array in object
        parser.consume('{"data": [')
        actual = parser.get()
        assert actual == {"data": []}

        # Add nested object
        parser.consume('{"nested": [1, 2]}')
        actual = parser.get()
        assert actual == {"data": [{"nested": [1, 2]}]}

        # Add comma and start new item
        parser.consume(', {"more": {')
        actual = parser.get()
        assert actual == {"data": [{"nested": [1, 2]}, {"more": {}}]}

        # Complete the structure
        parser.consume('"x": 3}}]}')
        actual = parser.get()
        assert actual == {"data": [{"nested": [1, 2]}, {"more": {"x": 3}}]}

    def test_array_malformed(self, parser):
        """Test malformed array inputs."""
        invalid_cases = [
            "[,]",  # Empty element
            "[1, , 2]",  # Missing element
            "[1, 2]]",  # Extra closing bracket
        ]
        for json_input in invalid_cases:
            parser = StreamJsonParser()
            with pytest.raises(StreamParserJSONDecodeError):
                parser.consume(json_input)
                parser.get()

    def test_array_streaming_edge_cases(self, parser):
        """Test edge cases in streaming array parsing."""
        # Test extremely small chunks
        parser.consume("[")
        actual = parser.get()
        assert actual == []

        parser.consume('"')
        parser.consume("t")
        parser.consume("e")
        parser.consume("s")
        parser.consume("t")
        parser.consume('"')
        actual = parser.get()
        assert actual == ["test"]

        # Test multiple commas in chunks
        parser.consume(", ")
        parser.consume("1, ")
        parser.consume("true, ")
        parser.consume("null]")
        actual = parser.get()
        assert actual == ["test", 1, True, None]


if __name__ == "__main__":
    pytest.main()
