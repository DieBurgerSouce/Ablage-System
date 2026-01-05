"""Unit tests for TokenCounter."""

import pytest
import sys
from pathlib import Path

# Add orchestration to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / ".claude" / "orchestration"))

from token_counter import TokenCounter, ContentType


class TestTokenCounter:
    """Test suite for token counting."""

    def test_count_tokens_basic(self):
        """Should count tokens for basic text."""
        counter = TokenCounter()
        text = "This is a simple test sentence."

        tokens = counter.count_tokens(text)
        assert tokens > 0
        assert isinstance(tokens, int)

    def test_prose_content_type(self):
        """Should handle prose content type."""
        counter = TokenCounter()
        prose = "The quick brown fox jumps over the lazy dog. This is a common English sentence used for testing."

        tokens = counter.count_tokens(prose, content_type=ContentType.PROSE)
        # Prose typically has ~4 chars per token
        expected_approx = len(prose) // 4
        assert 0.80 * expected_approx <= tokens <= 1.20 * expected_approx

    def test_code_content_type(self):
        """Should handle code content type."""
        counter = TokenCounter()
        code = '''
def hello_world():
    print("Hello, World!")
    return 42
'''

        tokens = counter.count_tokens(code, content_type=ContentType.CODE)
        # Code typically has more tokens due to symbols
        assert tokens > 0

    def test_json_content_type(self):
        """Should handle JSON content type."""
        counter = TokenCounter()
        json_text = '''
{
    "name": "Test",
    "value": 123,
    "items": ["a", "b", "c"]
}
'''

        tokens = counter.count_tokens(json_text, content_type=ContentType.JSON)
        # JSON has overhead from brackets, quotes, etc.
        assert tokens > 0

    def test_markdown_content_type(self):
        """Should handle Markdown content type."""
        counter = TokenCounter()
        markdown = '''
# Header

This is **bold** and this is *italic*.

- List item 1
- List item 2
'''

        tokens = counter.count_tokens(markdown, content_type=ContentType.MARKDOWN)
        assert tokens > 0

    def test_german_text_efficiency(self):
        """German text should have similar token efficiency to English."""
        counter = TokenCounter()
        german = "Dies ist ein deutscher Testsatz mit Umlauten: äöüß"
        english = "This is an English test sentence with special chars"

        german_tokens = counter.count_tokens(german, content_type=ContentType.PROSE)
        english_tokens = counter.count_tokens(english, content_type=ContentType.PROSE)

        # Token counts should be similar
        ratio = german_tokens / english_tokens
        assert 0.80 <= ratio <= 1.20  # Within 20% of each other

    def test_empty_text_returns_zero(self):
        """Empty text should return zero tokens."""
        counter = TokenCounter()
        assert counter.count_tokens("") == 0

    def test_whitespace_only_minimal_tokens(self):
        """Whitespace-only text should return minimal tokens."""
        counter = TokenCounter()
        tokens = counter.count_tokens("   \n\n\t\t   ")
        assert tokens <= 5  # Should be very small

    def test_special_characters_overhead(self):
        """Special characters should add token overhead."""
        counter = TokenCounter()
        simple = "a" * 100
        complex = "!@#$%^&*()" * 10

        simple_tokens = counter.count_tokens(simple)
        complex_tokens = counter.count_tokens(complex)

        # Complex should have more tokens per character
        assert complex_tokens > simple_tokens

    def test_accuracy_within_target_range(self):
        """Token estimation should be within ±10% of actual for common text."""
        counter = TokenCounter()

        # Test cases with approximate known token counts
        test_cases = [
            ("Hello world", 2),  # ~2 tokens
            ("This is a test sentence.", 6),  # ~6 tokens
            ("The quick brown fox jumps", 5),  # ~5 tokens
        ]

        for text, expected in test_cases:
            estimated = counter.count_tokens(text, content_type=ContentType.PROSE)
            error_pct = abs(estimated - expected) / expected
            assert error_pct < 0.15, f"Error too high for '{text}': {error_pct:.1%}"

    def test_code_with_indentation(self):
        """Code with indentation should count correctly."""
        counter = TokenCounter()
        indented_code = '''
class MyClass:
    def __init__(self):
        self.value = 42

    def method(self):
        return self.value * 2
'''

        tokens = counter.count_tokens(indented_code, content_type=ContentType.CODE)
        # Should account for indentation overhead
        assert tokens > 15  # Has meaningful token count

    def test_json_structure_overhead(self):
        """JSON structure should account for brackets, quotes."""
        counter = TokenCounter()
        json_simple = '{"key": "value"}'
        json_nested = '{"outer": {"inner": {"deep": "value"}}}'

        simple_tokens = counter.count_tokens(json_simple, content_type=ContentType.JSON)
        nested_tokens = counter.count_tokens(json_nested, content_type=ContentType.JSON)

        # Nested should have more overhead
        assert nested_tokens > simple_tokens

    def test_content_type_enum_values(self):
        """ContentType should have all required values."""
        assert hasattr(ContentType, 'PROSE')
        assert hasattr(ContentType, 'CODE')
        assert hasattr(ContentType, 'JSON')
        assert hasattr(ContentType, 'MARKDOWN')

    def test_unicode_characters_handling(self):
        """Should handle Unicode characters correctly."""
        counter = TokenCounter()
        unicode_text = "Hello 世界 🌍 Привет"

        tokens = counter.count_tokens(unicode_text)
        assert tokens > 0
        # Should not crash on Unicode

    def test_very_long_text_performance(self):
        """Should handle very long text efficiently."""
        counter = TokenCounter()
        long_text = "This is a test sentence. " * 1000  # ~5000 words

        import time
        start = time.time()
        tokens = counter.count_tokens(long_text, content_type=ContentType.PROSE)
        duration = time.time() - start

        assert tokens > 0
        assert duration < 1.0  # Should complete in under 1 second

    def test_mixed_content_auto_detection(self):
        """Should auto-detect content type if not specified."""
        counter = TokenCounter()

        # Code-like content
        code_text = "def function():\n    return 42"
        code_tokens = counter.count_tokens(code_text)
        assert code_tokens > 0

        # Prose-like content
        prose_text = "This is a normal sentence with common words."
        prose_tokens = counter.count_tokens(prose_text)
        assert prose_tokens > 0

    def test_markdown_formatting_overhead(self):
        """Markdown formatting should add token overhead."""
        counter = TokenCounter()
        plain = "This is bold and this is italic"
        markdown = "This is **bold** and this is *italic*"

        plain_tokens = counter.count_tokens(plain, content_type=ContentType.PROSE)
        markdown_tokens = counter.count_tokens(markdown, content_type=ContentType.MARKDOWN)

        # Markdown should have slightly more tokens due to formatting
        assert markdown_tokens >= plain_tokens

    def test_consistency_across_calls(self):
        """Same text should always return same token count."""
        counter = TokenCounter()
        text = "Consistent token counting is important."

        tokens1 = counter.count_tokens(text)
        tokens2 = counter.count_tokens(text)
        tokens3 = counter.count_tokens(text)

        assert tokens1 == tokens2 == tokens3

    def test_newlines_and_spacing_handling(self):
        """Should handle newlines and spacing correctly."""
        counter = TokenCounter()
        compact = "Line1Line2Line3"
        spaced = "Line1\n\nLine2\n\nLine3"

        compact_tokens = counter.count_tokens(compact)
        spaced_tokens = counter.count_tokens(spaced)

        # Spaced should have slightly more tokens
        assert spaced_tokens >= compact_tokens

    def test_code_comments_counted(self):
        """Code comments should be counted in token total."""
        counter = TokenCounter()
        code_with_comments = '''
# This is a comment
def function():
    # Another comment
    return 42
'''

        tokens = counter.count_tokens(code_with_comments, content_type=ContentType.CODE)
        # Should include comment tokens
        assert tokens > 10
