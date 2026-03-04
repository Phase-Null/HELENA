
---

## **Document 6: `training_configuration.md`**

```markdown
# HELENA Self‑Training System – Configuration

Training behaviour is controlled via the main HELENA configuration file (`~/.helena/config.yaml`) under the `training` section.

## 1. Example Configuration

```yaml
training:
  enabled: false                       # Master switch
  max_training_hours: 2.0               # Maximum duration of a single session
  scheduled_time: "02:00"                # Daily training time (24h format)
  weekly_deep_training:                  # Optional weekly extended session
    day: "sunday"
    time: "03:00"
    duration_hours: 4.0
  idle_threshold_minutes: 30             # Start training after this idle period
  focus_areas:                           # Default focus areas when none specified
    - code_quality
    - efficiency
    - accuracy
  max_parameter_change: 0.1               # Max fractional change per session (10%)
  require_operator_approval: true         # Must operator approve memory updates?
  data_retention_days: 90                  # How long to keep raw training data
  storage_path: "~/.helena/training_data"  # Where to store datasets
  backup_path: "~/.helena/backups"         # Where to store pre‑integration backups
  security_level: "strict"                  # See security_policies.yaml