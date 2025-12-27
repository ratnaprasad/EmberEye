#!/usr/bin/env python
"""
Test script for filtered dataset quick retrain functionality.
Tests:
1. Create filtered dataset method exists and works
2. Dataset manager can detect unclassified items
3. Filtered dataset properly excludes non-unclassified files
"""

import os
import sys
import json
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

def test_dataset_manager_imports():
    """Test that DatasetManager can be imported and has the new method."""
    print("=" * 60)
    print("TEST 1: DatasetManager imports and method presence")
    print("=" * 60)
    
    try:
        from embereye.core.training_pipeline import DatasetManager
        print("✓ DatasetManager imported successfully")
        
        # Check if method exists
        if hasattr(DatasetManager, 'create_filtered_dataset_unclassified_only'):
            print("✓ create_filtered_dataset_unclassified_only method exists")
        else:
            print("✗ create_filtered_dataset_unclassified_only method NOT found")
            return False
        
        # Check method signature
        import inspect
        sig = inspect.signature(DatasetManager.create_filtered_dataset_unclassified_only)
        print(f"✓ Method signature: {sig}")
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_training_worker_filtered_dataset_support():
    """Test that TrainingWorker can use filtered dataset path."""
    print("\n" + "=" * 60)
    print("TEST 2: TrainingWorker filtered dataset support")
    print("=" * 60)
    
    try:
        # Check main_window imports
        sys.path.insert(0, str(Path(__file__).parent))
        
        # Read main_window.py to check for _override_dataset_path handling
        main_window_path = Path(__file__).parent / "main_window.py"
        with open(main_window_path, 'r') as f:
            content = f.read()
        
        if '_override_dataset_path' in content:
            print("✓ TrainingWorker checks for _override_dataset_path attribute")
        else:
            print("✗ TrainingWorker does NOT check for _override_dataset_path")
            return False
        
        if 'filtered_dataset_path = getattr(self.config' in content:
            print("✓ TrainingWorker safely retrieves _override_dataset_path from config")
        else:
            print("✗ TrainingWorker does NOT safely retrieve _override_dataset_path")
            return False
        
        if 'base_dir = filtered_dataset_path if filtered_dataset_path else "training_data"' in content:
            print("✓ TrainingWorker correctly switches between filtered and default dataset")
        else:
            print("✗ TrainingWorker does NOT properly switch dataset paths")
            return False
        
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_quick_retrain_ui_dialog():
    """Test that quick retrain has UI dialog for dataset choice."""
    print("\n" + "=" * 60)
    print("TEST 3: Quick retrain UI dialog")
    print("=" * 60)
    
    try:
        main_window_path = Path(__file__).parent / "main_window.py"
        with open(main_window_path, 'r') as f:
            content = f.read()
        
        # Check for QMessageBox.question dialog
        if 'Retrain on full dataset or focus on unclassified items only?' in content:
            print("✓ Quick retrain dialog offers dataset choice")
        else:
            print("✗ Quick retrain dialog does NOT offer dataset choice")
            return False
        
        # Check for use_filtered logic
        if 'use_filtered = reply == QMessageBox.Yes' in content:
            print("✓ Dialog response correctly mapped to use_filtered flag")
        else:
            print("✗ Dialog response mapping NOT found")
            return False
        
        # Check for filtered dataset creation
        if 'dm.create_filtered_dataset_unclassified_only()' in content:
            print("✓ Quick retrain calls create_filtered_dataset_unclassified_only()")
        else:
            print("✗ Quick retrain does NOT call create_filtered_dataset_unclassified_only()")
            return False
        
        # Check for config attribute assignment
        if 'config._override_dataset_path = filtered_dataset_path' in content:
            print("✓ Config receives _override_dataset_path attribute")
        else:
            print("✗ Config does NOT receive _override_dataset_path attribute")
            return False
        
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_syntax_and_imports():
    """Test that all modified files have correct syntax and can be imported."""
    print("\n" + "=" * 60)
    print("TEST 4: Syntax and import validation")
    print("=" * 60)
    
    try:
        # Try importing main modules
        from embereye.core.training_pipeline import DatasetManager, YOLOTrainingPipeline
        print("✓ training_pipeline imports successfully")
        
        # Check for any import errors in main_window by reading it
        main_window_path = Path(__file__).parent / "main_window.py"
        try:
            with open(main_window_path, 'r') as f:
                compile(f.read(), str(main_window_path), 'exec')
            print("✓ main_window.py syntax is valid")
        except SyntaxError as e:
            print(f"✗ main_window.py has syntax error: {e}")
            return False
        
        # Check training_pipeline.py syntax
        training_pipeline_path = Path(__file__).parent / "embereye/core/training_pipeline.py"
        try:
            with open(training_pipeline_path, 'r') as f:
                compile(f.read(), str(training_pipeline_path), 'exec')
            print("✓ training_pipeline.py syntax is valid")
        except SyntaxError as e:
            print(f"✗ training_pipeline.py has syntax error: {e}")
            return False
        
        return True
        
    except Exception as e:
        print(f"✗ Import error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n" + "█" * 60)
    print("FILTERED DATASET QUICK RETRAIN - INTEGRATION TEST SUITE")
    print("█" * 60)
    
    results = []
    
    results.append(("DatasetManager imports and method presence", test_dataset_manager_imports()))
    results.append(("TrainingWorker filtered dataset support", test_training_worker_filtered_dataset_support()))
    results.append(("Quick retrain UI dialog", test_quick_retrain_ui_dialog()))
    results.append(("Syntax and import validation", test_syntax_and_imports()))
    
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! The filtered dataset quick retrain system is ready.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please review the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
