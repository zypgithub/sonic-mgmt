"""
High Frequency Telemetry tests with WJH toggle support.

This module dynamically imports all test functions (starting with 'test_')
from the original high_frequency_telemetry test module.

Usage:
    pytest tests/high_frequency_telemetry_with_wjh/test_high_frequency_telemetry_with_wjh.py
"""
import inspect

# Import the original test module
import tests.high_frequency_telemetry.test_high_frequency_telemetry as original_tests

# Dynamically import all test functions (functions starting with 'test_')
for name, obj in inspect.getmembers(original_tests, inspect.isfunction):
    if name.startswith('test_'):
        globals()[name] = obj

# Also import pytestmark for test markers
if hasattr(original_tests, 'pytestmark'):
    pytestmark = original_tests.pytestmark
