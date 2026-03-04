# helena_core/kernel/emotion.py
"""
HELENA Emotion / Affect Engine

Models internal emotional states that colour HELENA's responses and
decision-making.  Emotions are *functional* – they shift priorities,
adjust verbosity, and influence personality tone rather than being
mere cosmetic labels.

Design principles
-----------------
* Emotions decay over time toward a neutral baseline.
* Multiple emotions can be active simultaneously (blended).
* External events (task success, failure, operator praise, security
  threats) push emotion values through the ``register_event`` API.
* The engine exposes a ``get_state`` snapshot consumed by the
  PersonalityEngine to modulate output.
"""
import time
import math
import threading
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Any, Optional


# ── Emotion taxonomy ──────────────────────────────────────────────

class Emotion(Enum):
    """Core emotions that HELENA can experience."""
    CURIOSITY = auto()       # Triggered by novel patterns / new data
    SATISFACTION = auto()    # Triggered by task success
    FRUSTRATION = auto()     # Triggered by repeated failures
    CONCERN = auto()         # Triggered by security threats / anomalies
    ENTHUSIASM = auto()      # Triggered by operator engagement / praise
    CALM = auto()            # Baseline state; grows during idle time
    DETERMINATION = auto()   # Triggered by challenging tasks
    EMPATHY = auto()         # Triggered by operator frustration cues


# ── Data structures ───────────────────────────────────────────────

@dataclass
class EmotionState:
    """Current intensity of a single emotion (0.0 – 1.0)."""
    emotion: Emotion
    intensity: float = 0.0
    last_updated: float = field(default_factory=time.time)
    decay_rate: float = 0.02        # intensity lost per second
    min_intensity: float = 0.0
    max_intensity: float = 1.0

    def decay(self, now: Optional[float] = None) -> None:
        """Apply time-based decay toward *min_intensity*."""
        now = now or time.time()
        elapsed = now - self.last_updated
        if elapsed <= 0:
            return
        loss = self.decay_rate * elapsed
        self.intensity = max(self.min_intensity, self.intensity - loss)
        self.last_updated = now

    def boost(self, amount: float, now: Optional[float] = None) -> None:
        """Increase intensity, clamping to [min, max]."""
        now = now or time.time()
        self.decay(now)
        self.intensity = min(self.max_intensity, self.intensity + amount)
        self.last_updated = now


@dataclass
class EmotionEvent:
    """An event that shifts one or more emotions."""
    source: str
    description: str
    effects: Dict[Emotion, float]   # emotion -> delta
    timestamp: float = field(default_factory=time.time)


# ── Engine ────────────────────────────────────────────────────────

class EmotionEngine:
    """
    Maintains HELENA's emotional state and exposes it for the
    personality engine and response formatter.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

        # Initialise one state slot per emotion
        self.states: Dict[Emotion, EmotionState] = {}
        for emo in Emotion:
            baseline = 0.3 if emo == Emotion.CALM else 0.0
            self.states[emo] = EmotionState(
                emotion=emo,
                intensity=baseline,
                decay_rate=self._default_decay(emo),
            )

        # History of events (ring buffer)
        self._history: List[EmotionEvent] = []
        self._max_history = 500

        # Mood: a slow-moving weighted average of recent emotions
        self._mood_weights: Dict[Emotion, float] = {
            Emotion.SATISFACTION: 0.25,
            Emotion.ENTHUSIASM: 0.20,
            Emotion.CALM: 0.15,
            Emotion.CURIOSITY: 0.15,
            Emotion.FRUSTRATION: -0.20,
            Emotion.CONCERN: -0.10,
            Emotion.DETERMINATION: 0.10,
            Emotion.EMPATHY: 0.10,
        }

    # ── Event registration ────────────────────────────────────────

    def register_event(self, event: EmotionEvent) -> None:
        """Push an external event into the engine."""
        with self._lock:
            now = event.timestamp
            for emotion, delta in event.effects.items():
                state = self.states.get(emotion)
                if state is None:
                    continue
                if delta >= 0:
                    state.boost(delta, now)
                else:
                    state.decay(now)
                    state.intensity = max(0.0, state.intensity + delta)
                    state.last_updated = now

            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

    # ── Convenience event constructors ────────────────────────────

    def on_task_success(self, task_command: str) -> None:
        self.register_event(EmotionEvent(
            source="kernel",
            description=f"Task succeeded: {task_command}",
            effects={
                Emotion.SATISFACTION: 0.15,
                Emotion.CALM: 0.05,
                Emotion.FRUSTRATION: -0.10,
            },
        ))

    def on_task_failure(self, task_command: str, error: str) -> None:
        self.register_event(EmotionEvent(
            source="kernel",
            description=f"Task failed: {task_command} – {error}",
            effects={
                Emotion.FRUSTRATION: 0.15,
                Emotion.DETERMINATION: 0.10,
                Emotion.SATISFACTION: -0.05,
            },
        ))

    def on_security_threat(self, description: str) -> None:
        self.register_event(EmotionEvent(
            source="security",
            description=description,
            effects={
                Emotion.CONCERN: 0.30,
                Emotion.CALM: -0.20,
                Emotion.DETERMINATION: 0.15,
            },
        ))

    def on_operator_interaction(self, sentiment: float = 0.0) -> None:
        """*sentiment* ranges from -1 (negative) to +1 (positive)."""
        effects: Dict[Emotion, float] = {Emotion.CURIOSITY: 0.05}
        if sentiment > 0.3:
            effects[Emotion.ENTHUSIASM] = 0.15 * sentiment
            effects[Emotion.EMPATHY] = 0.05
        elif sentiment < -0.3:
            effects[Emotion.EMPATHY] = 0.15
            effects[Emotion.CONCERN] = 0.05
        self.register_event(EmotionEvent(
            source="operator",
            description="Operator interaction",
            effects=effects,
        ))

    def on_novel_pattern(self, description: str = "") -> None:
        self.register_event(EmotionEvent(
            source="learning",
            description=f"Novel pattern: {description}",
            effects={
                Emotion.CURIOSITY: 0.20,
                Emotion.ENTHUSIASM: 0.10,
            },
        ))

    def on_idle(self) -> None:
        self.register_event(EmotionEvent(
            source="system",
            description="Idle period",
            effects={
                Emotion.CALM: 0.10,
                Emotion.FRUSTRATION: -0.05,
                Emotion.CONCERN: -0.03,
            },
        ))

    # ── State queries ─────────────────────────────────────────────

    def get_state(self) -> Dict[str, Any]:
        """Return a snapshot suitable for the personality engine."""
        with self._lock:
            now = time.time()
            snapshot: Dict[str, float] = {}
            for emo, state in self.states.items():
                state.decay(now)
                snapshot[emo.name.lower()] = round(state.intensity, 3)

            dominant = max(snapshot, key=snapshot.get)  # type: ignore[arg-type]
            mood_score = sum(
                self._mood_weights.get(emo, 0.0) * state.intensity
                for emo, state in self.states.items()
            )
            return {
                "emotions": snapshot,
                "dominant": dominant,
                "mood": round(mood_score, 3),
                "timestamp": now,
            }

    def get_dominant_emotion(self) -> Emotion:
        """Return the highest-intensity emotion right now."""
        with self._lock:
            now = time.time()
            best = Emotion.CALM
            best_val = -1.0
            for emo, state in self.states.items():
                state.decay(now)
                if state.intensity > best_val:
                    best = emo
                    best_val = state.intensity
            return best

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent emotion events for diagnostics."""
        with self._lock:
            return [
                {
                    "source": e.source,
                    "description": e.description,
                    "effects": {k.name: v for k, v in e.effects.items()},
                    "timestamp": e.timestamp,
                }
                for e in self._history[-limit:]
            ]

    # ── Internal helpers ──────────────────────────────────────────

    @staticmethod
    def _default_decay(emotion: Emotion) -> float:
        """Per-emotion default decay rate (intensity / second)."""
        slow = {Emotion.CALM, Emotion.DETERMINATION, Emotion.EMPATHY}
        fast = {Emotion.FRUSTRATION, Emotion.CONCERN}
        if emotion in slow:
            return 0.005
        if emotion in fast:
            return 0.03
        return 0.015
