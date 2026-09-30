"""Erzeugt das App-Logo (PNG, ICO, ICNS) aus reinem Qt-Zeichencode.

Aufruf: python3 scripts/make_logo.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath, QPen

ASSETS = Path(__file__).resolve().parent.parent / "assets"
SIZE = 1024


def draw_logo(painter: QPainter, size: int = SIZE) -> None:
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(size / 1024, size / 1024)

    # Hintergrund: abgerundetes Quadrat mit Farbverlauf
    background = QPainterPath()
    background.addRoundedRect(QRectF(40, 40, 944, 944), 220, 220)
    gradient = QLinearGradient(0, 0, 1024, 1024)
    gradient.setColorAt(0.0, QColor("#14b8a6"))
    gradient.setColorAt(1.0, QColor("#0f4c5c"))
    painter.fillPath(background, QBrush(gradient))

    # dezenter Glanz oben
    painter.save()
    painter.setClipPath(background)
    shine = QLinearGradient(0, 40, 0, 520)
    shine.setColorAt(0.0, QColor(255, 255, 255, 60))
    shine.setColorAt(1.0, QColor(255, 255, 255, 0))
    painter.fillRect(QRectF(0, 0, 1024, 560), QBrush(shine))
    painter.restore()

    white = QColor("#ffffff")
    accent = QColor("#fbbf24")

    base = QPointF(330, 800)
    shoulder = QPointF(330, 600)
    elbow = QPointF(520, 330)
    tool = QPointF(780, 400)

    # Sockel
    pedestal = QPainterPath()
    pedestal.addRoundedRect(QRectF(190, 790, 280, 90), 40, 40)
    painter.fillPath(pedestal, white)
    column = QPainterPath()
    column.addRoundedRect(QRectF(285, 590, 90, 220), 30, 30)
    painter.fillPath(column, QColor(255, 255, 255, 235))

    # Armsegmente
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(white, 76, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.drawLine(shoulder, elbow)
    painter.drawLine(elbow, tool)

    # Gelenke
    for point, radius in ((shoulder, 64), (elbow, 64)):
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#0f4c5c"))
        painter.drawEllipse(point, radius, radius)
        painter.setBrush(accent)
        painter.drawEllipse(point, radius - 26, radius - 26)

    # Greifer (zwei Backen am Werkzeugpunkt)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(accent, 42, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    hub = QPointF(775, 405)
    painter.drawLine(hub, QPointF(885, 335))
    painter.drawLine(hub, QPointF(885, 475))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(accent)
    painter.drawEllipse(hub, 40, 40)


def render(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    draw_logo(painter, size)
    painter.end()
    return image


def main() -> int:
    app = QGuiApplication(sys.argv)
    del app
    ASSETS.mkdir(exist_ok=True)

    render(1024).save(str(ASSETS / "logo.png"))
    render(256).save(str(ASSETS / "icon.ico"))

    if sys.platform == "darwin" and shutil.which("iconutil"):
        iconset = ASSETS / "icon.iconset"
        iconset.mkdir(exist_ok=True)
        for base in (16, 32, 128, 256, 512):
            render(base).save(str(iconset / f"icon_{base}x{base}.png"))
            render(base * 2).save(str(iconset / f"icon_{base}x{base}@2x.png"))
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(ASSETS / "icon.icns")], check=True)
        shutil.rmtree(iconset)

    print(f"Logo geschrieben nach {ASSETS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
