# PPE Rule Guide: No Helmet Only When Vehicle Is Present

## Objective

Configure EmberEye Field so that:

- no_helmet is treated as a violation only when a vehicle is present in the same scene
- if no vehicle is present, person with helmet or without helmet does not trigger a violation alarm

## Where To Configure

In EmberEye Field (logged in as super admin):

1. Open Settings
2. Go to Sensor Grid
3. Select Conditional Alarm Rules

## Important Rule Engine Behavior

- Trigger Classes use Trigger Match mode (ANY or ALL)
- Require Classes are always AND-matched
- In PPE mode, PERSON is automatically required for PPE triggers if not already included

This means if your model has multiple vehicle labels (for example vehicle, commercial_vehicle, industrial_vehicle), do not place all of them in one rule unless you want all of them required at the same time.

## Recommended Configuration

Create one rule per vehicle class.

### Rule 1

- Enable: ON
- Name: No Helmet with Vehicle
- Trigger Match: ANY
- Trigger Classes: no_helmet
- Require Classes: vehicle

### Rule 2 (if class exists in active model)

- Enable: ON
- Name: No Helmet with Commercial Vehicle
- Trigger Match: ANY
- Trigger Classes: no_helmet
- Require Classes: commercial_vehicle

### Rule 3 (if class exists in active model)

- Enable: ON
- Name: No Helmet with Industrial Vehicle
- Trigger Match: ANY
- Trigger Classes: no_helmet
- Require Classes: industrial_vehicle

Save the rules.

## Example stream_config.json Snippet

Use this as a reference format under conditional_alarm_rules:

```json
"conditional_alarm_rules": [
  {
    "enabled": true,
    "name": "No Helmet with Vehicle",
    "trigger_match": "any",
    "trigger_classes": ["no_helmet"],
    "require_classes": ["vehicle"]
  },
  {
    "enabled": true,
    "name": "No Helmet with Commercial Vehicle",
    "trigger_match": "any",
    "trigger_classes": ["no_helmet"],
    "require_classes": ["commercial_vehicle"]
  },
  {
    "enabled": true,
    "name": "No Helmet with Industrial Vehicle",
    "trigger_match": "any",
    "trigger_classes": ["no_helmet"],
    "require_classes": ["industrial_vehicle"]
  }
]
```

## Validation Checklist

After saving rules, validate these scenarios:

1. person + no_helmet, no vehicle: no alarm
2. person + vehicle, helmet present: no alarm
3. person + vehicle + no_helmet: alarm triggers

## Troubleshooting

If rule does not trigger as expected:

- Verify active analytics category is ppe
- Verify alarm evaluation mode is vision
- Verify class names exactly match active model class names shown in the rule dialog
- Ensure at least one rule is enabled
- Ensure YOLO confidence meets rule_min_yolo_conf

If the class picker does not show vehicle variants, your active runtime model may not expose those labels. In that case, use only the available class names.
