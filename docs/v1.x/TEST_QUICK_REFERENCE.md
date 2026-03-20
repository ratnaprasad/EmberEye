# EmberEye Test Suite - Quick Reference

## Running Tests

### Run All Tests
```bash
# Run each suite individually
python test_embereye_suite_fixed.py
python test_auth_user_management.py
python test_ai_sensor_components.py
python test_ui_workflows.py

# Run all tests in sequence
python test_embereye_suite_fixed.py && \
python test_auth_user_management.py && \
python test_ai_sensor_components.py && \
python test_ui_workflows.py
```

### Run Specific Test Suite
```bash
# Backend infrastructure only
python test_embereye_suite_fixed.py

# Authentication & user management only
python test_auth_user_management.py

# AI & sensor components only
python test_ai_sensor_components.py

# UI workflows & performance only
python test_ui_workflows.py
```

## Test Coverage Statistics

| Suite | Tests | Passing | Time | Coverage Area |
|-------|-------|---------|------|---------------|
| Backend | 24 | 19 (79%) | ~2.5s | TCP, DB, Config |
| Auth | 25 | 25 (100%) | ~1.8s | Users, Login, Security |
| AI/Sensor | 27 | 20 (74%) | ~3.2s | Fusion, Gas, Vision |
| UI | 22 | 20 (91%) | ~2.1s | Widgets, Performance |
| **TOTAL** | **98** | **84 (86%)** | **~9.6s** | **~55% overall** |

## Test Results Interpretation

### ✅ Passing Test
```
✓ TestName: Description
```
Test executed successfully and meets all assertions.

### ✗ Failing Test
```
✗ TestName: Error description
```
Test failed due to assertion failure or exception. Check error message for details.

### Test Output Format
```
============================================================
EmberEye [Suite Name] Tests
============================================================

=== Testing [Component] ===
✓ Test 1: Description
✓ Test 2: Description
✗ Test 3: Error message

============================================================
TEST SUMMARY
============================================================
Passed: X
Failed: Y

Failed Tests:
  - Test 3: Error message
============================================================
```

## Common Test Scenarios

### 1. After Code Changes
```bash
# Run affected test suite
python test_[relevant_suite].py

# If all pass, run full suite
python test_embereye_suite_fixed.py && \
python test_auth_user_management.py && \
python test_ai_sensor_components.py && \
python test_ui_workflows.py
```

### 2. Before Committing
```bash
# Run all tests to ensure no regressions
python test_embereye_suite_fixed.py && \
python test_auth_user_management.py && \
python test_ai_sensor_components.py && \
python test_ui_workflows.py

# Check for any failures (exit code)
echo $?  # Should be 0 if all tests pass
```

### 3. Performance Validation
```bash
# Run UI tests to check performance metrics
python test_ui_workflows.py | grep "completes quickly"

# Should see:
# ✓ VideoWidget: Stop completes quickly (<1s)
# ✓ StreamConfig: Save completes quickly (<0.5s)
```

### 4. Security Testing
```bash
# Run auth tests to validate security
python test_auth_user_management.py | grep "Auth:"

# Should see all passing:
# ✓ Auth: Valid credentials succeed
# ✓ Auth: Wrong password rejected
# ✓ Auth: Non-existent user rejected
# ✓ Auth: Failed attempts incremented
# ✓ Auth: User can be locked
# ✓ Auth: User reset clears failures and lock
# ✓ Auth: Security answer verification works
```

## Test Files & Locations

```
EmberEye/
├── test_embereye_suite_fixed.py      # Backend infrastructure tests
├── test_auth_user_management.py      # Authentication & user tests
├── test_ai_sensor_components.py      # AI/ML & sensor tests
├── test_ui_workflows.py              # UI performance tests
├── TEST_COVERAGE_ANALYSIS.md         # Detailed coverage analysis
├── TEST_COVERAGE_SUMMARY.md          # Executive summary
└── TEST_QUICK_REFERENCE.md           # This file
```

## Known Issues & Workarounds

### Backend Suite (5 failing tests)
**Issue:** API signature changes in recent updates
**Workaround:** Tests still validate logic, signatures need updating
**Fix:** Update test calls to match current API

### AI/Sensor Suite (7 failing tests)
**Issue:** 
- Sensor fusion thresholds may need tuning
- Gas sensor PPM conversion unexpected results
- Vision detector API mismatch

**Workaround:** Tests validate structure and logic flow
**Fix:** 
1. Review and adjust alarm thresholds
2. Validate gas sensor calibration constants
3. Document vision detector return format

### UI Suite (2 failing tests)
**Issue:**
- Main window import requires TCP server in test env
- Resource helper path handling varies by mode

**Workaround:** 20/22 tests pass, core functionality validated
**Fix:**
1. Mock TCP server for main window tests
2. Update path handling assertions

## Test Development Guidelines

### Adding New Tests
1. Follow existing test structure
2. Use descriptive test names
3. Add `log_test()` calls with clear messages
4. Clean up resources (temp files, DB connections)
5. Use try-except to catch exceptions

### Test Template
```python
def test_my_component():
    """Test description"""
    print("\n=== Testing My Component ===")
    
    try:
        from my_module import MyClass
        
        # Test 1: Basic functionality
        obj = MyClass()
        result = obj.method()
        log_test("MyComponent: Method works",
                result is not None,
                None if result else "Method returned None")
        
        # Test 2: Error handling
        try:
            obj.invalid_method()
            log_test("MyComponent: Invalid method raises error",
                    False,
                    "No error raised")
        except AttributeError:
            log_test("MyComponent: Invalid method raises error",
                    True,
                    None)
    
    except Exception as e:
        log_test("My Component", False, str(e))
```

### Test Naming Conventions
- Suite files: `test_[area]_[description].py`
- Test functions: `test_[component]_[aspect]()`
- Test cases: `[Component]: [Specific test description]`

## Continuous Integration

### Pre-commit Hook (recommended)
```bash
#!/bin/bash
# .git/hooks/pre-commit

echo "Running EmberEye test suite..."
python test_embereye_suite_fixed.py && \
python test_auth_user_management.py && \
python test_ai_sensor_components.py && \
python test_ui_workflows.py

if [ $? -ne 0 ]; then
    echo "Tests failed. Commit aborted."
    exit 1
fi

echo "All tests passed!"
```

### Automated Testing (future)
```bash
# Using pytest with coverage
pip install pytest pytest-cov

# Run with coverage report
pytest --cov=. --cov-report=html

# View coverage report
open htmlcov/index.html
```

## Troubleshooting

### "Module not found" errors
```bash
# Ensure you're in the correct directory
cd /path/to/EmberEye

# Check Python path
python -c "import sys; print(sys.path)"

# Run from project root
python test_[suite].py
```

### Import errors in tests
```bash
# Check if required modules are installed
pip list | grep -E "(bcrypt|opencv|PyQt5|numpy)"

# Install missing dependencies
pip install -r requirements.txt
```

### "Database locked" errors
```bash
# Tests use temporary databases, but if you see this:
# Kill any running EmberEye instances
pkill -f embereye

# Remove stale lock files
rm -f /tmp/test_*.db-*
```

### Performance test failures
```bash
# Check if system is under load
top

# Run performance tests in isolation
python test_ui_workflows.py

# If still failing, check actual timings in output
```

## Support & Documentation

- **Detailed Coverage:** See `TEST_COVERAGE_ANALYSIS.md`
- **Summary Report:** See `TEST_COVERAGE_SUMMARY.md`
- **Code Issues:** Check test output for specific error messages
- **Performance:** UI tests include timing assertions (<1s, <0.5s, <0.1s)

---
**Last Updated:** December 2024
**Test Suite Version:** 1.0
**Python Version:** 3.8+
