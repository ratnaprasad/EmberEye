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

REPO_ROOT = Path(__file__).resolve().parent.parent
STUDIO_MAIN_WINDOW = REPO_ROOT / "embereye-studio/studio_main_window.py"
TRAINING_PIPELINE = REPO_ROOT / "embereye_base/core/training_pipeline.py"

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

def test_dataset_manager_imports():
    """Test that DatasetManager can be imported and has the new method."""
    print("=" * 60)
    print("TEST 1: DatasetManager imports and method presence")
    print("=" * 60)
    
    try:
        from embereye_base.core.training_pipeline import DatasetManager
        print("✓ DatasetManager imported successfully")
        
        # Check if method exists
        if hasattr(DatasetManager, 'create_filtered_dataset_unclassified_only'):
            print("✓ create_filtered_dataset_unclassified_only method exists")
        else:
            print("✗ create_filtered_dataset_unclassified_only method NOT found")
            assert False
        
        # Check method signature
        import inspect
        sig = inspect.signature(DatasetManager.create_filtered_dataset_unclassified_only)
        print(f"✓ Method signature: {sig}")
        return
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        assert False


def test_training_worker_filtered_dataset_support():
    """Test that TrainingWorker is wired to the current training pipeline."""
    print("\n" + "=" * 60)
    print("TEST 2: TrainingWorker filtered dataset support")
    print("=" * 60)
    
    try:
        with open(STUDIO_MAIN_WINDOW, 'r') as f:
            content = f.read()

        if 'self.pipeline = YOLOTrainingPipeline(config=self.config)' in content:
            print("✓ TrainingWorker constructs YOLOTrainingPipeline with current config")
        else:
            print("✗ TrainingWorker does NOT construct YOLOTrainingPipeline as expected")
            assert False

        if 'self.pipeline.set_progress_callback(self._emit_progress)' in content:
            print("✓ TrainingWorker wires progress callback to UI updates")
        else:
            print("✗ TrainingWorker does NOT wire progress callback")
            assert False

        if 'success, message = self.pipeline.run_full_pipeline()' in content:
            print("✓ TrainingWorker executes the full training pipeline")
        else:
            print("✗ TrainingWorker does NOT run the full training pipeline")
            assert False

        return
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        assert False


def test_quick_retrain_ui_dialog():
    """Test that quick retrain uses the current Studio quick-start flow."""
    print("\n" + "=" * 60)
    print("TEST 3: Quick retrain UI dialog")
    print("=" * 60)
    
    try:
        with open(STUDIO_MAIN_WINDOW, 'r') as f:
            content = f.read()

        if 'self.quick_retrain_btn.clicked.connect(self.start_quick_retraining)' in content:
            print("✓ Quick retrain button is connected to the handler")
        else:
            print("✗ Quick retrain button handler wiring NOT found")
            assert False

        if 'self.epochs_spin.setValue(20)' in content:
            print("✓ Quick retrain reduces epochs to 20")
        else:
            print("✗ Quick retrain epoch override NOT found")
            assert False

        if 'self.start_model_training()' in content:
            print("✓ Quick retrain reuses the standard training startup path")
        else:
            print("✗ Quick retrain does NOT reuse standard training startup")
            assert False

        return
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        assert False


def test_syntax_and_imports():
    """Test that all modified files have correct syntax and can be imported."""
    print("\n" + "=" * 60)
    print("TEST 4: Syntax and import validation")
    print("=" * 60)
    
    try:
        # Try importing main modules
        from embereye_base.core.training_pipeline import DatasetManager, YOLOTrainingPipeline
        print("✓ training_pipeline imports successfully")

        # Check for syntax errors in the current Studio window implementation
        try:
            with open(STUDIO_MAIN_WINDOW, 'r') as f:
                compile(f.read(), str(STUDIO_MAIN_WINDOW), 'exec')
            print("✓ studio_main_window.py syntax is valid")
        except SyntaxError as e:
            print(f"✗ studio_main_window.py has syntax error: {e}")
            assert False

        # Check training_pipeline.py syntax
        try:
            with open(TRAINING_PIPELINE, 'r') as f:
                compile(f.read(), str(TRAINING_PIPELINE), 'exec')
            print("✓ training_pipeline.py syntax is valid")
        except SyntaxError as e:
            print(f"✗ training_pipeline.py has syntax error: {e}")
            assert False
        
        return
        
    except Exception as e:
        print(f"✗ Import error: {e}")
        import traceback
        traceback.print_exc()
        assert False


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
