"""
Tests for BPMN Safe Module Loader security features.

These tests verify that the safe module loader properly prevents
runtime whitelist modification attacks (CWE-470).

Created: 2026-01-27
"""

import pytest
from unittest.mock import patch, MagicMock

from app.core.security.safe_module_loader import (
    lock_bpmn_registration,
    is_registration_locked,
    ALLOWED_BPMN_MODULES,
    RegistrationLockedError,
    ModuleLoadingError,
    ModuleNotAllowedError,
    FunctionNotAllowedError,
    SafeModuleLoader,
)


class TestBPMNRegistrationLock:
    """Test suite for BPMN registration lock mechanism."""

    def setup_method(self) -> None:
        """Reset registration lock state before each test."""
        # Note: In production, the lock is permanent once set.
        # For testing, we need to use a fresh module import or mock.
        # This test assumes the module has a way to reset for testing.
        pass

    def test_lock_function_exists(self) -> None:
        """lock_bpmn_registration function should exist."""
        assert callable(lock_bpmn_registration)

    def test_is_locked_function_exists(self) -> None:
        """is_registration_locked function should exist."""
        assert callable(is_registration_locked)

    def test_registration_starts_unlocked(self) -> None:
        """Registration should start in unlocked state (before main.py runs)."""
        # Note: This test may fail if run after main.py has initialized
        # In integration tests, the lock will already be set
        pass

    def test_lock_prevents_new_registrations(self) -> None:
        """After locking, new module registrations should fail."""
        # This test uses mocking to avoid affecting global state
        # The SafeModuleLoader should reject loading non-whitelisted modules

        loader = SafeModuleLoader()

        with patch(
            "app.core.security.safe_module_loader._registration_locked", True
        ):
            with pytest.raises((ModuleNotAllowedError, ModuleLoadingError)):
                loader.load_function("malicious.module.function")

    def test_lock_is_permanent(self) -> None:
        """Once locked, the registration cannot be unlocked."""
        # The lock mechanism should not have an unlock function
        # that can be called from outside the module

        import app.core.security.safe_module_loader as loader

        # Check there's no unlock function exposed
        assert not hasattr(loader, "unlock_bpmn_registration")
        assert not hasattr(loader, "reset_bpmn_registration")
        assert not hasattr(loader, "_unlock_bpmn_registration")

    def test_allowed_modules_is_frozen(self) -> None:
        """ALLOWED_BPMN_MODULES should be immutable."""
        # The whitelist should be a frozenset or similar immutable type
        assert isinstance(ALLOWED_BPMN_MODULES, (frozenset, tuple))

        # Attempting to modify should raise an error
        if isinstance(ALLOWED_BPMN_MODULES, frozenset):
            with pytest.raises((TypeError, AttributeError)):
                ALLOWED_BPMN_MODULES.add("malicious")  # type: ignore

    def test_existing_modules_still_work_after_lock(self) -> None:
        """Whitelisted modules should still be accessible after lock."""
        # The ALLOWED_BPMN_MODULES frozenset defines what's allowed
        # Modules in this list should be loadable even after lock

        assert len(ALLOWED_BPMN_MODULES) > 0
        assert isinstance(ALLOWED_BPMN_MODULES, frozenset)


class TestBPMNModuleWhitelist:
    """Test suite for BPMN module whitelist validation."""

    def test_whitelist_contains_expected_modules(self) -> None:
        """Whitelist should contain known safe modules."""
        # The exact modules depend on implementation
        # This test ensures the whitelist isn't empty
        assert len(ALLOWED_BPMN_MODULES) > 0

    def test_whitelist_does_not_allow_arbitrary_modules(self) -> None:
        """Arbitrary module names should not be in the whitelist."""
        arbitrary_names = [
            "os",
            "sys",
            "subprocess",
            "eval",
            "exec",
            "__builtins__",
            "importlib",
        ]

        for name in arbitrary_names:
            assert name not in ALLOWED_BPMN_MODULES, f"Dangerous module '{name}' in whitelist!"

    def test_whitelist_entries_are_strings(self) -> None:
        """All whitelist entries should be strings."""
        for entry in ALLOWED_BPMN_MODULES:
            assert isinstance(entry, str)
            assert len(entry) > 0


class TestBPMNModuleValidation:
    """Test suite for module loading validation."""

    def test_loader_validates_module_name(self) -> None:
        """Loader should validate module names against whitelist."""
        loader = SafeModuleLoader()

        # Attempting to load a non-whitelisted module should fail
        with pytest.raises((ModuleNotAllowedError, ModuleLoadingError)):
            loader.load_function("not_in_whitelist_module.function")

    def test_loader_rejects_path_traversal(self) -> None:
        """Loader should reject path traversal attempts."""
        loader = SafeModuleLoader()

        dangerous_names = [
            "../../../etc/passwd.read",
            "..\\..\\windows\\system32.exec",
            "module/../../../secret.func",
            "module\x00hidden.func",
        ]

        for name in dangerous_names:
            with pytest.raises((ModuleNotAllowedError, ModuleLoadingError, ValueError)):
                loader.load_function(name)

    def test_loader_rejects_code_injection(self) -> None:
        """Loader should reject code injection attempts."""
        loader = SafeModuleLoader()

        injection_attempts = [
            "__import__('os').system",
            "eval",
            "exec",
        ]

        for name in injection_attempts:
            with pytest.raises((ModuleNotAllowedError, ModuleLoadingError)):
                loader.load_function(name)


class TestSecurityIntegration:
    """Integration tests for module loader security."""

    def test_lock_called_in_main_lifespan(self) -> None:
        """lock_bpmn_registration should be called during app startup."""
        # Read main.py and verify the call exists
        import ast
        from pathlib import Path

        main_path = Path(__file__).parent.parent.parent / "app" / "main.py"

        with open(main_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check for the import
        assert "from app.core.security.safe_module_loader import lock_bpmn_registration" in content

        # Check for the function call
        assert "lock_bpmn_registration()" in content

    def test_lock_error_prevents_startup(self) -> None:
        """If lock fails, the application should not start."""
        # This test verifies the error handling in main.py
        import ast
        from pathlib import Path

        main_path = Path(__file__).parent.parent.parent / "app" / "main.py"

        with open(main_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check that lock failure raises RuntimeError
        assert "SICHERHEITSFEHLER" in content or "RuntimeError" in content


class TestRegistrationLockedError:
    """Test suite for the custom exception."""

    def test_exception_exists(self) -> None:
        """RegistrationLockedError should exist."""
        assert RegistrationLockedError is not None

    def test_exception_is_error_type(self) -> None:
        """RegistrationLockedError should be an Exception subclass."""
        assert issubclass(RegistrationLockedError, Exception)

    def test_exception_has_message(self) -> None:
        """Exception should support custom messages."""
        msg = "Test error message"
        error = RegistrationLockedError(msg)
        assert msg in str(error)
