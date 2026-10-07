from __future__ import annotations

import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, replace
import itertools
from typing import Any

from PySide6.QtCore import QPointF, QRectF, QRegularExpression, QSize, QStandardPaths, QTimer, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
    QRegularExpressionValidator,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None
    list_ports = None


THEME = {
    "primary": "#0d9488",
    "primary_dark": "#0f766e",
    "primary_soft": "#ccfbf1",
    "accent": "#f59e0b",
    "bg": "#f1f5f9",
    "card": "#ffffff",
    "border": "#e2e8f0",
    "text": "#0f172a",
    "muted": "#64748b",
}
POINT_COLORS = ("#16a34a", "#ef4444", "#3b82f6", "#a855f7", "#f97316", "#0891b2", "#db2777", "#65a30d", "#7c3aed", "#ca8a04", "#0d9488", "#e11d48")
FONT_FAMILY = "Helvetica Neue" if sys.platform == "darwin" else "Segoe UI"

APP_STYLE = """
* {{ font-size: 13px; }}
QMainWindow, QDialog {{ background: {bg}; }}
QWidget#central {{ background: {bg}; }}
QWidget {{ color: {text}; }}
QMenuBar {{ background: {card}; border-bottom: 1px solid {border}; padding: 2px 6px; }}
QMenuBar::item {{ padding: 5px 10px; border-radius: 6px; background: transparent; }}
QMenuBar::item:selected {{ background: {primary_soft}; }}
QMenu {{ background: {card}; border: 1px solid {border}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {primary_soft}; color: {text}; }}

QFrame#header {{ background: {card}; border: 1px solid {border}; border-radius: 16px; }}
QLabel#appTitle {{ font-size: 20px; font-weight: 700; color: {text}; }}
QLabel#appSubtitle {{ color: {muted}; }}
QLabel#cardTitle {{ font-size: 14px; font-weight: 700; }}
QLabel#hint {{ color: {muted}; font-size: 12px; }}
QLabel#status {{ color: {muted}; }}

QGroupBox {{
    background: {card}; border: 1px solid {border}; border-radius: 14px;
    margin-top: 22px; padding: 18px 14px 14px 14px; font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin; subcontrol-position: top left;
    left: 14px; top: 2px; padding: 0 6px; color: {primary_dark}; font-size: 13px; font-weight: 700;
}}
QFrame#waypoint {{ background: #f8fafc; border: 1px solid {border}; border-radius: 10px; }}
QFrame#waypoint QDoubleSpinBox, QFrame#waypoint QComboBox {{ background: white; }}
QPushButton#iconButton {{ padding: 0; border-radius: 14px; color: {muted}; }}
QPushButton#iconButton:hover {{ background: #fee2e2; border-color: #ef4444; color: #b91c1c; }}
QFrame#card {{ background: {card}; border: 1px solid {border}; border-radius: 14px; }}

QPushButton {{
    background: {card}; border: 1px solid {border}; border-radius: 10px;
    padding: 8px 14px; font-weight: 600;
}}
QPushButton:hover {{ background: {primary_soft}; border-color: {primary}; }}
QPushButton:pressed {{ background: #99f6e4; }}
QPushButton:disabled {{ color: #94a3b8; background: #f8fafc; }}
QPushButton#primary {{ background: {primary}; border: 1px solid {primary}; color: white; }}
QPushButton#primary:hover {{ background: {primary_dark}; border-color: {primary_dark}; }}
QPushButton#primary:disabled {{ background: #99d5cf; border-color: #99d5cf; color: white; }}

QDoubleSpinBox, QComboBox, QLineEdit {{
    background: #f8fafc; border: 1px solid {border}; border-radius: 8px;
    padding: 5px 8px; min-height: 20px; selection-background-color: {primary};
}}
QDoubleSpinBox:focus, QComboBox:focus {{ border: 1px solid {primary}; background: white; }}
QComboBox QAbstractItemView {{
    background: {card}; border: 1px solid {border}; selection-background-color: {primary_soft};
    selection-color: {text}; outline: 0;
}}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px; border: 1px solid #94a3b8; background: white; }}
QCheckBox::indicator:checked {{ background: {primary}; border-color: {primary}; }}

QTextEdit, QTextBrowser {{
    background: {card}; border: none; border-radius: 8px; selection-background-color: {primary_soft};
    selection-color: {text};
}}
QTabWidget::pane {{ border: none; top: 4px; }}
QTabBar::tab {{
    background: transparent; padding: 7px 16px; margin-right: 4px; border-radius: 8px;
    color: {muted}; font-weight: 600;
}}
QTabBar::tab:selected {{ background: {primary_soft}; color: {primary_dark}; }}
QTabBar::tab:hover:!selected {{ background: #f1f5f9; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #cbd5e1; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #94a3b8; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ height: 0; }}
""".format(**THEME)


def asset_path(name: str) -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS")) / "assets" / name
    return Path(__file__).resolve().parent / "assets" / name


MOTOR_LAYOUT = (
    (1, "base", "Standachse"),
    (2, "shoulder", "Arm kippen"),
    (3, "wrist", "Handgelenk"),
    (4, "gripper", "Greifer (Servo)"),
)


GRIPPER_ACTIONS = (
    ("none", "Keine Aktion", ()),
    ("close", "Schließen", ("close",)),
    ("open", "Öffnen", ("open",)),
    ("open_close", "Öffnen, dann Schließen", ("open", "close")),
    ("close_open", "Schließen, dann Öffnen", ("close", "open")),
)
GRIPPER_ACTION_S = 1.0
MAX_WAYPOINTS = 12


def waypoint_name(index: int) -> str:
    return chr(ord("A") + index)


@dataclass
class RobotConfig:
    base_height: float
    link_1: float
    link_2: float
    servo_open_deg: float = 90.0
    servo_closed_deg: float = 30.0

    def gripper_fraction(self, servo_deg: float) -> float:
        """0.0 = Greifer geschlossen, 1.0 = Greifer offen (fuer die Darstellung)."""
        span = self.servo_open_deg - self.servo_closed_deg
        if abs(span) < 1e-6:
            return 1.0
        return clamp((servo_deg - self.servo_closed_deg) / span, 0.0, 1.0)


@dataclass
class TargetPoint:
    x: float
    y: float
    z: float
    action: str = "none"


@dataclass
class JointState:
    base_deg: float
    shoulder_deg: float
    wrist_deg: float
    gripper_deg: float


@dataclass
class Keyframe:
    label: str
    point_index: int
    kind: str  # "move" oder "gripper"
    state: "JointState"


@dataclass
class MotorCommand:
    motor_id: int
    name: str
    label: str
    target_deg: float
    duration_ms: int


class InverseKinematicsError(ValueError):
    pass


class SerialBridgeError(RuntimeError):
    pass


class FirmwareDeployError(RuntimeError):
    pass


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def solve_inverse_kinematics(target: TargetPoint, config: RobotConfig, elbow_up: bool) -> JointState:
    radial_distance = math.hypot(target.x, target.y)
    vertical_offset = target.z - config.base_height
    reach = math.hypot(radial_distance, vertical_offset)
    max_reach = config.link_1 + config.link_2
    min_reach = abs(config.link_1 - config.link_2)

    if reach > max_reach + 1e-6 or reach < min_reach - 1e-6:
        raise InverseKinematicsError(
            f"Punkt ({target.x:.1f}, {target.y:.1f}, {target.z:.1f}) ist mit der aktuellen Armlaenge nicht erreichbar."
        )

    cos_wrist = clamp(
        (radial_distance**2 + vertical_offset**2 - config.link_1**2 - config.link_2**2)
        / (2 * config.link_1 * config.link_2),
        -1.0,
        1.0,
    )
    wrist_angle = math.acos(cos_wrist)
    if elbow_up:
        wrist_angle *= -1

    shoulder_angle = math.atan2(vertical_offset, radial_distance) - math.atan2(
        config.link_2 * math.sin(wrist_angle),
        config.link_1 + config.link_2 * math.cos(wrist_angle),
    )
    base_angle = math.atan2(target.y, target.x)

    return JointState(
        base_deg=math.degrees(base_angle),
        shoulder_deg=math.degrees(shoulder_angle),
        wrist_deg=math.degrees(wrist_angle),
        gripper_deg=config.servo_open_deg,
    )


def forward_kinematics(state: JointState, config: RobotConfig) -> dict[str, tuple[float, float, float]]:
    base_rad = math.radians(state.base_deg)
    shoulder_rad = math.radians(state.shoulder_deg)
    wrist_rad = math.radians(state.wrist_deg)

    shoulder_point = (0.0, 0.0, config.base_height)
    radial_elbow = config.link_1 * math.cos(shoulder_rad)
    elbow_z = config.base_height + config.link_1 * math.sin(shoulder_rad)
    elbow_point = (
        radial_elbow * math.cos(base_rad),
        radial_elbow * math.sin(base_rad),
        elbow_z,
    )

    forearm_angle = shoulder_rad + wrist_rad
    radial_tool = radial_elbow + config.link_2 * math.cos(forearm_angle)
    tool_z = elbow_z + config.link_2 * math.sin(forearm_angle)
    tool_point = (
        radial_tool * math.cos(base_rad),
        radial_tool * math.sin(base_rad),
        tool_z,
    )

    return {
        "base": (0.0, 0.0, 0.0),
        "shoulder": shoulder_point,
        "elbow": elbow_point,
        "tool": tool_point,
    }


def interpolate_state(start: JointState, end: JointState, factor: float) -> JointState:
    return JointState(
        base_deg=start.base_deg + (end.base_deg - start.base_deg) * factor,
        shoulder_deg=start.shoulder_deg + (end.shoulder_deg - start.shoulder_deg) * factor,
        wrist_deg=start.wrist_deg + (end.wrist_deg - start.wrist_deg) * factor,
        gripper_deg=start.gripper_deg + (end.gripper_deg - start.gripper_deg) * factor,
    )


def middle_joint_heights(state: JointState, config: RobotConfig) -> tuple[float, float]:
    points = forward_kinematics(state, config)
    shoulder_z = points["shoulder"][2]
    elbow_z = points["elbow"][2]
    return shoulder_z, elbow_z


def min_middle_joint_heights_on_path(
    start: JointState,
    end: JointState,
    config: RobotConfig,
    samples: int = 90,
) -> tuple[float, float]:
    min_shoulder = float("inf")
    min_elbow = float("inf")
    for sample in range(samples + 1):
        factor = sample / samples
        state = interpolate_state(start, end, factor)
        shoulder_z, elbow_z = middle_joint_heights(state, config)
        min_shoulder = min(min_shoulder, shoulder_z)
        min_elbow = min(min_elbow, elbow_z)
    return min_shoulder, min_elbow


def solve_safe_path(
    targets: list[TargetPoint],
    config: RobotConfig,
    preferred_elbow_up: bool,
    min_middle_joint_z: float = 0.0,
) -> tuple[list[JointState], list[bool], float, float]:
    """Waehlt fuer jeden Punkt eine IK-Loesung, so dass die ganze Bahn sicher ist.

    Rueckgabe: Zustaende, Ellbogen-Flags, minimale Schulter- und Ellbogenhoehe entlang der Bahn.
    """
    options: list[list[tuple[bool, JointState]]] = []
    for index, target in enumerate(targets):
        point_options = []
        for elbow_up in (preferred_elbow_up, not preferred_elbow_up):
            try:
                point_options.append((elbow_up, solve_inverse_kinematics(target, config, elbow_up)))
            except InverseKinematicsError as exc:
                last_error = exc
        if not point_options:
            raise InverseKinematicsError(f"Punkt {waypoint_name(index)}: {last_error}")
        options.append(point_options)

    edge_cache: dict[tuple[int, int, int], tuple[float, float]] = {}

    def edge(index: int, a: int, b: int) -> tuple[float, float]:
        key = (index, a, b)
        if key not in edge_cache:
            edge_cache[key] = min_middle_joint_heights_on_path(options[index][a][1], options[index + 1][b][1], config)
        return edge_cache[key]

    candidates = []
    for combo in itertools.product(*[range(len(point_options)) for point_options in options]):
        min_shoulder = float("inf")
        min_elbow = float("inf")
        for index in range(len(combo) - 1):
            shoulder_z, elbow_z = edge(index, combo[index], combo[index + 1])
            min_shoulder = min(min_shoulder, shoulder_z)
            min_elbow = min(min_elbow, elbow_z)
        if len(combo) == 1:
            min_shoulder, min_elbow = middle_joint_heights(options[0][combo[0]][1], config)
        flags = [options[i][k][0] for i, k in enumerate(combo)]
        cost = sum(1 for flag in flags if flag != preferred_elbow_up)
        candidates.append((cost, flags, [options[i][k][1] for i, k in enumerate(combo)], min_shoulder, min_elbow))

    safe = [c for c in candidates if c[3] >= min_middle_joint_z and c[4] >= min_middle_joint_z]
    if safe:
        _, flags, states, min_shoulder, min_elbow = min(safe, key=lambda item: item[0])
        return states, flags, min_shoulder, min_elbow

    best = max(candidates, key=lambda item: min(item[3], item[4]))
    raise InverseKinematicsError(
        "Keine sichere Bahn gefunden: Mindestens ein mittleres Gelenk unterschreitet den Sicherheitsabstand. "
        f"Beste gefundene Mindesthoehen: Schulter z={best[3]:.2f} cm, Ellbogen z={best[4]:.2f} cm."
    )


def build_keyframes(targets: list[TargetPoint], states: list[JointState], config: RobotConfig) -> list[Keyframe]:
    """Erzeugt die Schrittfolge: Anfahren jedes Punktes plus Greiferaktionen am Punkt."""
    frames: list[Keyframe] = []
    gripper = config.servo_open_deg
    action_labels = {"open": "Öffnen", "close": "Schließen"}
    action_angles = {"open": config.servo_open_deg, "close": config.servo_closed_deg}
    for index, (target, state) in enumerate(zip(targets, states)):
        name = waypoint_name(index)
        frames.append(Keyframe(name, index, "move", replace(state, gripper_deg=gripper)))
        steps = next((steps for key, _, steps in GRIPPER_ACTIONS if key == target.action), ())
        for step in steps:
            gripper = action_angles[step]
            frames.append(Keyframe(f"{name} · {action_labels[step]}", index, "gripper", replace(state, gripper_deg=gripper)))
    return frames


def build_motor_commands(state: JointState, duration_s: float) -> list[MotorCommand]:
    duration_ms = max(0, int(duration_s * 1000))
    values = {
        "base": state.base_deg,
        "shoulder": state.shoulder_deg,
        "wrist": state.wrist_deg,
        "gripper": state.gripper_deg,
    }
    return [
        MotorCommand(motor_id, name, label, values[name], duration_ms)
        for motor_id, name, label in MOTOR_LAYOUT
    ]


def build_serial_payload(profile: str, target: TargetPoint, state: JointState, duration_s: float) -> dict[str, Any]:
    commands = build_motor_commands(state, duration_s)
    return {
        "command": "move",
        "profile": profile,
        "duration_ms": max(0, int(duration_s * 1000)),
        "target_point_cm": {
            "x": round(target.x, 2),
            "y": round(target.y, 2),
            "z": round(target.z, 2),
        },
        "motors": [
            {
                "id": command.motor_id,
                "name": command.name,
                "label": command.label,
                "target_deg": round(command.target_deg, 3),
                "duration_ms": command.duration_ms,
            }
            for command in commands
        ],
    }


MAC_PATTERN = QRegularExpression(r"^\s*([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\s*$")
PEER_TIMEOUT_S = 8.0


def normalize_mac(text: str) -> str | None:
    """Gibt die MAC als 'AA:BB:CC:DD:EE:FF' zurueck, None bei ungueltiger Eingabe."""
    text = text.strip().upper().replace("-", ":")
    parts = text.split(":")
    if len(parts) != 6 or any(len(part) != 2 for part in parts):
        return None
    try:
        for part in parts:
            int(part, 16)
    except ValueError:
        return None
    return text


class RobotProfileStore:
    """Speichert pro Roboter die MAC-Adressen der vier Schueler-ESP32 als JSON-Datei."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.profiles: dict[str, list[str]] = {}
        self.last = ""
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        profiles = data.get("profiles", {}) if isinstance(data, dict) else {}
        for name, macs in profiles.items():
            if isinstance(name, str) and isinstance(macs, list):
                padded = [str(mac) for mac in macs[:len(MOTOR_LAYOUT)]]
                self.profiles[name] = padded + [""] * (len(MOTOR_LAYOUT) - len(padded))
        last = data.get("last", "") if isinstance(data, dict) else ""
        self.last = last if last in self.profiles else ""

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"last": self.last, "profiles": self.profiles}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


class SerialBridge:
    def __init__(self) -> None:
        self.connection: Any | None = None
        self.port_name = ""
        self.baudrate = 115200
        self._rx_buffer = b""

    def available_ports(self) -> list[str]:
        if list_ports is None:
            return []
        return [port.device for port in list_ports.comports()]

    def connect(self, port_name: str, baudrate: int) -> None:
        if serial is None:
            raise SerialBridgeError("pyserial ist nicht installiert.")
        self.disconnect()
        try:
            self.connection = serial.Serial(port=port_name, baudrate=baudrate, timeout=0.35, write_timeout=0.5)
        except Exception as exc:
            raise SerialBridgeError(f"Serielle Verbindung zu {port_name} konnte nicht geoeffnet werden: {exc}") from exc
        self.port_name = port_name
        self.baudrate = baudrate

    def disconnect(self) -> None:
        self._rx_buffer = b""
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def is_connected(self) -> bool:
        return self.connection is not None and bool(getattr(self.connection, "is_open", False))

    def send_payload(self, payload: dict[str, Any]) -> None:
        if not self.is_connected():
            raise SerialBridgeError("Keine serielle Verbindung zur ESP32-Bridge aktiv.")

        line = json.dumps(payload, separators=(",", ":")) + "\n"
        try:
            self.connection.write(line.encode("utf-8"))
            self.connection.flush()
        except Exception as exc:
            raise SerialBridgeError(f"Senden fehlgeschlagen: {exc}") from exc

    def read_lines(self) -> list[str]:
        """Liest alle bereits eingetroffenen, vollstaendigen Zeilen (nicht blockierend)."""
        if not self.is_connected():
            return []
        try:
            waiting = self.connection.in_waiting
            if waiting:
                self._rx_buffer += self.connection.read(waiting)
        except Exception as exc:
            raise SerialBridgeError(f"Lesen der Bridge-Antwort fehlgeschlagen: {exc}") from exc

        *complete, self._rx_buffer = self._rx_buffer.split(b"\n")
        lines = [raw.decode("utf-8", errors="replace").strip() for raw in complete]
        return [line for line in lines if line]


class ArmViewBase(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.config: RobotConfig | None = None
        self.state: JointState | None = None
        self.targets: list[TargetPoint] = []

    def set_scene(
        self,
        config: RobotConfig | None,
        state: JointState | None,
        targets: list[TargetPoint],
    ) -> None:
        self.config = config
        self.state = state
        self.targets = targets
        self.update()


def shade(color: QColor, light: float) -> QColor:
    """Hellt eine Farbe auf (light > 0) oder dunkelt sie ab (light < 0); light liegt in [-1, 1]."""
    if light >= 0:
        return color.lighter(100 + int(60 * light))
    return color.darker(100 + int(-70 * light))


class ThreeDViewWidget(ArmViewBase):
    LINK_1_COLOR = QColor(THEME["primary"])
    LINK_2_COLOR = QColor("#2dd4bf")
    BASE_COLOR = QColor("#475569")
    JOINT_COLOR = QColor(THEME["accent"])
    LIGHT_ANGLE = math.radians(-50)

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(520, 380)
        # Isometrische Ansicht: 45 Grad um z, danach ca. 35.264 Grad um x.
        self.iso_yaw = math.radians(45)
        self.iso_pitch = math.atan(math.sqrt(2) / 2)
        self.yaw = self.iso_yaw
        self.pitch = self.iso_pitch
        self.zoom = 1.0
        self.is_isometric = True
        self._drag_active = False
        self._last_mouse_x = 0.0
        self._last_mouse_y = 0.0
        self._scale = 1.0
        self._center = QPointF(0, 0)

    # --- Kamera ---------------------------------------------------------

    def set_view_mode(self, mode: str) -> None:
        self.is_isometric = mode == "isometric"
        if self.is_isometric:
            self.yaw = self.iso_yaw
            self.pitch = self.iso_pitch
        self.update()

    def reset_camera(self) -> None:
        self.yaw = self.iso_yaw
        self.pitch = self.iso_pitch
        self.zoom = 1.0
        self.update()

    def mousePressEvent(self, event) -> None:
        if self.is_isometric:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_active = True
            self._last_mouse_x = event.position().x()
            self._last_mouse_y = event.position().y()

    def mouseMoveEvent(self, event) -> None:
        if self.is_isometric or not self._drag_active:
            return

        current_x = event.position().x()
        current_y = event.position().y()
        dx = current_x - self._last_mouse_x
        dy = current_y - self._last_mouse_y
        self._last_mouse_x = current_x
        self._last_mouse_y = current_y

        self.yaw += math.radians(dx * 0.6)
        self.pitch += math.radians(dy * 0.45)
        pitch_limit = math.radians(80)
        self.pitch = clamp(self.pitch, -pitch_limit, pitch_limit)
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_active = False

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if delta:
            self.zoom = clamp(self.zoom * (1.0 + delta / 1200.0), 0.5, 3.0)
            self.update()

    # --- Projektion -----------------------------------------------------

    def _project(self, point: tuple[float, float, float]) -> tuple[QPointF, float]:
        x, y, z = point
        x1 = x * math.cos(self.yaw) - y * math.sin(self.yaw)
        y1 = x * math.sin(self.yaw) + y * math.cos(self.yaw)
        y2 = y1 * math.cos(self.pitch) - z * math.sin(self.pitch)
        depth = y1 * math.sin(self.pitch) + z * math.cos(self.pitch)
        return QPointF(self._center.x() + x1 * self._scale, self._center.y() + y2 * self._scale), depth

    def _screen(self, point: tuple[float, float, float]) -> QPointF:
        return self._project(point)[0]

    # --- Zeichnen -------------------------------------------------------

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        card = QPainterPath()
        card.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 14, 14)
        painter.setClipPath(card)
        background = QLinearGradient(0, 0, 0, self.height())
        background.setColorAt(0.0, QColor("#f8fafc"))
        background.setColorAt(1.0, QColor("#e2e8f0"))
        painter.fillRect(self.rect(), QBrush(background))

        if self.config is None or self.state is None:
            painter.setPen(QColor(THEME["muted"]))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Noch keine Berechnung vorhanden")
            return

        config = self.config
        state = self.state
        points = forward_kinematics(state, config)
        width = self.width()
        height = self.height()
        padding = 30
        reach = config.link_1 + config.link_2
        floor_radius = reach + 4
        fit = min(
            (width - 2 * padding) / (2 * floor_radius),
            (height - 2 * padding) / (1.9 * floor_radius),
        )
        self._scale = fit * self.zoom
        self._center = QPointF(width / 2, height * 0.6)

        self._draw_floor(painter, floor_radius)
        self._draw_shadow(painter, points)
        self._draw_targets(painter)
        self._draw_pedestal(painter, config)

        base_angle = math.radians(state.base_deg)
        tool_angle = math.radians(state.shoulder_deg + state.wrist_deg)
        shoulder, elbow, tool = points["shoulder"], points["elbow"], points["tool"]

        items: list[tuple[float, Any]] = []

        def add_link(a, b, r_a, r_b, color, bias=0.0) -> None:
            depth = (self._project(a)[1] + self._project(b)[1]) / 2 + bias
            items.append((depth, lambda a=a, b=b, r_a=r_a, r_b=r_b, color=color: self._draw_link(painter, a, b, r_a, r_b, color)))

        def add_joint(point, radius, color, bias=0.0) -> None:
            items.append((self._project(point)[1] + bias, lambda: self._draw_sphere(painter, point, radius, color)))

        add_link(shoulder, elbow, 2.2, 1.8, self.LINK_1_COLOR)
        add_link(elbow, tool, 1.8, 1.4, self.LINK_2_COLOR)
        add_joint(shoulder, 3.0, self.JOINT_COLOR, 0.5)
        add_joint(elbow, 2.6, self.JOINT_COLOR, 0.5)
        add_joint(tool, 1.9, self.JOINT_COLOR, 0.5)
        items.append(
            (
                self._project(tool)[1] + 0.8,
                lambda: self._draw_gripper(painter, tool, base_angle, tool_angle, 55.0 * config.gripper_fraction(state.gripper_deg)),
            )
        )

        for _, draw in sorted(items, key=lambda item: item[0]):
            draw()

        self._draw_overlay(painter, state)
        painter.setClipping(False)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(THEME["border"]), 1))
        painter.drawPath(card)

    def _draw_floor(self, painter: QPainter, radius: float) -> None:
        def ring(r: float) -> QPolygonF:
            return QPolygonF(
                [self._screen((r * math.cos(t * math.pi / 45), r * math.sin(t * math.pi / 45), 0.0)) for t in range(90)]
            )

        painter.setPen(QPen(QColor("#cbd5e1"), 1.4))
        painter.setBrush(QColor(255, 255, 255, 215))
        painter.drawPolygon(ring(radius))

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#e2e8f0"), 1))
        r = 10.0
        while r < radius - 0.5:
            painter.drawPolygon(ring(r))
            r += 10.0
        painter.drawLine(self._screen((-radius, 0, 0)), self._screen((radius, 0, 0)))
        painter.drawLine(self._screen((0, -radius, 0)), self._screen((0, radius, 0)))

        painter.setFont(QFont(FONT_FAMILY, 9, QFont.Weight.DemiBold))
        for axis_end, color, label in (
            ((16.0, 0.0, 0.0), QColor("#3b82f6"), "x"),
            ((0.0, 16.0, 0.0), QColor("#22c55e"), "y"),
            ((0.0, 0.0, 16.0), QColor("#ef4444"), "z"),
        ):
            start = self._screen((0.0, 0.0, 0.0))
            end = self._screen(axis_end)
            painter.setPen(QPen(color, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(start, end)
            painter.drawText(end + QPointF(4, -4), label)

    def _draw_shadow(self, painter: QPainter, points: dict[str, tuple[float, float, float]]) -> None:
        chain = [self._screen((p[0], p[1], 0.0)) for p in (points["shoulder"], points["elbow"], points["tool"])]
        pen = QPen(QColor(15, 23, 42, 45), max(2.0, 3.2 * self._scale), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolyline(QPolygonF(chain))

    def _draw_targets(self, painter: QPainter) -> None:
        if not self.targets:
            return
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(100, 116, 139, 150), 1.4, Qt.PenStyle.DotLine))
        painter.drawPolyline(QPolygonF([self._screen((t.x, t.y, t.z)) for t in self.targets]))

        for index, target in enumerate(self.targets):
            color = QColor(POINT_COLORS[index % len(POINT_COLORS)])
            marker = self._screen((target.x, target.y, target.z))
            floor = self._screen((target.x, target.y, 0.0))
            painter.setPen(QPen(color, 1.2, Qt.PenStyle.DashLine))
            painter.drawLine(marker, floor)
            painter.setBrush(QColor(color.red(), color.green(), color.blue(), 60))
            painter.setPen(QPen(color, 1.5))
            painter.drawEllipse(floor, 7, 3.5)
            painter.setBrush(color)
            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.drawEllipse(marker, 6, 6)
            painter.setPen(color.darker(120))
            painter.setFont(QFont(FONT_FAMILY, 11, QFont.Weight.Bold))
            painter.drawText(marker + QPointF(10, -8), waypoint_name(index))

    def _draw_pedestal(self, painter: QPainter, config: RobotConfig) -> None:
        top = max(config.base_height, 3.0)
        self._draw_cylinder(painter, 0.0, 1.5, 9.0, self.BASE_COLOR.darker(120))
        self._draw_cylinder(painter, 1.5, top - 2.5, 4.6, self.BASE_COLOR)
        self._draw_cylinder(painter, top - 2.5, top, 6.0, self.BASE_COLOR.lighter(125))

    def _draw_cylinder(self, painter: QPainter, z_low: float, z_high: float, radius: float, color: QColor) -> None:
        if z_high <= z_low:
            return
        steps = 40
        faces = []
        for i in range(steps):
            a0 = 2 * math.pi * i / steps
            a1 = 2 * math.pi * (i + 1) / steps
            quad = [
                (radius * math.cos(a0), radius * math.sin(a0), z_low),
                (radius * math.cos(a1), radius * math.sin(a1), z_low),
                (radius * math.cos(a1), radius * math.sin(a1), z_high),
                (radius * math.cos(a0), radius * math.sin(a0), z_high),
            ]
            mid_angle = (a0 + a1) / 2
            depth = self._project((radius * math.cos(mid_angle), radius * math.sin(mid_angle), (z_low + z_high) / 2))[1]
            light = math.cos(mid_angle - self.LIGHT_ANGLE)
            faces.append((depth, quad, light))

        painter.setPen(Qt.PenStyle.NoPen)
        for _, quad, light in sorted(faces, key=lambda item: item[0]):
            painter.setBrush(shade(color, light * 0.6))
            painter.drawPolygon(QPolygonF([self._screen(p) for p in quad]))

        cap_z = z_high if self.pitch >= 0 else z_low
        cap = QPolygonF(
            [
                self._screen((radius * math.cos(2 * math.pi * i / steps), radius * math.sin(2 * math.pi * i / steps), cap_z))
                for i in range(steps)
            ]
        )
        painter.setBrush(shade(color, 0.25))
        painter.drawPolygon(cap)

    def _draw_link(
        self,
        painter: QPainter,
        a: tuple[float, float, float],
        b: tuple[float, float, float],
        radius_a: float,
        radius_b: float,
        color: QColor,
    ) -> None:
        start = self._screen(a)
        end = self._screen(b)
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.hypot(dx, dy)
        if length < 1e-3:
            return
        nx, ny = -dy / length, dx / length
        wa = radius_a * self._scale
        wb = radius_b * self._scale
        polygon = QPolygonF(
            [
                QPointF(start.x() + nx * wa, start.y() + ny * wa),
                QPointF(end.x() + nx * wb, end.y() + ny * wb),
                QPointF(end.x() - nx * wb, end.y() - ny * wb),
                QPointF(start.x() - nx * wa, start.y() - ny * wa),
            ]
        )
        mid = QPointF((start.x() + end.x()) / 2, (start.y() + end.y()) / 2)
        wm = (wa + wb) / 2
        gradient = QLinearGradient(QPointF(mid.x() + nx * wm, mid.y() + ny * wm), QPointF(mid.x() - nx * wm, mid.y() - ny * wm))
        gradient.setColorAt(0.0, shade(color, -0.45))
        gradient.setColorAt(0.35, shade(color, 0.35))
        gradient.setColorAt(1.0, shade(color, -0.35))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawPolygon(polygon)
        # runde Enden
        for center, width_px in ((start, wa), (end, wb)):
            painter.setBrush(shade(color, -0.1))
            painter.drawEllipse(center, width_px, width_px)

    def _draw_sphere(self, painter: QPainter, point: tuple[float, float, float], radius: float, color: QColor) -> None:
        center = self._screen(point)
        r = radius * self._scale
        gradient = QRadialGradient(center, r, QPointF(center.x() - r * 0.35, center.y() - r * 0.4))
        gradient.setColorAt(0.0, shade(color, 0.7))
        gradient.setColorAt(0.6, color)
        gradient.setColorAt(1.0, shade(color, -0.55))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(center, r, r)

    def _draw_gripper(
        self,
        painter: QPainter,
        tool_point: tuple[float, float, float],
        base_angle: float,
        elevation_angle: float,
        opening_deg: float,
    ) -> None:
        reach = (
            math.cos(elevation_angle) * math.cos(base_angle),
            math.cos(elevation_angle) * math.sin(base_angle),
            math.sin(elevation_angle),
        )
        left = (-math.sin(base_angle), math.cos(base_angle), 0.0)
        palm_length = 2.4
        jaw_length = 4.8
        half_opening = math.radians(opening_deg / 2)

        palm_end = tuple(tool_point[i] + reach[i] * palm_length for i in range(3))
        self._draw_link(painter, tool_point, palm_end, 1.8, 1.8, QColor("#334155"))

        jaws = []
        for direction in (-1.0, 1.0):
            tip = tuple(
                palm_end[i]
                + reach[i] * math.cos(half_opening) * jaw_length
                + left[i] * math.sin(half_opening) * jaw_length * direction
                for i in range(3)
            )
            jaws.append((self._project(tip)[1], tip))
        for _, tip in sorted(jaws, key=lambda item: item[0]):
            self._draw_link(painter, palm_end, tip, 0.8, 0.5, self.JOINT_COLOR)

    def _draw_overlay(self, painter: QPainter, state: JointState) -> None:
        title = "3D-Ansicht · isometrisch" if self.is_isometric else "3D-Ansicht · frei (Maus ziehen, Mausrad = Zoom)"
        painter.setFont(QFont(FONT_FAMILY, 10, QFont.Weight.DemiBold))
        painter.setPen(QColor(THEME["muted"]))
        painter.drawText(16, 14, self.width() - 32, 20, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title)

        chips = (
            ("M1", state.base_deg),
            ("M2", state.shoulder_deg),
            ("M3", state.wrist_deg),
            ("Servo", state.gripper_deg),
        )
        painter.setFont(QFont(FONT_FAMILY, 10, QFont.Weight.DemiBold))
        metrics = painter.fontMetrics()
        x = 16.0
        y = self.height() - 40.0
        for name, value in chips:
            text = f"{name}  {value:7.1f}°"
            chip_width = metrics.horizontalAdvance(text) + 22
            rect = QRectF(x, y, chip_width, 26)
            painter.setPen(QPen(QColor(THEME["border"]), 1))
            painter.setBrush(QColor(255, 255, 255, 230))
            painter.drawRoundedRect(rect, 13, 13)
            painter.setPen(QColor(THEME["text"]))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
            x += chip_width + 8


class VisualizerPanel(QFrame):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.three_d_view = ThreeDViewWidget()
        layout.addWidget(self.three_d_view)

    def set_scene(
        self,
        config: RobotConfig | None,
        state: JointState | None,
        targets: list[TargetPoint],
    ) -> None:
        self.three_d_view.set_scene(config, state, targets)

    def set_3d_mode(self, mode: str) -> None:
        self.three_d_view.set_view_mode(mode)

    def reset_3d_camera(self) -> None:
        self.three_d_view.reset_camera()


class WaypointRow(QFrame):
    def __init__(self, index: int, x: float, y: float, z: float, action: str, removable: bool) -> None:
        super().__init__()
        self.setObjectName("waypoint")
        self.setMinimumHeight(92)
        layout = QGridLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(6)

        self.badge = QLabel()
        self.badge.setFixedSize(28, 28)
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.badge, 0, 0)

        self.x = self._spinbox("x ", x)
        self.y = self._spinbox("y ", y)
        self.z = self._spinbox("z ", z)
        for column, spinbox in enumerate((self.x, self.y, self.z), start=1):
            layout.addWidget(spinbox, 0, column)

        self.remove_button = QPushButton("✕")
        self.remove_button.setObjectName("iconButton")
        self.remove_button.setFixedSize(28, 28)
        self.remove_button.setToolTip("Punkt entfernen")
        self.remove_button.setVisible(removable)
        layout.addWidget(self.remove_button, 0, 4)

        self.gripper_label = QLabel("Greifer")
        self.gripper_label.setObjectName("hint")
        layout.addWidget(self.gripper_label, 1, 0, 1, 1, Qt.AlignmentFlag.AlignCenter)
        self.action = QComboBox()
        layout.addWidget(self.action, 1, 1, 1, 4)
        self.set_index(index, action)

    def _spinbox(self, prefix: str, value: float) -> QDoubleSpinBox:
        spinbox = QDoubleSpinBox()
        spinbox.setRange(-200, 200)
        spinbox.setDecimals(1)
        spinbox.setSingleStep(1.0)
        spinbox.setPrefix(prefix)
        spinbox.setValue(value)
        spinbox.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        return spinbox

    def set_index(self, index: int, action: str | None = None) -> None:
        """Beschriftet die Zeile neu; Punkt A startet mit geoeffnetem Greifer."""
        if action is None:
            action = self.action.currentData()
        color = POINT_COLORS[index % len(POINT_COLORS)]
        self.badge.setText(waypoint_name(index))
        self.badge.setStyleSheet(
            f"background: {color}; color: white; border-radius: 14px; font-weight: 700;"
        )
        allowed = ("none", "close") if index == 0 else tuple(key for key, _, _ in GRIPPER_ACTIONS)
        self.action.blockSignals(True)
        self.action.clear()
        for key, label, _ in GRIPPER_ACTIONS:
            if key in allowed:
                self.action.addItem(label, key)
        found = self.action.findData(action)
        self.action.setCurrentIndex(found if found >= 0 else 0)
        self.action.blockSignals(False)
        self.action.setToolTip(
            "Greifer startet geöffnet. Hier kann er geschlossen werden." if index == 0 else "Greiferaktion nach dem Anfahren dieses Punkts"
        )

    def target(self) -> TargetPoint:
        return TargetPoint(self.x.value(), self.y.value(), self.z.value(), str(self.action.currentData()))


class WaypointEditor(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[WaypointRow] = []
        self.rows_layout = QVBoxLayout(self)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(8)

        self.add_button = QPushButton("＋ Punkt hinzufügen")
        self.add_button.clicked.connect(lambda: self.add_waypoint())
        self.rows_layout.addWidget(self.add_button)

        self.add_waypoint(18, 8, 18, "close")
        self.add_waypoint(12, -14, 20, "open")

    def add_waypoint(self, x: float | None = None, y: float | None = None, z: float | None = None, action: str = "none") -> None:
        if len(self.rows) >= MAX_WAYPOINTS:
            return
        if not isinstance(x, (int, float)):
            last = self.rows[-1] if self.rows else None
            x, y, z = (last.x.value(), last.y.value(), last.z.value()) if last else (15.0, 0.0, 15.0)
        index = len(self.rows)
        row = WaypointRow(index, x, y, z, action, removable=index >= 2)
        row.remove_button.clicked.connect(lambda _=False, row=row: self.remove_waypoint(row))
        self.rows.append(row)
        self.rows_layout.insertWidget(index, row)
        self._refresh()

    def remove_waypoint(self, row: WaypointRow) -> None:
        if len(self.rows) <= 2 or row not in self.rows:
            return
        self.rows.remove(row)
        self.rows_layout.removeWidget(row)
        row.deleteLater()
        self._refresh()

    def _refresh(self) -> None:
        for index, row in enumerate(self.rows):
            row.set_index(index)
            row.remove_button.setVisible(index >= 2)
        self.add_button.setEnabled(len(self.rows) < MAX_WAYPOINTS)

    def targets(self) -> list[TargetPoint]:
        return [row.target() for row in self.rows]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Roboterarm Steuerung")
        self.setWindowIcon(QIcon(str(asset_path("logo.png"))))
        self.resize(1400, 900)

        self.targets: list[TargetPoint] = []
        self.states: list[JointState] = []
        self.keyframes: list[Keyframe] = []
        self.elbow_flags: list[bool] = []
        self.current_config: RobotConfig | None = None
        self.min_path_shoulder_z: float | None = None
        self.min_path_elbow_z: float | None = None
        self.serial_bridge = SerialBridge()
        self.animation_states: list[JointState] = []
        self.animation_index = 0
        self.animation_timer = QTimer(self)
        self.animation_timer.setInterval(33)
        self.animation_timer.timeout.connect(self._advance_animation)

        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(16, 14, 16, 16)
        root_layout.setSpacing(14)

        root_layout.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setSpacing(16)
        root_layout.addLayout(body, stretch=1)

        # --- linke Spalte: Eingaben -------------------------------------
        geometry_box = QGroupBox("Geometrie")
        geometry_layout = QGridLayout(geometry_box)
        geometry_layout.setVerticalSpacing(8)
        self.base_height = self._spinbox(0, 200, 12)
        self.link_1 = self._spinbox(1, 200, 20)
        self.link_2 = self._spinbox(1, 200, 18)
        self.duration = self._spinbox(0.5, 20, 3.0, step=0.5)
        self.middle_joint_clearance = self._spinbox(0.0, 50.0, 2.0, step=0.5)
        geometry_labels = (
            ("Sockelhöhe z0 [cm]", self.base_height),
            ("Armlänge 1 [cm]", self.link_1),
            ("Armlänge 2 [cm]", self.link_2),
            ("Animationsdauer [s]", self.duration),
            ("Sicherheitsabstand z [cm]", self.middle_joint_clearance),
        )
        for row, (label, widget) in enumerate(geometry_labels):
            geometry_layout.addWidget(QLabel(label), row, 0)
            geometry_layout.addWidget(widget, row, 1)
        geometry_layout.setColumnStretch(0, 1)

        self.elbow_up = QCheckBox("Alternative IK-Lösung (eingeklappt)")
        geometry_layout.addWidget(self.elbow_up, len(geometry_labels), 0, 1, 2)

        gripper_box = QGroupBox("Greifer (Servo SG90)")
        gripper_layout = QGridLayout(gripper_box)
        gripper_layout.setVerticalSpacing(8)
        self.servo_open = self._spinbox(0, 180, 90, step=5.0)
        self.servo_closed = self._spinbox(0, 180, 30, step=5.0)
        gripper_layout.addWidget(QLabel("Servowinkel offen [°]"), 0, 0)
        gripper_layout.addWidget(self.servo_open, 0, 1)
        gripper_layout.addWidget(QLabel("Servowinkel geschlossen [°]"), 1, 0)
        gripper_layout.addWidget(self.servo_closed, 1, 1)
        gripper_layout.setColumnStretch(0, 1)

        positions_box = QGroupBox("Punkte (Reihenfolge A, B, C, ...)")
        positions_layout = QVBoxLayout(positions_box)
        self.inputs = WaypointEditor()
        positions_layout.addWidget(self.inputs)

        button_box = QWidget()
        button_layout = QVBoxLayout(button_box)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(8)
        self.calculate_button = QPushButton("Winkel berechnen")
        self.calculate_button.setObjectName("primary")
        self.animate_button = QPushButton("Bewegung animieren")
        self.stop_button = QPushButton("Animation stoppen")
        button_layout.addWidget(self.calculate_button)
        secondary_row = QHBoxLayout()
        secondary_row.setSpacing(8)
        secondary_row.addWidget(self.animate_button)
        secondary_row.addWidget(self.stop_button)
        button_layout.addLayout(secondary_row)

        self.port_combo = QComboBox()
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["115200", "230400", "460800"])
        self.baud_combo.setCurrentText("115200")
        self.refresh_ports_button = QPushButton("Ports suchen")
        self.connect_bridge_button = QPushButton("Verbinden")
        self.disconnect_bridge_button = QPushButton("Trennen")
        self.send_step_combo = QComboBox()
        self.send_step_button = QPushButton("Senden")
        self.deploy_firmware_button = QPushButton("Bridge-Firmware auf ESP32 schreiben")
        self.bridge_status = QLabel("Nicht verbunden")
        self.bridge_mac_edit = QLineEdit()
        self.bridge_mac_edit.setReadOnly(True)
        self.bridge_mac_edit.setPlaceholderText("Erscheint nach dem Verbinden der Bridge")
        self.copy_mac_button = QPushButton("Kopieren")
        self.espnow_status = QLabel()
        self.profile_store = RobotProfileStore(self._profile_path())
        self.profile_combo = QComboBox()
        self.profile_combo.setEditable(True)
        self.profile_combo.lineEdit().setPlaceholderText("Name des Roboters")
        self.save_profile_button = QPushButton("Speichern")
        self.delete_profile_button = QPushButton("Löschen")
        self.peer_edits: list[QLineEdit] = []
        self.peer_dots: list[QLabel] = []
        for _ in MOTOR_LAYOUT:
            edit = QLineEdit()
            edit.setPlaceholderText("AA:BB:CC:DD:EE:FF")
            edit.setValidator(QRegularExpressionValidator(QRegularExpression(r"[0-9A-Fa-f:\-]{0,17}"), edit))
            self.peer_edits.append(edit)
            self.peer_dots.append(QLabel("●"))
        self.peer_last_ok: list[float | None] = [None] * len(MOTOR_LAYOUT)
        self.bridge_log = QTextEdit()
        self.bridge_log.setReadOnly(True)
        self.bridge_log.setFont(QFont("Courier New", 11))
        self.bridge_log.setMinimumHeight(180)
        self.clear_log_button = QPushButton("Leeren")
        self.esp_dialog = self._create_esp_dialog()
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(100)
        self.poll_timer.timeout.connect(self._poll_bridge)
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(1000)
        self.status_timer.timeout.connect(self._refresh_espnow_status)
        self.status_timer.start()

        controls_content = QWidget()
        controls_content.setObjectName("central")
        controls_layout = QVBoxLayout(controls_content)
        controls_layout.setContentsMargins(0, 0, 6, 0)
        controls_layout.setSpacing(10)
        controls_layout.addWidget(geometry_box)
        controls_layout.addWidget(gripper_box)
        controls_layout.addWidget(positions_box)
        controls_layout.addWidget(button_box)
        controls_layout.addStretch(1)

        controls = QScrollArea()
        controls.setWidgetResizable(True)
        controls.setFrameShape(QFrame.Shape.NoFrame)
        controls.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        controls.setFixedWidth(500)
        controls.setWidget(controls_content)

        # --- rechte Spalte: 3D-Ansicht + Ergebnis -------------------------
        visuals = QWidget()
        visuals_layout = QVBoxLayout(visuals)
        visuals_layout.setContentsMargins(0, 0, 0, 0)
        visuals_layout.setSpacing(12)

        view_controls = QHBoxLayout()
        view_title = QLabel("3D-Ansicht")
        view_title.setObjectName("cardTitle")
        view_controls.addWidget(view_title)
        view_controls.addStretch(1)
        self.view_mode_combo = QComboBox()
        self.view_mode_combo.addItem("Isometrisch", "isometric")
        self.view_mode_combo.addItem("Frei (Maus)", "free")
        self.reset_view_button = QPushButton("Kamera zurücksetzen")
        view_controls.addWidget(self.view_mode_combo)
        view_controls.addWidget(self.reset_view_button)

        self.visualizer = VisualizerPanel()

        result_box = QGroupBox("Ergebnis")
        result_layout = QVBoxLayout(result_box)
        result_layout.setContentsMargins(10, 14, 10, 10)
        self.result_tabs = QTabWidget()
        self.result_summary = QTextBrowser()
        self.result_summary.setOpenLinks(False)
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setFont(QFont("Courier New", 11))
        self.result_tabs.addTab(self.result_summary, "Winkel")
        self.result_tabs.addTab(self.result_text, "Details und Pakete")
        result_box.setMinimumHeight(290)
        result_layout.addWidget(self.result_tabs)
        self.result_summary.setHtml(self._empty_summary_html())

        visuals_layout.addLayout(view_controls)
        visuals_layout.addWidget(self.visualizer, stretch=3)
        visuals_layout.addWidget(result_box, stretch=2)

        body.addWidget(controls)
        body.addWidget(visuals, stretch=1)

        self._create_menu()

        self.calculate_button.clicked.connect(self.calculate_positions)
        self.animate_button.clicked.connect(self.animate_motion)
        self.stop_button.clicked.connect(self.stop_animation)
        self.refresh_ports_button.clicked.connect(self.refresh_serial_ports)
        self.connect_bridge_button.clicked.connect(self.connect_bridge)
        self.disconnect_bridge_button.clicked.connect(self.disconnect_bridge)
        self.send_step_button.clicked.connect(self.send_selected_step)
        self.deploy_firmware_button.clicked.connect(self.deploy_bridge_firmware)
        self.copy_mac_button.clicked.connect(self.copy_bridge_mac)
        self.save_profile_button.clicked.connect(self.save_profile)
        self.delete_profile_button.clicked.connect(self.delete_profile)
        self.profile_combo.activated.connect(self._load_profile)
        self.clear_log_button.clicked.connect(self.bridge_log.clear)
        for edit in self.peer_edits:
            edit.editingFinished.connect(self._peer_edit_finished)
        self.view_mode_combo.currentIndexChanged.connect(self._change_3d_mode)
        self.reset_view_button.clicked.connect(self.visualizer.reset_3d_camera)

        self.refresh_serial_ports()
        self._reload_profile_combo(select=self.profile_store.last)
        self._update_bridge_controls()
        self.visualizer.set_3d_mode("isometric")
        initial_config = self.get_config()
        initial_state = JointState(0.0, 20.0, 45.0, initial_config.servo_open_deg)
        self.visualizer.set_scene(initial_config, initial_state, [])

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("header")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(14)

        logo = QLabel()
        pixmap = QPixmap(str(asset_path("logo.png")))
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaled(QSize(48, 48), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        layout.addWidget(logo)

        titles = QVBoxLayout()
        titles.setSpacing(0)
        title = QLabel("Roboterarm Steuerung")
        title.setObjectName("appTitle")
        subtitle = QLabel("Winkelberechnung und Ansteuerung per ESP32")
        subtitle.setObjectName("appSubtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        layout.addLayout(titles)
        layout.addStretch(1)

        esp_button = QPushButton("ESP32-Kommunikation")
        esp_button.clicked.connect(self.open_esp_dialog)
        layout.addWidget(esp_button)
        return header

    def _empty_summary_html(self) -> str:
        return (
            f'<p style="color:{THEME["muted"]}; font-size:14px; margin:18px;">'
            "Noch keine Berechnung. Positionen eintragen und auf <b>Winkel berechnen</b> klicken."
            "</p>"
        )

    def _build_summary_html(self) -> str:
        if not self.keyframes or self.current_config is None:
            return self._empty_summary_html()

        config = self.current_config
        th = (
            f'style="background:{THEME["primary_soft"]}; color:{THEME["primary_dark"]}; '
            'padding:6px 10px; font-size:12px;"'
        )
        td = f'style="padding:6px 10px; border-bottom:1px solid {THEME["border"]}; font-size:14px;"'
        html = [
            '<table width="100%" cellspacing="0" cellpadding="0">',
            f'<tr><th align="left" {th}>Schritt</th>'
            f'<th align="right" {th}>M1 Standachse</th>'
            f'<th align="right" {th}>M2 Arm</th>'
            f'<th align="right" {th}>M3 Handgelenk</th>'
            f'<th align="right" {th}>Servo Greifer</th></tr>',
        ]
        for frame in self.keyframes:
            state = frame.state
            is_action = frame.kind == "gripper"
            weight = "font-weight:400;" if is_action else "font-weight:700;"
            row_bg = ' bgcolor="#f8fafc"' if is_action else ""
            fraction = config.gripper_fraction(state.gripper_deg)
            gripper_note = "offen" if fraction > 0.5 else "geschlossen"
            html.append(
                f'<tr{row_bg}><td {td}><span style="{weight}">{frame.label}</span></td>'
                f'<td align="right" {td}>{state.base_deg:.1f}°</td>'
                f'<td align="right" {td}>{state.shoulder_deg:.1f}°</td>'
                f'<td align="right" {td}>{state.wrist_deg:.1f}°</td>'
                f'<td align="right" {td}><b>{state.gripper_deg:.0f}°</b> '
                f'<span style="color:{THEME["muted"]}; font-size:12px;">{gripper_note}</span></td></tr>'
            )
        html.append("</table>")

        shoulder_z = "unbekannt" if self.min_path_shoulder_z is None else f"{self.min_path_shoulder_z:.1f} cm"
        elbow_z = "unbekannt" if self.min_path_elbow_z is None else f"{self.min_path_elbow_z:.1f} cm"
        points = " &nbsp;·&nbsp; ".join(
            f"{waypoint_name(i)}: ({t.x:.1f} | {t.y:.1f} | {t.z:.1f}) {'eingeklappt' if self.elbow_flags[i] else 'ausgeklappt'}"
            for i, t in enumerate(self.targets)
        )
        html.append(
            f'<p style="color:{THEME["muted"]}; font-size:12px;">M1–M3: Schrittmotoren (Winkel in Grad), '
            f'Servo: SG90 (0–180°).<br>{points}<br>'
            f'Mindesthöhe entlang der Bahn: Schulter {shoulder_z}, Ellbogen {elbow_z} '
            f'(Sicherheitsabstand {self.middle_joint_clearance.value():.1f} cm)</p>'
        )
        return "".join(html)

    def _profile_path(self) -> Path:
        base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        return Path(base or Path.home() / ".roboterarm") / "roboter_profile.json"

    def _create_esp_dialog(self) -> QDialog:
        dialog = QDialog(self)
        dialog.setWindowTitle("ESP32-Kommunikation")
        dialog.resize(820, 860)

        dialog_layout = QVBoxLayout(dialog)

        bridge_box = QGroupBox("Bridge-ESP32 (per USB angeschlossen)")
        bridge_layout = QGridLayout(bridge_box)
        bridge_layout.addWidget(QLabel("Serieller Port"), 0, 0)
        bridge_layout.addWidget(self.port_combo, 0, 1)
        bridge_layout.addWidget(self.refresh_ports_button, 0, 2)
        bridge_layout.addWidget(QLabel("Baudrate"), 1, 0)
        bridge_layout.addWidget(self.baud_combo, 1, 1)
        bridge_layout.addWidget(self.connect_bridge_button, 1, 2)
        bridge_layout.addWidget(QLabel("Status"), 2, 0)
        bridge_layout.addWidget(self.bridge_status, 2, 1)
        bridge_layout.addWidget(self.disconnect_bridge_button, 2, 2)
        bridge_layout.addWidget(QLabel("MAC der Bridge"), 3, 0)
        bridge_layout.addWidget(self.bridge_mac_edit, 3, 1)
        bridge_layout.addWidget(self.copy_mac_button, 3, 2)
        bridge_layout.addWidget(self.deploy_firmware_button, 4, 0, 1, 3)

        peers_box = QGroupBox("ESP32 der Schüler (ESP-NOW)")
        peers_layout = QGridLayout(peers_box)
        peers_layout.addWidget(self.espnow_status, 0, 0, 1, 4)
        peers_layout.addWidget(QLabel("Roboter"), 1, 0)
        peers_layout.addWidget(self.profile_combo, 1, 1)
        profile_buttons = QHBoxLayout()
        profile_buttons.addWidget(self.save_profile_button)
        profile_buttons.addWidget(self.delete_profile_button)
        peers_layout.addLayout(profile_buttons, 1, 2, 1, 2)
        for row, (motor_id, _name, label) in enumerate(MOTOR_LAYOUT, start=2):
            peers_layout.addWidget(QLabel(f"Motor {motor_id} · {label}"), row, 0)
            peers_layout.addWidget(self.peer_edits[row - 2], row, 1, 1, 2)
            peers_layout.addWidget(self.peer_dots[row - 2], row, 3)
        peers_layout.setColumnStretch(1, 1)

        data_box = QGroupBox("Übertragene Daten")
        data_layout = QGridLayout(data_box)
        data_layout.addWidget(self.send_step_combo, 0, 0)
        data_layout.addWidget(self.send_step_button, 0, 1)
        data_layout.addWidget(self.clear_log_button, 0, 2)
        data_layout.addWidget(self.bridge_log, 1, 0, 1, 3)
        data_layout.setColumnStretch(0, 1)

        dialog_layout.addWidget(bridge_box)
        dialog_layout.addWidget(peers_box)
        dialog_layout.addWidget(data_box, stretch=1)
        close_button = QPushButton("Schliessen")
        close_button.clicked.connect(dialog.accept)
        dialog_layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignRight)
        return dialog

    def open_esp_dialog(self) -> None:
        self.refresh_serial_ports()
        self._update_bridge_controls()
        self._refresh_espnow_status()
        self.esp_dialog.show()
        self.esp_dialog.raise_()
        self.esp_dialog.activateWindow()

    def _runtime_root(self) -> Path:
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            return Path(getattr(sys, "_MEIPASS"))
        return Path(__file__).resolve().parent

    def _firmware_path(self, filename: str) -> Path:
        return self._runtime_root() / "esp32_bridge" / filename

    def _resolve_mpremote_launcher(self) -> list[str] | None:
        # 1) Wenn aus einer venv gestartet, liegt mpremote meistens neben dem Python-Interpreter.
        python_dir = Path(sys.executable).resolve().parent
        candidate_names = ("mpremote", "mpremote.exe")
        for name in candidate_names:
            candidate = python_dir / name
            if candidate.exists():
                return [str(candidate)]

        # 2) Fallback ueber PATH.
        mpremote_on_path = shutil.which("mpremote")
        if mpremote_on_path:
            return [mpremote_on_path]

        # 3) Letzter Versuch: Modulaufruf ueber das aktuelle Python.
        # Das hilft in manchen Umgebungen ohne Skript-Wrapper.
        try:
            check = subprocess.run(
                [sys.executable, "-m", "mpremote", "--help"],
                capture_output=True,
                text=True,
                timeout=8,
            )
            if check.returncode == 0:
                return [sys.executable, "-m", "mpremote"]
        except (OSError, subprocess.SubprocessError):
            return None

        return None

    def _run_mpremote(self, launcher: list[str], args: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
        return subprocess.run([*launcher, *args], capture_output=True, text=True, timeout=timeout)

    def _friendly_upload_error(self, raw_detail: str) -> str:
        detail = raw_detail.strip()
        lowered = detail.lower()

        if "could not enter raw repl" in lowered:
            return (
                "Upload fehlgeschlagen: ESP32 konnte nicht in den Raw-REPL-Modus wechseln.\n\n"
                "Bitte pruefen:\n"
                "1) Auf dem Board laeuft wirklich MicroPython.\n"
                "2) Kein anderes Programm nutzt den Port (Thonny, Arduino-Serial-Monitor, etc.).\n"
                "3) ESP32 neu starten (Reset-Taste) und Upload erneut ausfuehren.\n"
                "4) Falls noetig, den Port in der GUI neu waehlen."
            )

        if "permission" in lowered or "access is denied" in lowered:
            return "Upload fehlgeschlagen: Kein Zugriff auf den seriellen Port (bereits belegt oder fehlende Rechte)."

        if len(detail) > 400:
            detail = detail[:400] + " ..."
        return f"Upload fehlgeschlagen: {detail}"

    def _copy_file_with_recovery(self, launcher: list[str], port_name: str, source_path: Path, target: str) -> None:
        src = str(source_path)
        attempts: list[tuple[str, list[str], int]] = [
            ("Direkter Upload", ["connect", port_name, "fs", "cp", src, f":{target}"], 45),
            ("Recovery: interrupt + soft-reset", ["connect", port_name, "interrupt", "soft-reset", "fs", "cp", src, f":{target}"], 60),
            ("Recovery: reset + Upload", ["connect", port_name, "reset", "fs", "cp", src, f":{target}"], 60),
        ]

        last_detail = "Unbekannter Fehler"
        for label, args, timeout in attempts:
            self._append_bridge_log(f"{label} ({target})...")
            result = self._run_mpremote(launcher, args, timeout=timeout)
            if result.returncode == 0:
                return
            last_detail = (result.stderr or result.stdout or "Unbekannter Fehler").strip()
            short_detail = last_detail.replace("\n", " ")
            if len(short_detail) > 220:
                short_detail = short_detail[:220] + " ..."
            self._append_bridge_log(f"Fehlversuch: {short_detail}")

        raise FirmwareDeployError(self._friendly_upload_error(last_detail))

    def deploy_bridge_firmware(self) -> None:
        port_name = self.port_combo.currentText().strip()
        if self.serial_bridge.is_connected():
            # Der Upload braucht den Port exklusiv.
            port_name = self.serial_bridge.port_name
            self.disconnect_bridge()

        if not port_name or port_name == "Kein Port gefunden":
            self._show_error("Bitte zuerst einen gueltigen seriellen Port auswaehlen.")
            return

        mpremote_launcher = self._resolve_mpremote_launcher()
        if not mpremote_launcher:
            self._show_error(
                "mpremote wurde nicht gefunden. Bitte in der verwendeten Python-Umgebung installieren: "
                "'python3 -m pip install mpremote'."
            )
            return

        # Die Bridge braucht die ESP-NOW-Bibliothek (nitbw_espnow.py) und das Programm (main.py).
        uploads = (
            (self._firmware_path("nitbw_espnow.py"), "nitbw_espnow.py"),
            (self._firmware_path("esp32_bridge_micropython.py"), "main.py"),
        )
        try:
            for source_path, _target in uploads:
                if not source_path.exists():
                    raise FirmwareDeployError(f"Firmware-Datei nicht gefunden: {source_path}")

            self._append_bridge_log(f"Firmware-Upload gestartet: Bridge -> {port_name}")
            for source_path, target in uploads:
                self._copy_file_with_recovery(mpremote_launcher, port_name, source_path, target)

            reset_cmd = [*mpremote_launcher, "connect", port_name, "reset"]
            reset_result = subprocess.run(reset_cmd, capture_output=True, text=True, timeout=20)
            if reset_result.returncode != 0:
                detail = (reset_result.stderr or reset_result.stdout or "Unbekannter Fehler").strip()
                self._append_bridge_log(f"Hinweis: Soft-Reset nicht erfolgreich ({detail})")

            self._append_bridge_log("Bridge-Firmware erfolgreich auf den ESP32 geschrieben.")
            QMessageBox.information(self, "Roboterarm", "Die Bridge-Firmware wurde auf den ESP32 uebertragen.")
        except (FirmwareDeployError, OSError, subprocess.SubprocessError) as exc:
            self._show_error(str(exc))

    def _create_menu(self) -> None:
        tools_menu = self.menuBar().addMenu("Werkzeuge")
        esp_action = tools_menu.addAction("ESP32-Kommunikation")
        esp_action.triggered.connect(self.open_esp_dialog)

        help_menu = self.menuBar().addMenu("Hilfe")
        readme_action = help_menu.addAction("README anzeigen")
        readme_action.triggered.connect(self.show_readme_help)

    def show_readme_help(self) -> None:
        readme_path = Path(__file__).resolve().parent / "README.md"
        try:
            content = readme_path.read_text(encoding="utf-8")
        except OSError as exc:
            self._show_error(f"README konnte nicht geladen werden: {exc}")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Hilfe - README")
        dialog.resize(920, 700)
        layout = QVBoxLayout(dialog)

        browser = QTextBrowser(dialog)
        browser.setOpenExternalLinks(True)
        browser.setMarkdown(content)
        layout.addWidget(browser)

        close_button = QPushButton("Schliessen", dialog)
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignRight)

        dialog.exec()

    def _change_3d_mode(self) -> None:
        mode = self.view_mode_combo.currentData()
        if not isinstance(mode, str):
            mode = "isometric"
        self.visualizer.set_3d_mode(mode)

    def _spinbox(self, lower: float, upper: float, value: float, step: float = 1.0) -> QDoubleSpinBox:
        spinbox = QDoubleSpinBox()
        spinbox.setRange(lower, upper)
        spinbox.setDecimals(1)
        spinbox.setSingleStep(step)
        spinbox.setValue(value)
        spinbox.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.PlusMinus)
        return spinbox

    def get_config(self) -> RobotConfig:
        return RobotConfig(
            self.base_height.value(),
            self.link_1.value(),
            self.link_2.value(),
            self.servo_open.value(),
            self.servo_closed.value(),
        )

    def calculate_positions(self) -> None:
        self.stop_animation()
        try:
            config = self.get_config()
            targets = self.inputs.targets()
            states, elbow_flags, min_shoulder, min_elbow = solve_safe_path(
                targets,
                config,
                preferred_elbow_up=self.elbow_up.isChecked(),
                min_middle_joint_z=self.middle_joint_clearance.value(),
            )
        except InverseKinematicsError as exc:
            self._show_error(str(exc))
            return

        self.current_config = config
        self.targets = targets
        self.states = states
        self.elbow_flags = elbow_flags
        self.min_path_shoulder_z = min_shoulder
        self.min_path_elbow_z = min_elbow
        self.keyframes = build_keyframes(targets, states, config)

        self.visualizer.set_scene(config, self.keyframes[0].state, self.targets)
        self.result_summary.setHtml(self._build_summary_html())
        self.result_text.setPlainText(self._build_result_text())
        self._update_send_steps()

    def animate_motion(self) -> None:
        if not self.keyframes:
            self.calculate_positions()
            if not self.keyframes:
                return

        self.stop_animation()
        frames: list[JointState] = [self.keyframes[0].state]
        for previous, current in zip(self.keyframes, self.keyframes[1:]):
            seconds = GRIPPER_ACTION_S if current.kind == "gripper" else self.duration.value()
            count = max(10, int(seconds * 30))
            for step in range(1, count + 1):
                frames.append(interpolate_state(previous.state, current.state, step / count))
        self.animation_states = frames
        self.animation_index = 0
        self.animation_timer.start()

    def stop_animation(self) -> None:
        if self.animation_timer.isActive():
            self.animation_timer.stop()

    def _advance_animation(self) -> None:
        if self.current_config is None or self.animation_index >= len(self.animation_states):
            self.animation_timer.stop()
            return

        self.visualizer.set_scene(self.current_config, self.animation_states[self.animation_index], self.targets)
        self.animation_index += 1

    def refresh_serial_ports(self) -> None:
        current = self.port_combo.currentText()
        self.port_combo.clear()
        ports = self.serial_bridge.available_ports()
        if ports:
            self.port_combo.addItems(ports)
            if current in ports:
                self.port_combo.setCurrentText(current)
        else:
            self.port_combo.addItem("Kein Port gefunden")
        if serial is None:
            self._append_bridge_log("pyserial nicht verfuegbar.")

    def connect_bridge(self) -> None:
        port_name = self.port_combo.currentText().strip()
        if not port_name or port_name == "Kein Port gefunden":
            self._show_error("Bitte zuerst einen gueltigen seriellen Port auswaehlen.")
            return
        try:
            baudrate = int(self.baud_combo.currentText())
        except ValueError:
            self._show_error("Bitte eine gueltige Baudrate angeben.")
            return

        try:
            self.serial_bridge.connect(port_name, baudrate)
        except SerialBridgeError as exc:
            self._show_error(str(exc))
            return

        self.bridge_status.setText(f"Verbunden: {port_name} @ {baudrate}")
        self._append_bridge_log(f"Verbunden mit {port_name} @ {baudrate}.")
        self.peer_last_ok = [None] * len(MOTOR_LAYOUT)
        self.poll_timer.start()
        self._update_bridge_controls()
        # Die Bridge antwortet mit ihrer MAC; die MAC-Liste wird beim Eintreffen von "ready" uebertragen.
        self._send_to_bridge({"command": "info"})

    def disconnect_bridge(self) -> None:
        self.poll_timer.stop()
        self.serial_bridge.disconnect()
        self.bridge_status.setText("Nicht verbunden")
        self.peer_last_ok = [None] * len(MOTOR_LAYOUT)
        self._append_bridge_log("Serielle Verbindung getrennt.")
        self._update_bridge_controls()
        self._refresh_espnow_status()

    def _send_to_bridge(self, payload: dict[str, Any]) -> bool:
        try:
            self.serial_bridge.send_payload(payload)
        except SerialBridgeError as exc:
            self._append_bridge_log(f"Fehler: {exc}")
            return False
        return True

    def _poll_bridge(self) -> None:
        try:
            lines = self.serial_bridge.read_lines()
        except SerialBridgeError as exc:
            self.disconnect_bridge()
            self._append_bridge_log(f"Verbindung verloren: {exc}")
            return
        for line in lines:
            self._handle_bridge_line(line)

    def _motor_label(self, motor_id: int) -> str:
        for known_id, _name, label in MOTOR_LAYOUT:
            if known_id == motor_id:
                return f"Motor {motor_id} ({label})"
        return f"Motor {motor_id}"

    def _handle_bridge_line(self, line: str) -> None:
        try:
            msg = json.loads(line)
        except ValueError:
            if "'command'" not in line:  # Python-Repr des Echos, siehe unten
                self._append_bridge_log(f"Bridge: {line}")
            return
        if not isinstance(msg, dict):
            self._append_bridge_log(f"Bridge: {line}")
            return
        if "command" in msg:
            self._append_bridge_log(
                "Der ESP32 antwortet nur mit der MicroPython-Konsole – die Bridge-Firmware läuft nicht. "
                "Bitte 'Bridge-Firmware auf ESP32 schreiben' klicken."
            )
            return

        status = msg.get("status")
        now = time.monotonic()
        if status == "ready":
            mac = str(msg.get("mac", ""))
            self.bridge_mac_edit.setText(mac)
            self._append_bridge_log(f"Bridge bereit, MAC {mac}")
            self._send_peer_config()
        elif status == "config":
            self._append_bridge_log(f"Bridge kennt {msg.get('count', 0)} Schüler-ESP32.")
        elif status == "tx":
            motor_id = int(msg.get("motor_id", 0))
            ok = msg.get("result") == "ok"
            if 1 <= motor_id <= len(self.peer_last_ok):
                self.peer_last_ok[motor_id - 1] = now if ok else None
            self._append_bridge_log(
                f"→ {self._motor_label(motor_id)} {msg.get('mac', '')}  "
                f"{float(msg.get('target_deg', 0.0)):7.2f}°  {msg.get('duration_ms', 0)} ms  "
                f"{'angekommen' if ok else 'KEINE Bestätigung'}"
            )
        elif status == "peer":
            motor_id = int(msg.get("motor_id", 0))
            if 1 <= motor_id <= len(self.peer_last_ok):
                self.peer_last_ok[motor_id - 1] = now if msg.get("online") else None
        elif status == "rx":
            sender = normalize_mac(str(msg.get("mac", "")))
            for index, edit in enumerate(self.peer_edits):
                if sender is not None and normalize_mac(edit.text()) == sender:
                    self.peer_last_ok[index] = now
            self._append_bridge_log(f"← {msg.get('mac', '')}  {msg.get('data', '')}")
        elif status == "ok":
            self._append_bridge_log(
                f"Befehl {msg.get('sequence')}: weitergeleitet {msg.get('forwarded', 0)}, "
                f"ohne MAC/ungültig {msg.get('invalid', 0)}, ohne Bestätigung {msg.get('failed', 0)}"
            )
        elif status == "error":
            self._append_bridge_log(f"Bridge-Fehler: {msg.get('message', '')}")
        else:
            self._append_bridge_log(f"Bridge: {line}")
        self._refresh_espnow_status()

    def _refresh_espnow_status(self) -> None:
        now = time.monotonic()
        configured = 0
        online = 0
        for index, edit in enumerate(self.peer_edits):
            has_mac = normalize_mac(edit.text()) is not None
            last_ok = self.peer_last_ok[index]
            is_online = has_mac and last_ok is not None and now - last_ok < PEER_TIMEOUT_S
            configured += has_mac
            online += is_online
            color = "#16a34a" if is_online else ("#94a3b8" if not has_mac else "#ef4444")
            self.peer_dots[index].setStyleSheet(f"color: {color}; font-size: 18px;")
            self.peer_dots[index].setToolTip("erreichbar" if is_online else ("nicht erreichbar" if has_mac else "keine MAC"))

        if online:
            text, color = f"● Verbunden – {online} von {configured} ESP32 erreichbar", "#16a34a"
        elif self.serial_bridge.is_connected():
            text, color = "● Bridge verbunden – kein ESP32 erreichbar", "#f59e0b"
        else:
            text, color = "● Nicht verbunden", "#94a3b8"
        self.espnow_status.setText(text)
        self.espnow_status.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 15px;")

    # --- Roboter-Profile (MAC-Adressen) ------------------------------------
    def _collect_macs(self) -> list[str] | None:
        """Gibt die vier MACs (leer = nicht belegt) zurueck, None bei ungueltiger Eingabe."""
        macs: list[str] = []
        valid = True
        for edit in self.peer_edits:
            text = edit.text().strip()
            normalized = normalize_mac(text) if text else ""
            if normalized is None:
                valid = False
                edit.setStyleSheet("border: 1px solid #ef4444;")
            else:
                edit.setStyleSheet("")
                macs.append(normalized)
        return macs if valid else None

    def _peer_edit_finished(self) -> None:
        macs = self._collect_macs()
        if macs is None:
            return
        for edit, mac in zip(self.peer_edits, macs):
            edit.setText(mac)
        self._send_peer_config()
        self._refresh_espnow_status()

    def _send_peer_config(self) -> None:
        macs = self._collect_macs()
        if macs is None or not self.serial_bridge.is_connected():
            return
        self.peer_last_ok = [None] * len(MOTOR_LAYOUT)
        self._send_to_bridge({"command": "config", "peers": macs})

    def _reload_profile_combo(self, select: str = "") -> None:
        self.profile_combo.clear()
        self.profile_combo.addItems(sorted(self.profile_store.profiles))
        if select in self.profile_store.profiles:
            self.profile_combo.setCurrentText(select)
            self._load_profile()
        else:
            self.profile_combo.setCurrentIndex(-1)

    def _load_profile(self, *_args: object) -> None:
        name = self.profile_combo.currentText().strip()
        macs = self.profile_store.profiles.get(name)
        if macs is None:
            return
        for edit, mac in zip(self.peer_edits, macs):
            edit.setText(mac)
        self.profile_store.last = name
        self._try_save_profiles()
        self._collect_macs()
        self._send_peer_config()
        self._refresh_espnow_status()

    def save_profile(self) -> None:
        name = self.profile_combo.currentText().strip()
        if not name:
            self._show_error("Bitte einen Namen für den Roboter eingeben.")
            return
        macs = self._collect_macs()
        if macs is None:
            self._show_error("Mindestens eine MAC-Adresse ist ungültig (Format AA:BB:CC:DD:EE:FF).")
            return
        self.profile_store.profiles[name] = macs
        self.profile_store.last = name
        if self._try_save_profiles():
            self._append_bridge_log(f"Konfiguration '{name}' gespeichert.")
        self._reload_profile_combo()
        self.profile_combo.setCurrentText(name)
        self._send_peer_config()

    def delete_profile(self) -> None:
        name = self.profile_combo.currentText().strip()
        if name not in self.profile_store.profiles:
            return
        answer = QMessageBox.question(self, "Roboterarm", f"Konfiguration '{name}' löschen?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        del self.profile_store.profiles[name]
        if self.profile_store.last == name:
            self.profile_store.last = ""
        self._try_save_profiles()
        self._reload_profile_combo()

    def _try_save_profiles(self) -> bool:
        try:
            self.profile_store.save()
        except OSError as exc:
            self._show_error(f"Konfiguration konnte nicht gespeichert werden: {exc}")
            return False
        return True

    def copy_bridge_mac(self) -> None:
        mac = self.bridge_mac_edit.text().strip()
        if mac:
            QApplication.clipboard().setText(mac)

    def _update_send_steps(self) -> None:
        current = self.send_step_combo.currentIndex()
        self.send_step_combo.clear()
        for index, frame in enumerate(self.keyframes):
            self.send_step_combo.addItem(frame.label, index)
        if 0 <= current < self.send_step_combo.count():
            self.send_step_combo.setCurrentIndex(current)
        self._update_bridge_controls()

    def send_selected_step(self) -> None:
        if not self.keyframes:
            self.calculate_positions()
            if not self.keyframes:
                return

        index = self.send_step_combo.currentData()
        if not isinstance(index, int) or not 0 <= index < len(self.keyframes):
            self._show_error("Es sind noch keine berechneten Positionen vorhanden.")
            return

        frame = self.keyframes[index]
        seconds = GRIPPER_ACTION_S if frame.kind == "gripper" else self.duration.value()
        payload = build_serial_payload(f"Schritt {frame.label}", self.targets[frame.point_index], frame.state, seconds)
        if self._send_to_bridge(payload):
            self._append_bridge_log(f"Schritt {frame.label} an Bridge gesendet.")

    def _update_bridge_controls(self) -> None:
        connected = self.serial_bridge.is_connected()
        has_serial = serial is not None
        self.connect_bridge_button.setEnabled(has_serial and not connected)
        self.disconnect_bridge_button.setEnabled(connected)
        self.send_step_combo.setEnabled(connected and self.send_step_combo.count() > 0)
        self.send_step_button.setEnabled(connected and self.send_step_combo.count() > 0)
        self.deploy_firmware_button.setEnabled(has_serial)
        self.refresh_ports_button.setEnabled(not connected)
        self.port_combo.setEnabled(not connected)
        self.baud_combo.setEnabled(not connected)
        if not connected and self.bridge_status.text() != "Nicht verbunden":
            self.bridge_status.setText("Nicht verbunden")

    def _build_result_text(self) -> str:
        if not self.keyframes:
            return ""

        min_shoulder_text = "unbekannt" if self.min_path_shoulder_z is None else f"{self.min_path_shoulder_z:.2f} cm"
        min_elbow_text = "unbekannt" if self.min_path_elbow_z is None else f"{self.min_path_elbow_z:.2f} cm"
        lines = ["Sicherheitspruefung mittlere Gelenke", f"Eingestellter Sicherheitsabstand: {self.middle_joint_clearance.value():.2f} cm"]
        for index, elbow_up in enumerate(self.elbow_flags):
            lines.append(f"IK-Loesung {waypoint_name(index)}: {'eingeklappt' if elbow_up else 'ausgeklappt'}")
        lines.append(f"Mindesthoehe Schulter entlang der Bahn: {min_shoulder_text}")
        lines.append(f"Mindesthoehe Ellbogen entlang der Bahn: {min_elbow_text}")
        text = "\n".join(lines) + "\n\n"

        for frame in self.keyframes:
            target = self.targets[frame.point_index]
            seconds = GRIPPER_ACTION_S if frame.kind == "gripper" else self.duration.value()
            payload = build_serial_payload(f"Schritt {frame.label}", target, frame.state, seconds)
            text += self._format_result(f"Schritt {frame.label}", target, frame.state) + "\n"
            text += json.dumps(payload, indent=2, ensure_ascii=True) + "\n\n"
        return text

    def _format_result(self, title: str, target: TargetPoint, state: JointState) -> str:
        return (
            f"{title}\n"
            f"Zielpunkt: x={target.x:6.1f} cm, y={target.y:6.1f} cm, z={target.z:6.1f} cm\n"
            f"Motor 1 Standachse (Stepper) : {state.base_deg:7.2f}°\n"
            f"Motor 2 Arm kippen (Stepper) : {state.shoulder_deg:7.2f}°\n"
            f"Motor 3 Handgelenk (Stepper) : {state.wrist_deg:7.2f}°\n"
            f"Greifer (Servo SG90)         : {state.gripper_deg:7.2f}°\n"
        )

    def _append_bridge_log(self, text: str) -> None:
        self.bridge_log.append(f"{time.strftime('%H:%M:%S')}  {text}")

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "Roboterarm", message)


def main() -> int:
    app = QApplication(sys.argv)
    app.setOrganizationName("Roboterarm")
    app.setApplicationName("Roboterarm")
    app.setStyle("Fusion")
    app.setFont(QFont(FONT_FAMILY, 13))
    app.setStyleSheet(APP_STYLE)
    app.setWindowIcon(QIcon(str(asset_path("logo.png"))))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())