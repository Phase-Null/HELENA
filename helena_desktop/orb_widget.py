"""
HELENA Orb Widget
 
Animated orb that visualizes HELENA's speech patterns.
- Idle: slow pulsing rings, low bars
- Speaking: bars animate driven by text content, rings pulse faster
- When real audio is implemented: replace text-driven animation with audio FFT data
"""
import math
import random
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QPainterPath, QFont
 
 
class OrbWidget(QWidget):
    """
    Animated orb visualizer.
 
    Text-driven animation works as follows:
    - Each character in the response text maps to a bar height
    - A QTimer steps through the characters at ~80ms intervals
    - Bar heights decay back to idle levels when not speaking
    """
 
    ORB_GOLD = QColor(201, 168, 76)
    ORB_GOLD_DIM = QColor(201, 168, 76, 40)
    ORB_GOLD_MID = QColor(201, 168, 76, 100)
    ORB_DARK = QColor(10, 10, 10)
    ORB_BG = QColor(8, 8, 8)
 
    BAR_COUNT = 14
    BAR_WIDTH = 3
    BAR_GAP = 3
    BAR_MAX_HEIGHT = 28
    BAR_MIN_HEIGHT = 3
 
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 220)
        self.setMaximumSize(260, 260)
 
        # Bar heights — current and target
        self._bar_heights = [self.BAR_MIN_HEIGHT] * self.BAR_COUNT
        self._bar_targets = [self.BAR_MIN_HEIGHT] * self.BAR_COUNT
 
        # Text animation state
        self._text_buffer = []       # chars queued for animation
        self._text_pos = 0
        self._speaking = False
 
        # Ring pulse state
        self._pulse_phase = 0.0
        self._pulse_speed = 0.03     # idle speed
 
        # Animation timer — 50ms = 20fps
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(50)
 
    # ── Public API ────────────────────────────────────────────────
 
    def speak(self, text: str) -> None:
        """Feed text to animate. Call this when HELENA sends a response."""
        self._text_buffer = list(text)
        self._text_pos = 0
        self._speaking = True
        self._pulse_speed = 0.08
 
    def stop_speaking(self) -> None:
        """Return to idle state."""
        self._speaking = False
        self._text_buffer = []
        self._pulse_speed = 0.03
 
    # ── Animation tick ────────────────────────────────────────────
 
    def _tick(self) -> None:
        """Called every 50ms. Advance animation state."""
        # Advance pulse
        self._pulse_phase += self._pulse_speed
        if self._pulse_phase > math.pi * 2:
            self._pulse_phase -= math.pi * 2
 
        # Advance text-driven bar animation
        if self._speaking and self._text_buffer:
            # Process 2 chars per tick for smooth but readable animation
            for _ in range(2):
                if self._text_pos < len(self._text_buffer):
                    char = self._text_buffer[self._text_pos]
                    self._text_pos += 1
                    self._drive_bars_from_char(char)
                else:
                    self._speaking = False
                    self._pulse_speed = 0.03
                    break
 
        # Decay bars toward targets
        for i in range(self.BAR_COUNT):
            diff = self._bar_targets[i] - self._bar_heights[i]
            self._bar_heights[i] += diff * 0.25
 
        # In idle mode, gently randomize targets
        if not self._speaking:
            if random.random() < 0.08:
                idx = random.randint(0, self.BAR_COUNT - 1)
                self._bar_targets[idx] = random.uniform(
                    self.BAR_MIN_HEIGHT, self.BAR_MIN_HEIGHT + 6
                )
            # Decay all targets toward min
            for i in range(self.BAR_COUNT):
                self._bar_targets[i] = max(
                    self.BAR_MIN_HEIGHT,
                    self._bar_targets[i] * 0.92
                )
 
        self.update()
 
    def _drive_bars_from_char(self, char: str) -> None:
        """Map a character to bar movement."""
        if char == ' ':
            # Space: all bars drop
            for i in range(self.BAR_COUNT):
                self._bar_targets[i] = self.BAR_MIN_HEIGHT
            return
 
        if char in '.,!?;:':
            # Punctuation: brief spike then drop
            mid = self.BAR_COUNT // 2
            for i in range(self.BAR_COUNT):
                dist = abs(i - mid)
                self._bar_targets[i] = max(
                    self.BAR_MIN_HEIGHT,
                    self.BAR_MAX_HEIGHT * 0.7 - dist * 3
                )
            return
 
        # Regular character: map ASCII value to bar heights
        # Create a wave pattern centered around a position based on char value
        val = ord(char.lower()) if char.isalpha() else ord(char)
        center = (val % self.BAR_COUNT)
        height = self.BAR_MIN_HEIGHT + (val % 22)
 
        for i in range(self.BAR_COUNT):
            dist = min(abs(i - center), self.BAR_COUNT - abs(i - center))
            h = max(self.BAR_MIN_HEIGHT, height - dist * 3)
            # Only raise bars, don't lower them mid-speech
            if h > self._bar_targets[i]:
                self._bar_targets[i] = h
 
    # ── Paint ─────────────────────────────────────────────────────
 
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
 
        w = self.width()
        h = self.height()
        cx = w / 2
        cy = h / 2 - 15  # Orb center, leave room for bars below
 
        # Background
        painter.fillRect(self.rect(), self.ORB_BG)
 
        # Draw rings
        self._draw_rings(painter, cx, cy)
 
        # Draw core
        self._draw_core(painter, cx, cy)
 
        # Draw bars below orb
        self._draw_bars(painter, cx, cy)
 
        painter.end()
 
    def _draw_rings(self, painter: QPainter, cx: float, cy: float) -> None:
        """Draw three pulsing concentric rings."""
        base_pulse = math.sin(self._pulse_phase)
        fast_pulse = math.sin(self._pulse_phase * 2)
 
        ring_sizes = [72, 54, 38]
        ring_offsets = [0, 0.8, 1.6]
        ring_alphas = [25, 45, 70]
 
        for i, (size, offset, alpha) in enumerate(zip(ring_sizes, ring_offsets, ring_alphas)):
            pulse = math.sin(self._pulse_phase + offset)
            scale = 1.0 + pulse * 0.04
            r = (size / 2) * scale
 
            opacity = alpha + int(pulse * 20)
            color = QColor(201, 168, 76, max(0, min(255, opacity)))
            pen = QPen(color, 1)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(cx, cy), r, r)
 
    def _draw_core(self, painter: QPainter, cx: float, cy: float) -> None:
        """Draw the central orb core."""
        r = 26
 
        # Core fill
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(10, 10, 10)))
        painter.drawEllipse(QPointF(cx, cy), r, r)
 
        # Core border
        pen = QPen(QColor(201, 168, 76, 120), 1)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), r, r)
 
        # H glyph
        font = QFont("Courier New", 11, QFont.Normal)
        painter.setFont(font)
        painter.setPen(QPen(QColor(201, 168, 76, 180)))
        painter.drawText(
            QRectF(cx - r, cy - r, r * 2, r * 2),
            Qt.AlignCenter,
            "H"
        )
 
    def _draw_bars(self, painter: QPainter, cx: float, cy: float) -> None:
        """Draw the waveform bars below the orb."""
        total_width = self.BAR_COUNT * self.BAR_WIDTH + (self.BAR_COUNT - 1) * self.BAR_GAP
        start_x = cx - total_width / 2
        bar_y_base = cy + 42  # Below the orb
 
        for i, height in enumerate(self._bar_heights):
            x = start_x + i * (self.BAR_WIDTH + self.BAR_GAP)
            h = max(self.BAR_MIN_HEIGHT, height)
 
            # Color based on height
            ratio = (h - self.BAR_MIN_HEIGHT) / (self.BAR_MAX_HEIGHT - self.BAR_MIN_HEIGHT)
            alpha = int(60 + ratio * 140)
            color = QColor(201, 168, 76, alpha)
 
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(color))
 
            rect = QRectF(x, bar_y_base - h / 2, self.BAR_WIDTH, h)
            painter.drawRoundedRect(rect, 1, 1)
