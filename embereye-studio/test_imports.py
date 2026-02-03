"""Quick test of studio components"""
from forgelab import (
    TrainingConfig, TrainingProgress, TrainingStatus, 
    DeviceManager, DatasetManager, YOLOTrainingPipeline
)

print('✓ ForgeLab imports successful')

# Test device detection
devices = DeviceManager.get_available_devices()
print(f'✓ Devices detected: GPU={devices["gpu"]}, CPU={devices["cpu"]}, MPS={devices["mps"]}')
print(f'  Recommended device: {devices["recommended"]}')

# Test config creation
config = TrainingConfig(
    project_name='test_fire_v1',
    model_size='n',
    epochs=10,
    batch_size=16
)
print(f'✓ Config created: {config.project_name}')

print('\n✓ All ForgeLab tests passed!')
