# -*- coding: utf-8 -*-
"""
Tests for SafeModuleLoader and BPMN Registration Lock.

Tests the secure module loading with whitelists and registration locking.
Covers CWE-470: Use of Externally-Controlled Input to Select Classes or Code.
"""

import pytest
from unittest.mock import patch, MagicMock
import threading

from app.core.security.safe_module_loader import (
    SafeModuleLoader,
    ModuleLoadingError,
    ModuleNotAllowedError,
    FunctionNotAllowedError,
    RegistrationLockedError,
    ALLOWED_BPMN_MODULES,
    ALLOWED_BPMN_FUNCTIONS,
    lock_bpmn_registration,
    is_registration_locked,
    register_bpmn_function,
    safe_load_function,
    is_function_allowed,
    get_default_loader,
)


class TestSafeModuleLoader:
    """Tests for SafeModuleLoader class."""

    def test_default_whitelists_loaded(self) -> None:
        """Default loader should have BPMN whitelists."""
        loader = SafeModuleLoader()
        assert loader.allowed_modules == ALLOWED_BPMN_MODULES
        assert loader.allowed_functions == ALLOWED_BPMN_FUNCTIONS

    def test_custom_whitelists(self) -> None:
        """Custom whitelists should override defaults."""
        custom_modules = frozenset({"my.module"})
        custom_functions = {"my.module": frozenset({"my_func"})}

        loader = SafeModuleLoader(
            allowed_modules=custom_modules,
            allowed_functions=custom_functions,
        )

        assert loader.allowed_modules == custom_modules
        assert loader.allowed_functions == custom_functions

    def test_is_module_allowed_whitelisted(self) -> None:
        """Whitelisted modules should return True."""
        loader = SafeModuleLoader()
        # Check one of the default whitelisted modules
        assert loader.is_module_allowed("app.services.bpmn.notifications") is True

    def test_is_module_allowed_not_whitelisted(self) -> None:
        """Non-whitelisted modules should return False."""
        loader = SafeModuleLoader()
        assert loader.is_module_allowed("os") is False
        assert loader.is_module_allowed("subprocess") is False
        assert loader.is_module_allowed("__builtins__") is False

    def test_is_function_allowed_whitelisted(self) -> None:
        """Whitelisted functions should return True."""
        loader = SafeModuleLoader()
        assert loader.is_function_allowed(
            "app.services.bpmn.notifications",
            "send_approval_email",
        ) is True

    def test_is_function_allowed_not_whitelisted(self) -> None:
        """Non-whitelisted functions should return False."""
        loader = SafeModuleLoader()
        # Module exists but function doesn't
        assert loader.is_function_allowed(
            "app.services.bpmn.notifications",
            "execute_shell_command",  # Dangerous, not whitelisted
        ) is False

    def test_is_function_allowed_module_not_exists(self) -> None:
        """Functions in non-existent modules should return False."""
        loader = SafeModuleLoader()
        assert loader.is_function_allowed("evil.module", "func") is False


class TestModuleLoading:
    """Tests for actual module loading."""

    def test_load_module_not_allowed(self) -> None:
        """Loading non-whitelisted module should raise."""
        loader = SafeModuleLoader()
        with pytest.raises(ModuleNotAllowedError) as exc_info:
            loader.load_module("os")
        assert "nicht erlaubt" in str(exc_info.value)

    def test_load_module_dangerous_builtin(self) -> None:
        """Loading dangerous builtins should raise."""
        loader = SafeModuleLoader()
        dangerous_modules = ["subprocess", "shutil", "pickle", "marshal"]
        for module in dangerous_modules:
            with pytest.raises(ModuleNotAllowedError):
                loader.load_module(module)


class TestFunctionLoading:
    """Tests for function loading with path parsing."""

    def test_load_function_invalid_path_no_dot(self) -> None:
        """Path without dot should raise."""
        loader = SafeModuleLoader()
        with pytest.raises(ModuleLoadingError) as exc_info:
            loader.load_function("no_dot_in_path")
        assert "Ungültig" in str(exc_info.value) or "ungültig" in str(exc_info.value).lower()

    def test_load_function_invalid_path_empty(self) -> None:
        """Empty path should raise."""
        loader = SafeModuleLoader()
        with pytest.raises(ModuleLoadingError):
            loader.load_function("")

    def test_load_function_invalid_function_name(self) -> None:
        """Invalid function names should raise."""
        loader = SafeModuleLoader()
        # Function name with special characters
        with pytest.raises(ModuleLoadingError):
            loader.load_function("app.module.func-name")

    def test_load_function_module_not_allowed(self) -> None:
        """Loading function from non-whitelisted module should raise."""
        loader = SafeModuleLoader()
        with pytest.raises(ModuleNotAllowedError):
            loader.load_function("os.system")

    def test_load_function_not_allowed(self) -> None:
        """Loading non-whitelisted function should raise."""
        loader = SafeModuleLoader()
        with pytest.raises(FunctionNotAllowedError):
            loader.load_function("app.services.bpmn.notifications.evil_function")

    def test_path_traversal_prevention(self) -> None:
        """Path traversal attempts should be blocked."""
        loader = SafeModuleLoader()
        malicious_paths = [
            "app.services.bpmn.notifications..send_email",
            "..app.services.evil",
            "app.services.__init__",
        ]
        for path in malicious_paths:
            with pytest.raises((ModuleNotAllowedError, ModuleLoadingError)):
                loader.load_function(path)


class TestRegistrationLock:
    """Tests for BPMN registration locking mechanism."""

    def setup_method(self) -> None:
        """Reset lock state before each test."""
        # We need to reset the global state for testing
        import app.core.security.safe_module_loader as module
        module._registration_locked = False
        module._default_loader = None

    def test_lock_bpmn_registration(self) -> None:
        """lock_bpmn_registration should lock registration."""
        import app.core.security.safe_module_loader as module
        module._registration_locked = False

        assert is_registration_locked() is False
        lock_bpmn_registration()
        assert is_registration_locked() is True

    def test_register_function_before_lock(self) -> None:
        """Registration should work before lock."""
        import app.core.security.safe_module_loader as module
        module._registration_locked = False
        module._default_loader = None

        # Should not raise
        register_bpmn_function("test.module", "test_function")

        # Verify it was added
        loader = get_default_loader()
        assert loader.is_module_allowed("test.module")
        assert loader.is_function_allowed("test.module", "test_function")

    def test_register_function_after_lock_raises(self) -> None:
        """Registration after lock should raise RegistrationLockedError."""
        import app.core.security.safe_module_loader as module
        module._registration_locked = False

        lock_bpmn_registration()

        with pytest.raises(RegistrationLockedError) as exc_info:
            register_bpmn_function("evil.module", "evil_function")
        assert "gesperrt" in str(exc_info.value)

    def test_lock_is_permanent(self) -> None:
        """Lock should be permanent (cannot be undone)."""
        import app.core.security.safe_module_loader as module
        module._registration_locked = False

        lock_bpmn_registration()
        # Try to unlock (this should not be possible through public API)
        # The only way to unlock is restarting the application

        assert is_registration_locked() is True
        # Calling lock again should just be a no-op
        lock_bpmn_registration()
        assert is_registration_locked() is True

    def test_concurrent_registration_safety(self) -> None:
        """Registration lock should be thread-safe."""
        import app.core.security.safe_module_loader as module
        module._registration_locked = False

        results = []

        def try_register(idx: int) -> None:
            try:
                register_bpmn_function(f"test.module{idx}", f"func{idx}")
                results.append(("success", idx))
            except RegistrationLockedError:
                results.append(("locked", idx))

        def do_lock() -> None:
            lock_bpmn_registration()

        # Start multiple threads
        threads = []
        for i in range(5):
            t = threading.Thread(target=try_register, args=(i,))
            threads.append(t)

        lock_thread = threading.Thread(target=do_lock)
        threads.append(lock_thread)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # After all threads finish, registration should be locked
        assert is_registration_locked() is True


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def setup_method(self) -> None:
        """Reset state before each test."""
        import app.core.security.safe_module_loader as module
        module._registration_locked = False
        module._default_loader = None

    def test_get_default_loader_singleton(self) -> None:
        """get_default_loader should return same instance."""
        loader1 = get_default_loader()
        loader2 = get_default_loader()
        assert loader1 is loader2

    def test_is_function_allowed_convenience(self) -> None:
        """is_function_allowed convenience function should work."""
        assert is_function_allowed(
            "app.services.bpmn.notifications.send_approval_email"
        ) is True
        assert is_function_allowed("os.system") is False

    def test_is_function_allowed_invalid_path(self) -> None:
        """is_function_allowed should handle invalid paths."""
        assert is_function_allowed("nodot") is False
        assert is_function_allowed("") is False


class TestSecurityScenarios:
    """Security-focused test scenarios."""

    def test_prevent_arbitrary_code_execution(self) -> None:
        """Should prevent loading arbitrary code execution functions."""
        loader = SafeModuleLoader()
        dangerous_paths = [
            "os.system",
            "subprocess.call",
            "subprocess.Popen",
            "eval.eval",
            "exec.exec",
            "builtins.__import__",
            "importlib.import_module",
        ]
        for path in dangerous_paths:
            with pytest.raises((ModuleNotAllowedError, ModuleLoadingError)):
                loader.load_function(path)

    def test_prevent_file_system_access(self) -> None:
        """Should prevent loading file system access functions."""
        loader = SafeModuleLoader()
        fs_paths = [
            "os.remove",
            "os.unlink",
            "shutil.rmtree",
            "pathlib.Path.unlink",
        ]
        for path in fs_paths:
            with pytest.raises((ModuleNotAllowedError, ModuleLoadingError)):
                loader.load_function(path)

    def test_prevent_network_access(self) -> None:
        """Should prevent loading network access functions."""
        loader = SafeModuleLoader()
        network_paths = [
            "socket.socket",
            "urllib.request.urlopen",
            "requests.get",
        ]
        for path in network_paths:
            with pytest.raises((ModuleNotAllowedError, ModuleLoadingError)):
                loader.load_function(path)

    def test_whitelist_is_frozen(self) -> None:
        """Whitelists should be immutable frozensets."""
        assert isinstance(ALLOWED_BPMN_MODULES, frozenset)
        for funcs in ALLOWED_BPMN_FUNCTIONS.values():
            assert isinstance(funcs, frozenset)


class TestErrorMessages:
    """Tests for German error messages."""

    def test_module_not_allowed_german_message(self) -> None:
        """ModuleNotAllowedError should have German message."""
        loader = SafeModuleLoader()
        with pytest.raises(ModuleNotAllowedError) as exc_info:
            loader.load_module("evil.module")
        assert "Modul nicht erlaubt" in str(exc_info.value)

    def test_function_not_allowed_german_message(self) -> None:
        """FunctionNotAllowedError should have German message."""
        loader = SafeModuleLoader()
        with pytest.raises(FunctionNotAllowedError) as exc_info:
            loader.load_function("app.services.bpmn.notifications.evil_func")
        assert "Funktion nicht erlaubt" in str(exc_info.value)

    def test_registration_locked_german_message(self) -> None:
        """RegistrationLockedError should have German message."""
        import app.core.security.safe_module_loader as module
        module._registration_locked = False

        lock_bpmn_registration()
        with pytest.raises(RegistrationLockedError) as exc_info:
            register_bpmn_function("test.module", "test_func")
        assert "gesperrt" in str(exc_info.value)
