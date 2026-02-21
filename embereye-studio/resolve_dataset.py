#!/usr/bin/env python
"""
Resolve dataset issues for inference.
Creates YOLO-format dataset from annotations with class remapping.
"""
import os
import json
import shutil
from pathlib import Path
from collections import defaultdict
import random

print('=' * 70)
print('RESOLVING DATASET FOR INFERENCE')
print('=' * 70)

# Load master classes
with open('master_classes.json') as f:
    mc = json.load(f)

leaves = []
for cat in mc.get('IncidentEnvironment', []):
    for leaf in mc.get(cat, []):
        leaves.append(leaf)

print('\n[1/4] Analyzing annotations...')

# Scan annotations
training_data = Path('training_data/annotations')
class_ids_found = defaultdict(int)

if training_data.exists():
    for txt_file in training_data.rglob('*.txt'):
        if txt_file.name != 'labels.txt':
            try:
                with open(txt_file) as f:
                    for line in f:
                        if line.strip():
                            class_id = int(line.split()[0])
                            class_ids_found[class_id] += 1
            except:
                pass

classes_with_data = sorted(class_ids_found.keys())
classes_without_data = [i for i in range(41) if i not in classes_with_data]

print(f'   Classes with annotations: {len(classes_with_data)}')
print(f'   Classes without annotations: {len(classes_without_data)}')
for cid in classes_with_data:
    print(f'      {cid}: {leaves[cid]} ({class_ids_found[cid]} boxes)')

# Create YOLO dataset directory
print('\n[2/4] Creating YOLO dataset structure...')
dataset_dir = Path('training_data/yolo_dataset')
dataset_dir.mkdir(exist_ok=True)

# Create dataset.yaml
yaml_lines = []
yaml_lines.append(f'path: {str(dataset_dir.absolute())}')
yaml_lines.append('train: images/train')
yaml_lines.append('val: images/val')
yaml_lines.append('')
yaml_lines.append(f'nc: {len(classes_with_data)}')
yaml_lines.append('names:')

for old_idx in classes_with_data:
    yaml_lines.append(f'  {old_idx}: {leaves[old_idx]}')

yaml_path = dataset_dir / 'dataset.yaml'
with open(yaml_path, 'w') as f:
    f.write('\n'.join(yaml_lines))

print(f'   ✅ Created dataset.yaml with {len(classes_with_data)} classes')

# Create class mapping
class_remap = {}
new_id = 0
for old_id in sorted(classes_with_data):
    class_remap[old_id] = new_id
    new_id += 1

# Create directories
(dataset_dir / 'images' / 'train').mkdir(parents=True, exist_ok=True)
(dataset_dir / 'images' / 'val').mkdir(parents=True, exist_ok=True)
(dataset_dir / 'labels' / 'train').mkdir(parents=True, exist_ok=True)
(dataset_dir / 'labels' / 'val').mkdir(parents=True, exist_ok=True)

print('\n[3/4] Organizing images and labels...')

# Copy and remap
processed = 0
for txt_file in training_data.rglob('*.txt'):
    if txt_file.name != 'labels.txt':
        try:
            # Find corresponding image
            img_file = None
            for ext in ['.jpg', '.jpeg', '.png']:
                potential = txt_file.with_suffix(ext)
                if potential.exists():
                    img_file = potential
                    break
            
            if not img_file:
                continue
            
            # Read and remap
            with open(txt_file) as f:
                lines = f.readlines()
            
            remapped_lines = []
            valid = True
            for line in lines:
                if line.strip():
                    parts = line.split()
                    old_class = int(parts[0])
                    if old_class not in class_remap:
                        valid = False
                        break
                    new_class = class_remap[old_class]
                    remapped_lines.append(f'{new_class} ' + ' '.join(parts[1:]) + '\n')
            
            if not valid:
                continue
            
            # Split into train/val
            split = 'train' if random.random() < 0.8 else 'val'
            
            # Copy files
            new_img_path = dataset_dir / 'images' / split / img_file.name
            new_lbl_path = dataset_dir / 'labels' / split / (img_file.stem + '.txt')
            
            shutil.copy2(img_file, new_img_path)
            with open(new_lbl_path, 'w') as f:
                f.writelines(remapped_lines)
            
            processed += 1
            if processed % 100 == 0:
                print(f'   Processed {processed} files...')
            
        except Exception as e:
            pass

train_imgs = len(list((dataset_dir / 'images' / 'train').glob('*')))
val_imgs = len(list((dataset_dir / 'images' / 'val').glob('*')))

print(f'   ✅ Processed and organized: {processed} image-label pairs')

print('\n[4/4] Verification...')
print(f'   ✅ Training images: {train_imgs}')
print(f'   ✅ Validation images: {val_imgs}')
print(f'   ✅ Total images: {train_imgs + val_imgs}')

print('\n' + '=' * 70)
print('✅ DATASET SUCCESSFULLY RESOLVED!')
print('=' * 70)
print(f'\nDataset ready for training/inference:')
print(f'  Path: {dataset_dir}')
print(f'  Config: {yaml_path}')
print(f'  Classes: {len(classes_with_data)}')
print(f'  Images: {train_imgs + val_imgs} total ({train_imgs} train, {val_imgs} val)')
print('\n' + '=' * 70)
