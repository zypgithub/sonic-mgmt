"""
Test module to verify all modules under tests_nvos can be imported successfully.
This helps catch import errors early in CI.
"""
import importlib
import allure
from pathlib import Path
from typing import List, Tuple

import pytest


def collect_python_modules() -> List[str]:
    """
    Collect all python module paths under tests_nvos directory.
    Returns a list of module paths like 'ngts.tests_nvos.system.test_example'.
    """
    tests_nvos_dir = Path(__file__).parent.parent
    base_package = 'ngts.tests_nvos'
    modules = []

    for path in tests_nvos_dir.rglob('test_*.py'):
        # Skip __pycache__ directories
        if '__pycache__' in str(path):
            continue

        # Convert file path to module path
        relative_path = path.relative_to(tests_nvos_dir)
        # Remove .py extension and convert path separators to dots
        module_parts = list(relative_path.parts)
        module_parts[-1] = module_parts[-1].rsplit('.', maxsplit=1)[0]
        module_path = f"{base_package}.{'.'.join(module_parts)}"
        modules.append(module_path)

    return sorted(modules)


def try_import_module(module_path: str) -> Tuple[bool, str]:
    """
    Try to import a module and return success status and error message.
    """
    try:
        importlib.import_module(module_path)
        return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def test_all_modules_can_be_imported():
    """
    Verify that all modules under tests_nvos can be imported.

    This test collects all *.py files under the tests_nvos directory
    and attempts to import each one. Any import failure will cause this
    test to fail, helping catch import errors early in CI.
    """
    with allure.step('Collecting all python files.'):
        test_modules = collect_python_modules()

    assert test_modules, "No python modules found under tests_nvos"

    failed_imports: List[Tuple[str, str]] = []

    with allure.step('Importing all python modules..'):
        for module_path in test_modules:
            success, error = try_import_module(module_path)
            if not success:
                failed_imports.append((module_path, error))

    if failed_imports:
        failure_report = "\n".join(
            f"  - {module}: {error}"
            for module, error in failed_imports
        )
        pytest.fail(
            f"Failed to import {len(failed_imports)} out of {len(test_modules)} modules:\n"
            f"{failure_report}"
        )
