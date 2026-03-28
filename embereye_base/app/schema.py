"""
Schema definitions and validators for classes and annotations.

Classes v2 schema:
{
  "type": "classes",
  "version": 2,
  "export_id": "uuid",
  "origin": "device/user",
  "timestamp": "iso",
  "root": "IncidentEnvironment",
  "categories": [
    {"id": "uuid", "name": "FIRE_CATEGORY", "tombstone": false},
    ...
  ],
  "classes": [
    {"id": "uuid", "name": "flame", "category_id": "uuid", "tombstone": false}
  ]
}

Annotations v2 schema (extended):
{
  "type": "annotations",
  "version": 2,
  "export_id": "uuid",
  "origin": "device/user",
  "timestamp": "iso",
  "items": [
    {
      "media_base": "base",
      "labels_order": ["flame", ...],
      "frames": [
        {
          "image": "frame_00001.jpg",
          "labels": [
            {"class": "flame", "bbox": [x,y,w,h], "created_by": "user", "confidence": 1.0, "updated_at": "iso"}
          ]
        }
      ]
    }
  ]
}
"""

from typing import Dict, Any, List


def validate_classes_v2(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if payload.get("type") != "classes":
        errors.append("type must be 'classes'")
    if payload.get("version") != 2:
        errors.append("version must be 2 for v2 schema")
    if not isinstance(payload.get("categories"), list):
        errors.append("categories must be a list")
    if not isinstance(payload.get("classes"), list):
        errors.append("classes must be a list")
    cat_ids = set()
    for c in payload.get("categories", []):
        if not c.get("id") or not c.get("name"):
            errors.append("category requires id and name")
        cat_ids.add(c.get("id"))
    for cl in payload.get("classes", []):
        if not cl.get("id") or not cl.get("name") or not cl.get("category_id"):
            errors.append("class requires id, name, and category_id")
        if cl.get("category_id") not in cat_ids:
            errors.append(f"class category_id not found: {cl.get('category_id')}")
    return errors


def validate_annotations_v2(package: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if package.get("type") != "annotations":
        errors.append("type must be 'annotations'")
    if package.get("version") != 2:
        errors.append("version must be 2 for v2 schema")
    for item in package.get("items", []):
        if not item.get("media_base"):
            errors.append("item.media_base required")
        if not isinstance(item.get("frames"), list):
            errors.append("item.frames must be a list")
        for fr in item.get("frames", []):
            if not fr.get("image"):
                errors.append("frame.image required")
            for lab in fr.get("labels", []):
                if not lab.get("class") or not isinstance(lab.get("bbox"), list) or len(lab.get("bbox")) != 4:
                    errors.append("label requires class and bbox=[x,y,w,h]")
    return errors
