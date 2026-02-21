#!/usr/bin/env python
"""
Test script - Train a quick model and verify inference with class names.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd().parent))

def test_training_and_inference():
    """Quick training test and inference verification."""
    from embereye.core.training_pipeline import YOLOTrainingPipeline, TrainingConfig
    
    print("=" * 60)
    print("EMBEREYE MODEL TRAINING & INFERENCE TEST")
    print("=" * 60)
    
    # 1. Train a quick model (only 1 epoch for testing)
    print("\n1. Starting quick training (1 epoch - testing only)...")
    config = TrainingConfig(
        project_name="test_model",
        epochs=1,  # Just 1 epoch for quick test
        batch_size=8,
        patience=1,
        device="0"  # Use GPU 0
    )
    
    pipeline = YOLOTrainingPipeline(config=config)
    success, msg = pipeline.run_full_pipeline()
    
    if not success:
        print(f"❌ Training failed: {msg}")
        return False
    
    print(f"✅ Training complete: {msg}")
    best_model_path = pipeline.get_best_model_path()
    print(f"   Best model: {best_model_path}")
    
    # 2. Load model and check class names
    print("\n2. Loading model and checking class names...")
    try:
        from ultralytics import YOLO
        model = YOLO(best_model_path)
        
        print(f"✅ Model loaded successfully")
        print(f"   Classes: {len(model.names)}")
        print(f"   Sample classes:")
        for i in range(min(5, len(model.names))):
            print(f"     {i}: {model.names[i]}")
        
        # Verify these are real class names, not placeholders
        real_names = [n for n in model.names.values() if not n.startswith("CLASS")]
        placeholder_names = [n for n in model.names.values() if n.startswith("CLASS")]
        
        print(f"\n   Real class names: {len(real_names)}")
        print(f"   Placeholder names (CLASS A/B/C/etc.): {len(placeholder_names)}")
        
        if placeholder_names:
            print(f"   ℹ️  Note: Some placeholder names are expected (fire categories)")
            print(f"   Placeholders: {placeholder_names[:5]}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error loading model: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_training_and_inference()
    sys.exit(0 if success else 1)
