
---

## **Document 4: `training_scheduler.md`**

```markdown
# HELENA Self‑Training System – Scheduler

The scheduler determines when training sessions run. It balances resource usage with system load and operator preferences.

## 1. Scheduling Rules

- **Daily scheduled time** – e.g., every night at 02:00.
- **Weekly deep training** – e.g., every Sunday at 03:00 for 4 hours.
- **Idle‑time training** – automatically starts when system has been idle for a configurable period (e.g., 30 minutes) and no gaming is detected.
- **Manual override** – operator can start a session at any time via CLI or UI.

## 2. Integration with Runtime

The scheduler subscribes to runtime events:
- `on_game_detected` – pauses any ongoing training and prevents new sessions.
- `on_game_ended` – resumes idle‑time detection.

It also queries `runtime.get_system_status()` to obtain current CPU/GPU usage and thermal state, and uses thresholds to decide if it's safe to start a session.

## 3. Scheduler Class Implementation

```python
class TrainingScheduler:
    def __init__(self, trainer, config):
        self.trainer = trainer
        self.daily_time = config.get('daily_time', '02:00')
        self.weekly_day = config.get('weekly_day', 'sunday')
        self.weekly_time = config.get('weekly_time', '03:00')
        self.idle_minutes = config.get('idle_minutes', 30)
        self.max_duration_hours = config.get('max_duration_hours', 2)
        
        self.last_idle_check = time.time()
        self.idle_start = None
        self.running = False
        self.thread = threading.Thread(target=self._run, daemon=True)
    
    def start(self):
        self.running = True
        self.thread.start()
    
    def stop(self):
        self.running = False
    
    def _run(self):
        while self.running:
            try:
                now = datetime.now()
                # Check daily schedule
                if self._is_daily_time(now):
                    self._start_session_if_allowed('daily')
                
                # Check weekly schedule
                if self._is_weekly_time(now):
                    self._start_session_if_allowed('weekly', focus_areas=['deep'])
                
                # Check idle detection
                if self._system_idle():
                    if self.idle_start is None:
                        self.idle_start = time.time()
                    elif time.time() - self.idle_start > self.idle_minutes * 60:
                        self._start_session_if_allowed('idle')
                else:
                    self.idle_start = None
                
                time.sleep(60)  # check every minute
            except Exception as e:
                logger.error("TrainingScheduler", f"Scheduler error: {e}")
                time.sleep(300)
    
    def _is_daily_time(self, now):
        target = datetime.strptime(self.daily_time, '%H:%M').time()
        return now.time().hour == target.hour and now.time().minute == target.minute
    
    def _is_weekly_time(self, now):
        if now.strftime('%A').lower() != self.weekly_day.lower():
            return False
        target = datetime.strptime(self.weekly_time, '%H:%M').time()
        return now.time().hour == target.hour and now.time().minute == target.minute
    
    def _system_idle(self):
        # Simplified idle detection – in production, check user input, foreground app, etc.
        cpu = psutil.cpu_percent(interval=0.5)
        return cpu < 10  # arbitrary threshold
    
    def _start_session_if_allowed(self, reason, focus_areas=None):
        if self.trainer.is_training():
            logger.debug("TrainingScheduler", "Already training, skipping scheduled start")
            return
        
        # Check if gaming
        if self.trainer.runtime.gaming_optimizer.active_session:
            logger.debug("TrainingScheduler", "Gaming active, postponing training")
            return
        
        # Check thermal
        usage = self.trainer.runtime.resource_manager.get_system_usage()
        if usage.cpu_temp_c and usage.cpu_temp_c > 80:
            logger.warning("TrainingScheduler", "Temperature too high, skipping training")
            return
        
        self.trainer.start_session(focus_areas=focus_areas, reason=reason)