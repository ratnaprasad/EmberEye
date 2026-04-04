# External Dataset Class Mapping Flow - Visual Diagram

## Current (BROKEN) Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    EXTERNAL DATASET IMPORT PIPELINE                         │
└─────────────────────────────────────────────────────────────────────────────┘

    EXTERNAL DATASET                    MASTER_CLASSES.JSON (DAY 1)
    ◄─────────────────►                 ◄──────────────────────────►
    
    Input files:                        Current order:
    ├─ helmet (class name)              ├─ [0] CLASS A
    ├─ person (class name)              ├─ [1] CLASS B  
    ├─ vest (class name)                ├─ [2] CLASS C
    └─ images...                        └─ [3] CLASS D


                            │
                            │ "Map external names to master classes"
                            ▼
    
    CLASS MAPPING CREATED:
    helmet  ───────► CLASS A  (idx 0)
    vest    ───────► CLASS C  (idx 2)
    person  ───────► CLASS D  (idx 3)
    

                            │
                            │ "Write annotations with class IDs"
                            ▼
    
    ANNOTATION FILES (.txt):            METADATA.json:
    ◄──────────────────────────────►     ◄──────────────────────┐
    0 0.5 0.5 0.2 0.2     (CLASS A)      {
    2 0.6 0.4 0.1 0.2     (CLASS C)        "class_mapping": {
    3 0.3 0.2 0.3 0.3     (CLASS D)          "helmet": "CLASS A",
                                             "vest": "CLASS C",
                                             "person": "CLASS D"
                                           }
    ❌ NO _id_map.json                   ❌ NO REVERSE MAPPING
    ❌ NO ID → NAME MAPPING              }



┌─────────────────────────────────────────────────────────────────────────────┐
│                         QC REVIEW (DAY 2 - BROKEN)                          │
└─────────────────────────────────────────────────────────────────────────────┘

    Annotation file:                    MASTER_CLASSES.JSON (DAY 2)
    0 0.5 0.5 0.2 0.2                  Someone reordered classes:
    2 0.6 0.4 0.1 0.2                  ├─ [0] CLASS B  ◄── CHANGED!
    3 0.3 0.2 0.3 0.3                  ├─ [1] CLASS A  ◄── CHANGED!
                                        ├─ [2] CLASS C
                                        └─ [3] CLASS D

                            │
                            │ "Read class ID from annotation"
                            ▼
    
    Read class_id = 0       Lookup: flat_classes[0]  ──► CLASS B  ❌ WRONG!
    Read class_id = 2       Lookup: flat_classes[2]  ──► CLASS C  ✓ correct  
    Read class_id = 3       Lookup: flat_classes[3]  ──► CLASS D  ✓ correct
    
    
    DISPLAY IN QC REVIEW:
    ├─ Annotation 1: "CLASS B" (should be CLASS A) ❌ CLASS SWAPPED
    ├─ Annotation 2: "CLASS C" (correct, wasn't reordered)
    └─ Annotation 3: "CLASS D" (correct, wasn't reordered)



┌─────────────────────────────────────────────────────────────────────────────┐
│                      FIXED FLOW WITH _id_map.json                           │
└─────────────────────────────────────────────────────────────────────────────┘

    [At Import Time - Same as before]    [New: Generate _id_map.json]
    
    class_to_id = {                     _id_map = {
      "CLASS A": 0,           ────────►   "0": "CLASS A",
      "CLASS B": 1,           ────────►   "1": "CLASS B",
      "CLASS C": 2,           ────────►   "2": "CLASS C",
      "CLASS D": 3                        "3": "CLASS D"
    }                                   }


    ANNOTATION FILES (.txt):            METADATA.json:
    0 0.5 0.5 0.2 0.2                  {
    2 0.6 0.4 0.1 0.2                    "class_mapping": {...},
    3 0.3 0.2 0.3 0.3                    "_id_map": {          ✓ NEW!
                                           "0": "CLASS A",
                                           "1": "CLASS B",
                                           "2": "CLASS C",
                                           "3": "CLASS D"
                                         }
                                       }
    ALSO WRITE:                         
    _id_map.json         ✓ NEW!           Same as in metadata


┌─────────────────────────────────────────────────────────────────────────────┐
│                        QC REVIEW (DAY 2 - FIXED)                            │
└─────────────────────────────────────────────────────────────────────────────┘

    Annotation file:                    Load metadata.json:
    0 0.5 0.5 0.2 0.2                  {
    2 0.6 0.4 0.1 0.2                    "_id_map": {
    3 0.3 0.2 0.3 0.3                      "0": "CLASS A",
                                           "2": "CLASS C",
                                           "3": "CLASS D"
                                         }
                                       }

                            │
                            │ "Look up class_id in _id_map"
                            ▼
    
    Read class_id = 0       Lookup: _id_map["0"]  ──► CLASS A  ✓ CORRECT!
    Read class_id = 2       Lookup: _id_map["2"]  ──► CLASS C  ✓ CORRECT!
    Read class_id = 3       Lookup: _id_map["3"]  ──► CLASS D  ✓ CORRECT!
    
    ✓ Classes remain correct even if master_classes.json was reordered!
```

---

## Data Structure Comparison

### ❌ BEFORE (Broken)
```
Stored:
  - class_mapping (forward only)
  - No ID → name mapping
  - QC reads from current master_classes.json order

Problem:
  Annotation says: class_id = 0
  QC looks up:    flat_classes[0] = ???
  
  If order changed:
    Was: flat_classes[0] = "CLASS A"
    Now: flat_classes[0] = "CLASS B"
    Result: Wrong class displayed
```

### ✓ AFTER (Fixed)
```
Stored:
  - class_mapping (forward)
  - _id_map (reverse: ID → name)
  - Both in metadata.json and as separate file

Solution:
  Annotation says: class_id = 0
  QC looks up:    _id_map["0"] = "CLASS A"
  
  Regardless of master_classes.json order:
    - Still find "CLASS A" because it's stored in _id_map
    - master_classes.json order doesn't matter
    - Result: ALWAYS correct
```

---

## Timeline: How This Breaks

```
Timeline                Action                          State
─────────────────────────────────────────────────────────────────────

Day 1, 10:00 AM
                Import external dataset           
                master_classes order:             ✓ Works
                [A, B, C, D]                      (A is [0])
                
                Writes annotations with           
                class_id = 0 for "helmet"         ✓ Correct
                
                Stores metadata with              ✓ Good
                class_mapping (forward only)      ⚠️  Missing _id_map


Day 1, 2:00 PM
                Someone reorders classes:         
                [B, A, C, D]                      ⚠️  Problem created!
                                                  
                But no one notices yet...         


Day 1, 3:00 PM
                User opens QC Review              
                
                QC reads: class_id = 0            
                QC looks up: flat_classes[0]     ❌ BROKEN
                Result: Shows "CLASS B"
                         not "CLASS A"
                
                User thinks:                      
                "Why is my annotation wrong?"     


Day 2, 9:00 AM
                User looks at Annotation          ✓ Works (uses metadata)
                screen again
                
                Sees "CLASS A" correctly          ✓ Correct
                
                Confused: "Why the difference    😕  Inconsistency!
                           between screens?"


Day 2, 1:00 PM
                User trains model with this      ❌ CORRUPTION
                dataset
                
                Silent data corruption causes     ⚠️  Data quality issue
                poor model performance           🔴 Most critical!
```

---

## Key Insight

```
┌─────────────────────────────────────────────────────┐
│  The Problem is TEMPORAL COUPLING                   │
├─────────────────────────────────────────────────────┤
│                                                     │
│  Import creates class_ids based on:                │
│    master_classes.json @ Time A                    │
│                                                     │
│  Display reads class_ids using:                    │
│    master_classes.json @ Time B                    │
│                                                     │
│  If Time A ≠ Time B, or                           │
│  If master_classes.json changed between A and B:  │
│    → Indices don't match anymore                  │
│    → Wrong classes displayed/trained               │
│                                                     │
│  Solution: Store the mapping snapshot              │
│  from Time A and use it at Time B                 │
│  instead of rebuilding from current state          │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## What Needs to Change

```
OLD CODE PATTERN:
───────────────
1. Get class list from master_classes.json (current)
2. Create index mapping: class_name → idx
3. Use idx directly in annotation files

NEW CODE PATTERN:
────────────────
1. Get class list from master_classes.json (at import time)
2. Create index mapping: class_name → idx (at import time)
3. STORE the mapping in _id_map.json
4. Use stored mapping when displaying/training (not current list)
5. ONLY fall back to current list if old mapping missing
```
