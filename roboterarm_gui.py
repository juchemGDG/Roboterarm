from __future__ import annotations

import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QPointF, QTimer, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
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
    QMainWindow,
    QMessageBox,
    QPushButton,
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


MOTOR_LAYOUT = (
    (1, "base", "Standachse"),
    (2, "shoulder", "Arm kippen"),
    (3, "wrist", "Handgelenk"),
    (4, "gripper", "Klammer"),
)


@dataclass
class RobotConfig:
    base_height: float
    link_1: float
    link_2: float


@dataclass
class TargetPoint:
    x: float
    y: float
    z: float
    gripper: float


@dataclass
class JointState:
    base_deg: float
    shoulder_deg: float
    wrist_deg: float
    gripper_deg: float


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
        gripper_deg=target.gripper,
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


def solve_safe_motion_pair(
    start_target: TargetPoint,
    end_target: TargetPoint,
    config: RobotConfig,
    preferred_elbow_up: bool,
    min_middle_joint_z: float = 0.0,
) -> tuple[JointState, JointState, bool, bool, float, float]:
    preferred = [preferred_elbow_up, not preferred_elbow_up]

    candidates: list[tuple[JointState, JointState, bool, bool, float, float]] = []
    for start_elbow_up in preferred:
        for end_elbow_up in preferred:
            try:
                start_state = solve_inverse_kinematics(start_target, config, start_elbow_up)
                end_state = solve_inverse_kinematics(end_target, config, end_elbow_up)
            except InverseKinematicsError:
                continue

            min_shoulder, min_elbow = min_middle_joint_heights_on_path(start_state, end_state, config)
            candidates.append((start_state, end_state, start_elbow_up, end_elbow_up, min_shoulder, min_elbow))

    safe_candidates = [
        candidate
        for candidate in candidates
        if candidate[4] >= min_middle_joint_z and candidate[5] >= min_middle_joint_z
    ]
    if safe_candidates:
        return safe_candidates[0]

    if candidates:
        best = max(candidates, key=lambda item: min(item[4], item[5]))
        raise InverseKinematicsError(
            "Keine sichere Bahn gefunden: Mindestens ein mittleres Gelenk unterschreitet den Sicherheitsabstand. "
            f"Beste gefundene Mindesthoehen: Schulter z={best[4]:.2f} cm, Ellbogen z={best[5]:.2f} cm."
        )

    raise InverseKinematicsError("Es konnte keine gueltige IK-Kombination fuer Start/Ziel gefunden werden.")


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
            "gripper": round(target.gripper, 2),
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


class SerialBridge:
    def __init__(self) -> None:
        self.connection: Any | None = None
        self.port_name = ""
        self.baudrate = 115200

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
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def is_connected(self) -> bool:
        return self.connection is not None and bool(getattr(self.connection, "is_open", False))

    def send_payload(self, payload: dict[str, Any]) -> list[str]:
        if not self.is_connected():
            raise SerialBridgeError("Keine serielle Verbindung zur ESP32-Bridge aktiv.")

        line = json.dumps(payload, separators=(",", ":")) + "\n"
        try:
            self.connection.reset_input_buffer()
            self.connection.write(line.encode("utf-8"))
            self.connection.flush()
        except Exception as exc:
            raise SerialBridgeError(f"Senden fehlgeschlagen: {exc}") from exc

        responses: list[str] = []
        deadline = time.monotonic() + 0.45
        while time.monotonic() < deadline:
            try:
                raw = self.connection.readline()
            except Exception as exc:
                raise SerialBridgeError(f"Lesen der Bridge-Antwort fehlgeschlagen: {exc}") from exc
            if not raw:
                break
            responses.append(raw.decode("utf-8", errors="replace").strip())
        return responses


class ArmViewBase(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.config: RobotConfig | None = None
        self.state: JointState | None = None
        self.start_target: TargetPoint | None = None
        self.end_target: TargetPoint | None = None

    def set_scene(
        self,
        config: RobotConfig | None,
        state: JointState | None,
        start_target: TargetPoint | None,
        end_target: TargetPoint | None,
    ) -> None:
        self.config = config
        self.state = state
        self.start_target = start_target
        self.end_target = end_target
        self.update()


class SideViewWidget(ArmViewBase):
    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(320)

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#fffef7"))

        if self.config is None or self.state is None:
            painter.setPen(QColor("#4b5563"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Noch keine Berechnung vorhanden")
            return

        config = self.config
        state = self.state
        points = forward_kinematics(state, config)
        width = self.width()
        height = self.height()
        padding = 28
        total_length = config.link_1 + config.link_2 + config.base_height + 10
        scale = min((width - 2 * padding) / max(total_length, 1), (height - 2 * padding) / max(total_length, 1))
        origin_x = padding
        origin_y = height - padding

        def project(point: tuple[float, float, float]) -> QPointF:
            x, y, z = point
            radial = math.hypot(x, y)
            return QPointF(origin_x + radial * scale, origin_y - z * scale)

        painter.setPen(QPen(QColor("#8f8f8f"), 2))
        painter.drawLine(origin_x, origin_y, width - padding, origin_y)
        painter.drawLine(origin_x, origin_y, origin_x, padding)
        painter.setPen(QColor("#555555"))
        painter.drawText(width - padding - 18, origin_y - 10, "r")
        painter.drawText(origin_x + 8, padding + 14, "z")

        for target, color in ((self.start_target, QColor("#2f7d32")), (self.end_target, QColor("#b84a3a"))):
            if target is None:
                continue
            marker = project((target.x, target.y, target.z))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(marker, 5, 5)

        base = project(points["base"])
        shoulder = project(points["shoulder"])
        elbow = project(points["elbow"])
        tool = project(points["tool"])

        painter.setPen(QPen(QColor("#2d4059"), 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(base, shoulder)
        painter.setPen(QPen(QColor("#ea5455"), 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(shoulder, elbow)
        painter.setPen(QPen(QColor("#f07b3f"), 9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(elbow, tool)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#233142"))
        for point in (base, shoulder, elbow, tool):
            painter.drawEllipse(point, 5, 5)

        self._draw_gripper(painter, tool, math.radians(state.shoulder_deg + state.wrist_deg), state.gripper_deg, scale)
        painter.setPen(QColor("#111827"))
        painter.setFont(QFont("Helvetica", 11, QFont.Weight.Bold))
        painter.drawText(
            0,
            18,
            width,
            20,
            Qt.AlignmentFlag.AlignCenter,
            (
                f"Motor 1: {state.base_deg:6.1f}°    "
                f"Motor 2: {state.shoulder_deg:6.1f}°    "
                f"Motor 3: {state.wrist_deg:6.1f}°    "
                f"Motor 4: {state.gripper_deg:6.1f}°"
            ),
        )

    def _draw_gripper(self, painter: QPainter, tool: QPointF, tool_angle: float, opening_deg: float, scale: float) -> None:
        jaw_length = 8 + scale * 0.8
        base_length = 10
        opening_rad = math.radians(opening_deg / 2)
        back = QPointF(tool.x() - math.cos(tool_angle) * base_length, tool.y() + math.sin(tool_angle) * base_length)

        painter.setPen(QPen(QColor("#364f6b"), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(back, tool)
        painter.setPen(QPen(QColor("#364f6b"), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for offset in (-opening_rad, opening_rad):
            angle = tool_angle + offset
            end_point = QPointF(tool.x() + math.cos(angle) * jaw_length, tool.y() - math.sin(angle) * jaw_length)
            painter.drawLine(tool, end_point)


class TopViewWidget(ArmViewBase):
    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(260)

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#f4f7fb"))

        if self.config is None or self.state is None:
            painter.setPen(QColor("#4b5563"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Draufsicht")
            return

        config = self.config
        points = forward_kinematics(self.state, config)
        width = self.width()
        height = self.height()
        padding = 24
        max_radius = config.link_1 + config.link_2 + 10
        scale = min((width / 2 - padding) / max(max_radius, 1), (height / 2 - padding) / max(max_radius, 1))
        center_x = width / 2
        center_y = height / 2

        def project(point: tuple[float, float, float]) -> QPointF:
            x, y, _ = point
            return QPointF(center_x + x * scale, center_y - y * scale)

        painter.setPen(QPen(QColor("#9ca3af"), 1.5))
        painter.drawLine(padding, center_y, width - padding, center_y)
        painter.drawLine(center_x, padding, center_x, height - padding)
        painter.setPen(QColor("#555555"))
        painter.drawText(width - padding - 10, int(center_y - 10), "x")
        painter.drawText(int(center_x + 10), padding + 14, "y")
        painter.setPen(QPen(QColor("#d6dbe4"), 1.5))
        radius = (config.link_1 + config.link_2) * scale
        painter.drawEllipse(QPointF(center_x, center_y), radius, radius)

        for target, color in ((self.start_target, QColor("#2f7d32")), (self.end_target, QColor("#b84a3a"))):
            if target is None:
                continue
            marker = project((target.x, target.y, target.z))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(marker, 5, 5)

        shoulder = project(points["shoulder"])
        elbow = project(points["elbow"])
        tool = project(points["tool"])
        painter.setPen(QPen(QColor("#ea5455"), 7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(shoulder, elbow)
        painter.setPen(QPen(QColor("#f07b3f"), 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(elbow, tool)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#233142"))
        for point in (shoulder, elbow, tool):
            painter.drawEllipse(point, 5, 5)

        painter.setPen(QColor("#111827"))
        painter.setFont(QFont("Helvetica", 11, QFont.Weight.Bold))
        painter.drawText(0, 10, width, 20, Qt.AlignmentFlag.AlignCenter, "Draufsicht")


class ThreeDViewWidget(ArmViewBase):
    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(320)
        # Isometrische Ansicht: 45 Grad um z, danach ca. 35.264 Grad um x.
        self.iso_yaw = math.radians(45)
        self.iso_pitch = math.atan(math.sqrt(2) / 2)
        self.yaw = self.iso_yaw
        self.pitch = self.iso_pitch
        self.is_isometric = True
        self._drag_active = False
        self._last_mouse_x = 0
        self._last_mouse_y = 0

    def set_view_mode(self, mode: str) -> None:
        self.is_isometric = mode == "isometric"
        if self.is_isometric:
            self.yaw = self.iso_yaw
            self.pitch = self.iso_pitch
        self.update()

    def reset_camera(self) -> None:
        self.yaw = self.iso_yaw
        self.pitch = self.iso_pitch
        self.update()

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#f8f8fd"))

        if self.config is None or self.state is None:
            painter.setPen(QColor("#4b5563"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._title_text())
            return

        config = self.config
        points = forward_kinematics(self.state, config)
        width = self.width()
        height = self.height()
        padding = 28
        max_extent = config.link_1 + config.link_2 + config.base_height + 12
        scale = min((width - 2 * padding) / max(2 * max_extent, 1), (height - 2 * padding) / max(1.6 * max_extent, 1))
        center_x = width / 2
        center_y = height / 2 + 35

        def project(point: tuple[float, float, float]) -> tuple[QPointF, float]:
            x, y, z = point
            x1 = x * math.cos(self.yaw) - y * math.sin(self.yaw)
            y1 = x * math.sin(self.yaw) + y * math.cos(self.yaw)
            y2 = y1 * math.cos(self.pitch) - z * math.sin(self.pitch)
            depth = y1 * math.sin(self.pitch) + z * math.cos(self.pitch)
            return QPointF(center_x + x1 * scale, center_y + y2 * scale), depth

        self._draw_grid(painter, scale, center_x, center_y, max_extent)

        projected = {name: project(point) for name, point in points.items()}
        segments = [
            (points["base"], points["shoulder"], QColor("#2d4059"), 8),
            (points["shoulder"], points["elbow"], QColor("#ea5455"), 10),
            (points["elbow"], points["tool"], QColor("#f07b3f"), 9),
        ]
        ordered_segments = sorted(segments, key=lambda item: (project(item[0])[1] + project(item[1])[1]) / 2)
        for start, end, color, width_px in ordered_segments:
            start_point, _ = project(start)
            end_point, _ = project(end)
            painter.setPen(QPen(color, width_px, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(start_point, end_point)

        for target, color, label in (
            (self.start_target, QColor("#2f7d32"), "A"),
            (self.end_target, QColor("#b84a3a"), "B"),
        ):
            if target is None:
                continue
            marker, _ = project((target.x, target.y, target.z))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(marker, 5, 5)
            painter.setPen(color.darker(130))
            painter.setFont(QFont("Helvetica", 10, QFont.Weight.Bold))
            painter.drawText(marker + QPointF(8, -6), label)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#233142"))
        for name in ("base", "shoulder", "elbow", "tool"):
            point, _ = projected[name]
            painter.drawEllipse(point, 5, 5)

        tool_angle = math.radians(self.state.shoulder_deg + self.state.wrist_deg)
        self._draw_gripper_3d(painter, points["tool"], math.radians(self.state.base_deg), tool_angle, self.state.gripper_deg, project)
        painter.setPen(QColor("#111827"))
        painter.setFont(QFont("Helvetica", 11, QFont.Weight.Bold))
        painter.drawText(0, 12, width, 20, Qt.AlignmentFlag.AlignCenter, self._title_text())

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

    def _title_text(self) -> str:
        if self.is_isometric:
            return "3D-Ansicht (isometrisch)"
        return "3D-Ansicht (frei, Maus ziehen)"

    def _draw_grid(self, painter: QPainter, scale: float, center_x: float, center_y: float, max_extent: float) -> None:
        painter.setPen(QPen(QColor("#e2e8f0"), 1))
        step = 10
        for value in range(-int(max_extent), int(max_extent) + 1, step):
            start_a, _ = self._project_helper((-max_extent, value, 0.0), scale, center_x, center_y)
            end_a, _ = self._project_helper((max_extent, value, 0.0), scale, center_x, center_y)
            start_b, _ = self._project_helper((value, -max_extent, 0.0), scale, center_x, center_y)
            end_b, _ = self._project_helper((value, max_extent, 0.0), scale, center_x, center_y)
            painter.drawLine(start_a, end_a)
            painter.drawLine(start_b, end_b)

        for axis_end, color, label in (
            ((18.0, 0.0, 0.0), QColor("#2563eb"), "x"),
            ((0.0, 18.0, 0.0), QColor("#16a34a"), "y"),
            ((0.0, 0.0, 18.0), QColor("#dc2626"), "z"),
        ):
            start, _ = self._project_helper((0.0, 0.0, 0.0), scale, center_x, center_y)
            end, _ = self._project_helper(axis_end, scale, center_x, center_y)
            painter.setPen(QPen(color, 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(start, end)
            painter.setPen(color)
            painter.drawText(end + QPointF(4, -4), label)

    def _project_helper(self, point: tuple[float, float, float], scale: float, center_x: float, center_y: float) -> tuple[QPointF, float]:
        x, y, z = point
        x1 = x * math.cos(self.yaw) - y * math.sin(self.yaw)
        y1 = x * math.sin(self.yaw) + y * math.cos(self.yaw)
        y2 = y1 * math.cos(self.pitch) - z * math.sin(self.pitch)
        depth = y1 * math.sin(self.pitch) + z * math.cos(self.pitch)
        return QPointF(center_x + x1 * scale, center_y + y2 * scale), depth

    def _draw_gripper_3d(
        self,
        painter: QPainter,
        tool_point: tuple[float, float, float],
        base_angle: float,
        elevation_angle: float,
        opening_deg: float,
        project,
    ) -> None:
        length = 4.5
        reach_vector = (
            math.cos(elevation_angle) * math.cos(base_angle),
            math.cos(elevation_angle) * math.sin(base_angle),
            math.sin(elevation_angle),
        )
        left_dir = (
            -math.sin(base_angle),
            math.cos(base_angle),
            0.0,
        )
        opening_factor = math.sin(math.radians(opening_deg / 2)) * 2.2
        endpoints = []
        for direction in (-1.0, 1.0):
            end = (
                tool_point[0] + reach_vector[0] * length + left_dir[0] * opening_factor * direction,
                tool_point[1] + reach_vector[1] * length + left_dir[1] * opening_factor * direction,
                tool_point[2] + reach_vector[2] * length,
            )
            endpoints.append(end)

        tool_screen, _ = project(tool_point)
        painter.setPen(QPen(QColor("#364f6b"), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for end in endpoints:
            end_screen, _ = project(end)
            painter.drawLine(tool_screen, end_screen)


class VisualizerPanel(QFrame):
    def __init__(self) -> None:
        super().__init__()
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(10)
        self.side_view = SideViewWidget()
        self.three_d_view = ThreeDViewWidget()
        self.top_view = TopViewWidget()
        layout.addWidget(self.side_view, 0, 0)
        layout.addWidget(self.three_d_view, 0, 1)
        layout.addWidget(self.top_view, 1, 0, 1, 2)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)
        layout.setRowStretch(0, 3)
        layout.setRowStretch(1, 2)

    def set_scene(
        self,
        config: RobotConfig | None,
        state: JointState | None,
        start_target: TargetPoint | None,
        end_target: TargetPoint | None,
    ) -> None:
        self.side_view.set_scene(config, state, start_target, end_target)
        self.three_d_view.set_scene(config, state, start_target, end_target)
        self.top_view.set_scene(config, state, start_target, end_target)

    def set_3d_mode(self, mode: str) -> None:
        self.three_d_view.set_view_mode(mode)

    def reset_3d_camera(self) -> None:
        self.three_d_view.reset_camera()


class MotorInputGrid(QWidget):
    def __init__(self, title_a: str, title_b: str) -> None:
        super().__init__()
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(8)

        headers = ("Punkt", "x [cm]", "y [cm]", "z [cm]", "Klammer [°]")
        for column, header in enumerate(headers):
            label = QLabel(header)
            label.setStyleSheet("font-weight: 600;")
            layout.addWidget(label, 0, column)

        self.start_x = self._spinbox(-200, 200, 18)
        self.start_y = self._spinbox(-200, 200, 8)
        self.start_z = self._spinbox(-200, 200, 18)
        self.start_gripper = self._spinbox(0, 90, 8)
        self.end_x = self._spinbox(-200, 200, 12)
        self.end_y = self._spinbox(-200, 200, -14)
        self.end_z = self._spinbox(-200, 200, 20)
        self.end_gripper = self._spinbox(0, 90, 24)

        values = (
            (title_a, self.start_x, self.start_y, self.start_z, self.start_gripper),
            (title_b, self.end_x, self.end_y, self.end_z, self.end_gripper),
        )
        for row, row_values in enumerate(values, start=1):
            layout.addWidget(QLabel(row_values[0]), row, 0)
            for column, widget in enumerate(row_values[1:], start=1):
                layout.addWidget(widget, row, column)

    def _spinbox(self, lower: float, upper: float, value: float) -> QDoubleSpinBox:
        spinbox = QDoubleSpinBox()
        spinbox.setRange(lower, upper)
        spinbox.setDecimals(1)
        spinbox.setSingleStep(1.0)
        spinbox.setValue(value)
        spinbox.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.PlusMinus)
        return spinbox

    def start_target(self) -> TargetPoint:
        return TargetPoint(self.start_x.value(), self.start_y.value(), self.start_z.value(), self.start_gripper.value())

    def end_target(self) -> TargetPoint:
        return TargetPoint(self.end_x.value(), self.end_y.value(), self.end_z.value(), self.end_gripper.value())


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Roboterarm Steuerung")
        self.resize(1380, 900)

        self.start_state: JointState | None = None
        self.end_state: JointState | None = None
        self.start_target_value: TargetPoint | None = None
        self.end_target_value: TargetPoint | None = None
        self.current_config: RobotConfig | None = None
        self.start_elbow_up: bool | None = None
        self.end_elbow_up: bool | None = None
        self.min_path_shoulder_z: float | None = None
        self.min_path_elbow_z: float | None = None
        self.serial_bridge = SerialBridge()
        self.animation_frames = 0
        self.animation_index = 0
        self.animation_timer = QTimer(self)
        self.animation_timer.setInterval(33)
        self.animation_timer.timeout.connect(self._advance_animation)

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(14, 14, 14, 14)
        root_layout.setSpacing(14)

        controls = QWidget()
        controls.setFixedWidth(440)
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(12)

        geometry_box = QGroupBox("Geometrie")
        geometry_layout = QGridLayout(geometry_box)
        self.base_height = self._spinbox(0, 200, 12)
        self.link_1 = self._spinbox(1, 200, 20)
        self.link_2 = self._spinbox(1, 200, 18)
        self.duration = self._spinbox(0.5, 20, 3.0, step=0.5)
        self.middle_joint_clearance = self._spinbox(0.0, 50.0, 2.0, step=0.5)
        geometry_labels = (
            ("Sockelhoehe z0 [cm]", self.base_height),
            ("Armlaenge 1 [cm]", self.link_1),
            ("Armlaenge 2 [cm]", self.link_2),
            ("Animationsdauer [s]", self.duration),
            ("Sicherheitsabstand z [cm]", self.middle_joint_clearance),
        )
        for row, (label, widget) in enumerate(geometry_labels):
            geometry_layout.addWidget(QLabel(label), row, 0)
            geometry_layout.addWidget(widget, row, 1)

        self.elbow_up = QCheckBox("Alternative IK-Loesung (eingeklappt)")
        geometry_layout.addWidget(self.elbow_up, len(geometry_labels), 0, 1, 2)

        positions_box = QGroupBox("Positionen")
        positions_layout = QVBoxLayout(positions_box)
        self.inputs = MotorInputGrid("A", "B")
        positions_layout.addWidget(self.inputs)

        button_box = QWidget()
        button_layout = QVBoxLayout(button_box)
        button_layout.setContentsMargins(0, 0, 0, 0)
        self.calculate_button = QPushButton("Winkel berechnen")
        self.animate_button = QPushButton("Bewegung animieren")
        self.stop_button = QPushButton("Animation stoppen")
        button_layout.addWidget(self.calculate_button)
        button_layout.addWidget(self.animate_button)
        button_layout.addWidget(self.stop_button)

        self.port_combo = QComboBox()
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["115200", "230400", "460800"])
        self.baud_combo.setCurrentText("115200")
        self.refresh_ports_button = QPushButton("Ports suchen")
        self.connect_bridge_button = QPushButton("Verbinden")
        self.disconnect_bridge_button = QPushButton("Trennen")
        self.send_a_button = QPushButton("Position A senden")
        self.send_b_button = QPushButton("Position B senden")
        self.firmware_combo = QComboBox()
        self.firmware_combo.addItem("Bridge (MicroPython)", "bridge")
        self.firmware_combo.addItem("Motor-Empfaenger (MicroPython)", "motor")
        self.firmware_motor_id = QComboBox()
        self.firmware_motor_id.addItems(["1", "2", "3", "4"])
        self.deploy_firmware_button = QPushButton("Firmware als main.py auf ESP32")
        self.bridge_status = QLabel("Nicht verbunden")
        self.bridge_log = QTextEdit()
        self.bridge_log.setReadOnly(True)
        self.bridge_log.setMinimumHeight(120)
        self.esp_dialog = self._create_esp_dialog()

        result_box = QGroupBox("Ergebnis")
        result_layout = QVBoxLayout(result_box)
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setFont(QFont("Courier New", 11))
        self.result_text.setMinimumHeight(260)
        result_layout.addWidget(self.result_text)

        controls_layout.addWidget(geometry_box)
        controls_layout.addWidget(positions_box)
        controls_layout.addWidget(button_box)
        controls_layout.addWidget(result_box, stretch=1)

        visuals = QWidget()
        visuals_layout = QVBoxLayout(visuals)
        visuals_layout.setContentsMargins(0, 0, 0, 0)
        visuals_layout.setSpacing(12)

        info_box = QGroupBox("Annahmen")
        info_layout = QVBoxLayout(info_box)
        info_label = QLabel(
            "Der Roboter wird als 2-gliedriger Arm mit drehbarer Basis modelliert. "
            "Motor 1 dreht um die Standachse, Motor 2 kippt das erste Segment, "
            "Motor 3 kippt das zweite Segment relativ zum ersten, Motor 4 steuert die Klammer. "
            "Ein angeschlossener ESP32 kann die berechneten Zielwinkel seriell empfangen und per ESP-NOW an die Motor-Controller weiterleiten."
        )
        info_label.setWordWrap(True)
        info_layout.addWidget(info_label)

        view_controls = QHBoxLayout()
        view_controls.addWidget(QLabel("3D-Modus:"))
        self.view_mode_combo = QComboBox()
        self.view_mode_combo.addItem("Isometrisch", "isometric")
        self.view_mode_combo.addItem("Frei (Maus)", "free")
        self.reset_view_button = QPushButton("Kamera zurücksetzen")
        view_controls.addWidget(self.view_mode_combo)
        view_controls.addWidget(self.reset_view_button)
        view_controls.addStretch(1)
        info_layout.addLayout(view_controls)

        view_hint = QLabel("Im Modus 'Frei (Maus)' mit linker Maustaste in der 3D-Ansicht ziehen.")
        view_hint.setStyleSheet("color: #4b5563;")
        info_layout.addWidget(view_hint)

        self.visualizer = VisualizerPanel()
        visuals_layout.addWidget(info_box)
        visuals_layout.addWidget(self.visualizer, stretch=1)

        root_layout.addWidget(controls)
        root_layout.addWidget(visuals, stretch=1)

        self._create_menu()

        self.calculate_button.clicked.connect(self.calculate_positions)
        self.animate_button.clicked.connect(self.animate_motion)
        self.stop_button.clicked.connect(self.stop_animation)
        self.refresh_ports_button.clicked.connect(self.refresh_serial_ports)
        self.connect_bridge_button.clicked.connect(self.connect_bridge)
        self.disconnect_bridge_button.clicked.connect(self.disconnect_bridge)
        self.send_a_button.clicked.connect(lambda: self.send_position_to_bridge("A"))
        self.send_b_button.clicked.connect(lambda: self.send_position_to_bridge("B"))
        self.deploy_firmware_button.clicked.connect(self.deploy_selected_firmware)
        self.firmware_combo.currentIndexChanged.connect(self._update_firmware_ui)
        self.view_mode_combo.currentIndexChanged.connect(self._change_3d_mode)
        self.reset_view_button.clicked.connect(self.visualizer.reset_3d_camera)

        self.refresh_serial_ports()
        self._update_firmware_ui()
        self._update_bridge_controls()
        self.visualizer.set_3d_mode("isometric")
        initial_config = self.get_config()
        initial_state = JointState(0.0, 20.0, 45.0, 10.0)
        self.visualizer.set_scene(initial_config, initial_state, None, None)

    def _create_esp_dialog(self) -> QDialog:
        dialog = QDialog(self)
        dialog.setWindowTitle("ESP32-Kommunikation")
        dialog.resize(760, 560)

        dialog_layout = QVBoxLayout(dialog)
        bridge_box = QGroupBox("ESP32-Bridge und Firmware")
        bridge_layout = QGridLayout(bridge_box)

        bridge_layout.addWidget(QLabel("Serieller Port"), 0, 0)
        bridge_layout.addWidget(self.port_combo, 0, 1)
        bridge_layout.addWidget(self.refresh_ports_button, 0, 2)
        bridge_layout.addWidget(QLabel("Baudrate"), 1, 0)
        bridge_layout.addWidget(self.baud_combo, 1, 1)
        bridge_layout.addWidget(self.connect_bridge_button, 1, 2)
        bridge_layout.addWidget(self.disconnect_bridge_button, 2, 2)
        bridge_layout.addWidget(self.send_a_button, 2, 0)
        bridge_layout.addWidget(self.send_b_button, 2, 1)
        bridge_layout.addWidget(QLabel("Status"), 3, 0)
        bridge_layout.addWidget(self.bridge_status, 3, 1, 1, 2)
        bridge_layout.addWidget(QLabel("Firmware"), 4, 0)
        bridge_layout.addWidget(self.firmware_combo, 4, 1)
        bridge_layout.addWidget(self.firmware_motor_id, 4, 2)
        bridge_layout.addWidget(self.deploy_firmware_button, 5, 0, 1, 3)
        bridge_layout.addWidget(self.bridge_log, 6, 0, 1, 3)

        dialog_layout.addWidget(bridge_box)
        close_button = QPushButton("Schliessen")
        close_button.clicked.connect(dialog.accept)
        dialog_layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignRight)
        return dialog

    def open_esp_dialog(self) -> None:
        self.refresh_serial_ports()
        self._update_bridge_controls()
        self.esp_dialog.show()
        self.esp_dialog.raise_()
        self.esp_dialog.activateWindow()

    def _runtime_root(self) -> Path:
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            return Path(getattr(sys, "_MEIPASS"))
        return Path(__file__).resolve().parent

    def _firmware_path(self, filename: str) -> Path:
        return self._runtime_root() / "esp32_bridge" / filename

    def _update_firmware_ui(self) -> None:
        is_motor = self.firmware_combo.currentData() == "motor"
        self.firmware_motor_id.setEnabled(is_motor)

    def _build_motor_receiver_temp(self, motor_id: int) -> Path:
        source_path = self._firmware_path("esp32_motor_receiver_micropython.py")
        if not source_path.exists():
            raise FirmwareDeployError(f"Datei nicht gefunden: {source_path}")

        source_text = source_path.read_text(encoding="utf-8")
        old_line = "MOTOR_ID = 1  # 1..4"
        new_line = f"MOTOR_ID = {motor_id}  # 1..4"
        if old_line in source_text:
            modified = source_text.replace(old_line, new_line, 1)
        else:
            modified = source_text

        temp_file = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".py", delete=False)
        try:
            temp_file.write(modified)
            temp_path = Path(temp_file.name)
        finally:
            temp_file.close()
        return temp_path

    def _firmware_source_for_deploy(self) -> tuple[Path, str]:
        firmware_kind = self.firmware_combo.currentData()
        if firmware_kind == "bridge":
            source_path = self._firmware_path("esp32_bridge_micropython.py")
            return source_path, "Bridge"

        try:
            motor_id = int(self.firmware_motor_id.currentText())
        except ValueError as exc:
            raise FirmwareDeployError("Ungueltige Motor-ID fuer Empfaenger-Firmware.") from exc

        temp_path = self._build_motor_receiver_temp(motor_id)
        return temp_path, f"Motor-Empfaenger (ID {motor_id})"

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

    def _copy_main_with_recovery(self, launcher: list[str], port_name: str, source_path: Path) -> None:
        attempts: list[tuple[str, list[str], int]] = [
            ("Direkter Upload", ["connect", port_name, "fs", "cp", str(source_path), ":main.py"], 45),
            ("Recovery: interrupt + soft-reset", ["connect", port_name, "interrupt", "soft-reset", "fs", "cp", str(source_path), ":main.py"], 60),
            ("Recovery: reset + Upload", ["connect", port_name, "reset", "fs", "cp", str(source_path), ":main.py"], 60),
        ]

        last_detail = "Unbekannter Fehler"
        for label, args, timeout in attempts:
            self._append_bridge_log(f"{label}...")
            result = self._run_mpremote(launcher, args, timeout=timeout)
            if result.returncode == 0:
                return
            last_detail = (result.stderr or result.stdout or "Unbekannter Fehler").strip()
            short_detail = last_detail.replace("\n", " ")
            if len(short_detail) > 220:
                short_detail = short_detail[:220] + " ..."
            self._append_bridge_log(f"Fehlversuch: {short_detail}")

        raise FirmwareDeployError(self._friendly_upload_error(last_detail))

    def deploy_selected_firmware(self) -> None:
        if self.serial_bridge.is_connected():
            self._show_error("Bitte zuerst die serielle Bridge-Verbindung trennen.")
            return

        port_name = self.port_combo.currentText().strip()
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

        source_path: Path | None = None
        temp_generated = False
        try:
            source_path, label = self._firmware_source_for_deploy()
            if not source_path.exists():
                raise FirmwareDeployError(f"Firmware-Datei nicht gefunden: {source_path}")
            temp_generated = source_path.name.startswith("tmp") and source_path.suffix == ".py"

            self._append_bridge_log(f"Firmware-Upload gestartet: {label} -> {port_name}")
            self._copy_main_with_recovery(mpremote_launcher, port_name, source_path)

            reset_cmd = [*mpremote_launcher, "connect", port_name, "reset"]
            reset_result = subprocess.run(reset_cmd, capture_output=True, text=True, timeout=20)
            if reset_result.returncode != 0:
                detail = (reset_result.stderr or reset_result.stdout or "Unbekannter Fehler").strip()
                self._append_bridge_log(f"Hinweis: Soft-Reset nicht erfolgreich ({detail})")

            self._append_bridge_log("Firmware erfolgreich als main.py auf ESP32 geschrieben.")
            QMessageBox.information(self, "Roboterarm", "Firmware wurde als main.py auf den ESP32 uebertragen.")
        except (FirmwareDeployError, OSError, subprocess.SubprocessError) as exc:
            self._show_error(str(exc))
        finally:
            if temp_generated and source_path is not None:
                try:
                    source_path.unlink(missing_ok=True)
                except OSError:
                    pass

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
        return RobotConfig(self.base_height.value(), self.link_1.value(), self.link_2.value())

    def calculate_positions(self) -> None:
        self.stop_animation()
        try:
            self.current_config = self.get_config()
            self.start_target_value = self.inputs.start_target()
            self.end_target_value = self.inputs.end_target()
            (
                self.start_state,
                self.end_state,
                self.start_elbow_up,
                self.end_elbow_up,
                self.min_path_shoulder_z,
                self.min_path_elbow_z,
            ) = solve_safe_motion_pair(
                self.start_target_value,
                self.end_target_value,
                self.current_config,
                preferred_elbow_up=self.elbow_up.isChecked(),
                min_middle_joint_z=self.middle_joint_clearance.value(),
            )
        except InverseKinematicsError as exc:
            self._show_error(str(exc))
            return

        self.visualizer.set_scene(self.current_config, self.start_state, self.start_target_value, self.end_target_value)
        self.result_text.setPlainText(self._build_result_text())

    def animate_motion(self) -> None:
        if self.start_state is None or self.end_state is None:
            self.calculate_positions()
            if self.start_state is None or self.end_state is None:
                return

        self.stop_animation()
        self.animation_frames = max(30, int(self.duration.value() * 30))
        self.animation_index = 0
        self.animation_timer.start()

    def stop_animation(self) -> None:
        if self.animation_timer.isActive():
            self.animation_timer.stop()

    def _advance_animation(self) -> None:
        if (
            self.start_state is None
            or self.end_state is None
            or self.current_config is None
            or self.start_target_value is None
            or self.end_target_value is None
        ):
            self.animation_timer.stop()
            return

        factor = self.animation_index / self.animation_frames
        state = interpolate_state(self.start_state, self.end_state, factor)
        self.visualizer.set_scene(self.current_config, state, self.start_target_value, self.end_target_value)

        if self.animation_index >= self.animation_frames:
            self.animation_timer.stop()
            return

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
        self._update_bridge_controls()

    def disconnect_bridge(self) -> None:
        self.serial_bridge.disconnect()
        self.bridge_status.setText("Nicht verbunden")
        self._append_bridge_log("Serielle Verbindung getrennt.")
        self._update_bridge_controls()

    def send_position_to_bridge(self, position_name: str) -> None:
        if self.start_state is None or self.end_state is None:
            self.calculate_positions()
            if self.start_state is None or self.end_state is None:
                return

        if position_name == "A":
            target = self.start_target_value
            state = self.start_state
        else:
            target = self.end_target_value
            state = self.end_state

        if target is None or state is None:
            self._show_error("Es sind noch keine berechneten Positionen vorhanden.")
            return

        payload = build_serial_payload(f"Position {position_name}", target, state, self.duration.value())
        try:
            responses = self.serial_bridge.send_payload(payload)
        except SerialBridgeError as exc:
            self._show_error(str(exc))
            return

        self._append_bridge_log(f"TX Position {position_name}: {json.dumps(payload, ensure_ascii=True)}")
        if responses:
            for response in responses:
                self._append_bridge_log(f"RX: {response}")
        else:
            self._append_bridge_log("Keine Rueckmeldung der Bridge empfangen.")

    def _update_bridge_controls(self) -> None:
        connected = self.serial_bridge.is_connected()
        has_serial = serial is not None
        self.connect_bridge_button.setEnabled(has_serial and not connected)
        self.disconnect_bridge_button.setEnabled(connected)
        self.send_a_button.setEnabled(connected)
        self.send_b_button.setEnabled(connected)
        self.deploy_firmware_button.setEnabled(has_serial and not connected)
        self.firmware_combo.setEnabled(not connected)
        self.firmware_motor_id.setEnabled(not connected and self.firmware_combo.currentData() == "motor")
        self.refresh_ports_button.setEnabled(not connected)
        self.port_combo.setEnabled(not connected)
        self.baud_combo.setEnabled(not connected)
        if not connected and self.bridge_status.text() != "Nicht verbunden":
            self.bridge_status.setText("Nicht verbunden")

    def _build_result_text(self) -> str:
        if (
            self.start_state is None
            or self.end_state is None
            or self.start_target_value is None
            or self.end_target_value is None
        ):
            return ""

        payload_a = build_serial_payload("Position A", self.start_target_value, self.start_state, self.duration.value())
        payload_b = build_serial_payload("Position B", self.end_target_value, self.end_state, self.duration.value())
        start_solution = "eingeklappt" if self.start_elbow_up else "ausgeklappt"
        end_solution = "eingeklappt" if self.end_elbow_up else "ausgeklappt"
        min_shoulder_text = "unbekannt" if self.min_path_shoulder_z is None else f"{self.min_path_shoulder_z:.2f} cm"
        min_elbow_text = "unbekannt" if self.min_path_elbow_z is None else f"{self.min_path_elbow_z:.2f} cm"
        clearance_text = f"{self.middle_joint_clearance.value():.2f} cm"
        return (
            self._format_result("Position A", self.start_target_value, self.start_state)
            + "\n"
            + self._format_result("Position B", self.end_target_value, self.end_state)
            + "\n"
            + self._format_delta(self.start_state, self.end_state)
            + "\n"
            + "Sicherheitspruefung mittlere Gelenke\n"
            + f"Eingestellter Sicherheitsabstand: {clearance_text}\n"
            + f"IK-Loesung A: {start_solution}\n"
            + f"IK-Loesung B: {end_solution}\n"
            + f"Mindesthoehe Schulter entlang A->B: {min_shoulder_text}\n"
            + f"Mindesthoehe Ellbogen entlang A->B: {min_elbow_text}\n\n"
            + "Beispielpaket fuer ESP32-Bridge A\n"
            + json.dumps(payload_a, indent=2, ensure_ascii=True)
            + "\n\n"
            + "Beispielpaket fuer ESP32-Bridge B\n"
            + json.dumps(payload_b, indent=2, ensure_ascii=True)
        )

    def _format_result(self, title: str, target: TargetPoint, state: JointState) -> str:
        return (
            f"{title}\n"
            f"Zielpunkt: x={target.x:6.1f} cm, y={target.y:6.1f} cm, z={target.z:6.1f} cm\n"
            f"Motor 1 Standachse : {state.base_deg:7.2f}°\n"
            f"Motor 2 Arm kippen : {state.shoulder_deg:7.2f}°\n"
            f"Motor 3 Handgelenk : {state.wrist_deg:7.2f}°\n"
            f"Motor 4 Klammer     : {state.gripper_deg:7.2f}°\n"
        )

    def _format_delta(self, start: JointState, end: JointState) -> str:
        return (
            "Bewegung A -> B\n"
            f"Motor 1 Delta: {end.base_deg - start.base_deg:7.2f}°\n"
            f"Motor 2 Delta: {end.shoulder_deg - start.shoulder_deg:7.2f}°\n"
            f"Motor 3 Delta: {end.wrist_deg - start.wrist_deg:7.2f}°\n"
            f"Motor 4 Delta: {end.gripper_deg - start.gripper_deg:7.2f}°\n"
        )

    def _append_bridge_log(self, text: str) -> None:
        self.bridge_log.append(text)

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "Roboterarm", message)


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())