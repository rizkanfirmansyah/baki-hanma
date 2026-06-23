from __future__ import annotations

from collections import deque

from PyQt6.QtCore import QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget


class TrafficChartCanvas(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._upload_points: deque[float] = deque(maxlen=48)
        self._download_points: deque[float] = deque(maxlen=48)
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def add_sample(self, upload_mbps: float, download_mbps: float) -> None:
        self._upload_points.append(max(upload_mbps, 0.0))
        self._download_points.append(max(download_mbps, 0.0))
        self.update()

    def clear(self) -> None:
        self._upload_points.clear()
        self._download_points.clear()
        self.update()

    def samples(self) -> tuple[list[float], list[float]]:
        return list(self._upload_points), list(self._download_points)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(10, 10, -10, -14)
        painter.fillRect(rect, QColor("#0b1422"))

        grid_pen = QPen(QColor("#1f2937"), 1)
        grid_pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(grid_pen)
        for step in range(1, 4):
            y = rect.top() + rect.height() * step / 4
            painter.drawLine(rect.left(), int(y), rect.right(), int(y))

        if len(self._upload_points) < 2 and len(self._download_points) < 2:
            painter.setPen(QColor("#64748b"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Waiting for network traffic data")
            return

        max_value = max(max(self._upload_points, default=0.0), max(self._download_points, default=0.0), 0.5)
        self._draw_series(
            painter,
            rect,
            list(self._download_points),
            max_value,
            QColor("#22c55e"),
            QColor(34, 197, 94, 50),
        )
        self._draw_series(
            painter,
            rect,
            list(self._upload_points),
            max_value,
            QColor("#38bdf8"),
            QColor(56, 189, 248, 44),
        )

    def _draw_series(
        self,
        painter: QPainter,
        rect,
        points: list[float],
        max_value: float,
        line_color: QColor,
        fill_color: QColor,
    ) -> None:
        if len(points) < 2:
            return

        x_step = rect.width() / max(len(points) - 1, 1)
        coords: list[QPointF] = []
        for index, value in enumerate(points):
            x = rect.left() + index * x_step
            normalized = min(max(value / max_value, 0.0), 1.0)
            y = rect.bottom() - normalized * rect.height()
            coords.append(QPointF(x, y))

        line_path = QPainterPath(coords[0])
        for point in coords[1:]:
            line_path.lineTo(point)

        fill_path = QPainterPath(coords[0])
        for point in coords[1:]:
            fill_path.lineTo(point)
        fill_path.lineTo(rect.right(), rect.bottom())
        fill_path.lineTo(rect.left(), rect.bottom())
        fill_path.closeSubpath()

        painter.fillPath(fill_path, fill_color)
        painter.setPen(QPen(line_color, 2.2))
        painter.drawPath(line_path)


class TrafficMonitorWidget(QFrame):
    interface_changed = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("TrafficCard")
        self._auto_label = "Auto (preferred)"
        self._suppress_interface_signal = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("Traffic Monitor", self)
        title.setObjectName("SectionTitle")
        subtitle = QLabel("Upload / download throughput trend", self)
        subtitle.setObjectName("MutedLabel")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)

        self.interface_combo = QComboBox(self)
        self.interface_combo.setObjectName("InterfaceCombo")
        self.interface_combo.currentTextChanged.connect(self._emit_interface_change)

        title_row.addLayout(title_col, 1)
        title_row.addWidget(self.interface_combo, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        layout.addLayout(title_row)

        self.interface_label = QLabel("Interface: detecting...", self)
        self.interface_label.setObjectName("TrafficMeta")
        layout.addWidget(self.interface_label)

        self.chart = TrafficChartCanvas(self)
        layout.addWidget(self.chart)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)

        self.upload_label = QLabel("Upload: 0 kbps", self)
        self.upload_label.setObjectName("TrafficUpload")
        self.download_label = QLabel("Download: 0 kbps", self)
        self.download_label.setObjectName("TrafficDownload")
        self.trend_label = QLabel("Trend: Stable", self)
        self.trend_label.setObjectName("TrafficTrend")

        stats_row.addWidget(self.upload_label)
        stats_row.addWidget(self.download_label)
        stats_row.addStretch(1)
        stats_row.addWidget(self.trend_label)
        layout.addLayout(stats_row)

        totals_grid = QGridLayout()
        totals_grid.setHorizontalSpacing(12)
        totals_grid.setVerticalSpacing(6)

        self.total_upload_label = QLabel("Total Upload: 0 B", self)
        self.total_upload_label.setObjectName("TrafficMeta")
        self.total_download_label = QLabel("Total Download: 0 B", self)
        self.total_download_label.setObjectName("TrafficMeta")
        self.avg_upload_label = QLabel("Avg Upload: 0 kbps", self)
        self.avg_upload_label.setObjectName("TrafficMeta")
        self.avg_download_label = QLabel("Avg Download: 0 kbps", self)
        self.avg_download_label.setObjectName("TrafficMeta")

        totals_grid.addWidget(self.total_upload_label, 0, 0)
        totals_grid.addWidget(self.total_download_label, 0, 1)
        totals_grid.addWidget(self.avg_upload_label, 1, 0)
        totals_grid.addWidget(self.avg_download_label, 1, 1)
        layout.addLayout(totals_grid)

    def set_interface_choices(self, interfaces: list[str], selected_interface: str | None, auto_label: str | None = None) -> None:
        if auto_label is not None:
            self._auto_label = auto_label
        current_text = self.interface_combo.currentText()
        self._suppress_interface_signal = True
        self.interface_combo.clear()
        self.interface_combo.addItem(self._auto_label)
        for name in interfaces:
            self.interface_combo.addItem(name)

        preferred = selected_interface or current_text or self._auto_label
        index = self.interface_combo.findText(preferred)
        if index < 0:
            index = 0
        self.interface_combo.setCurrentIndex(index)
        self._suppress_interface_signal = False

    def selected_interface(self) -> str | None:
        current = self.interface_combo.currentText().strip()
        if not current or current == self._auto_label:
            return None
        return current

    def update_metrics(
        self,
        upload_mbps: float,
        download_mbps: float,
        interface_name: str | None,
        total_upload_bytes: int,
        total_download_bytes: int,
        average_upload_mbps: float,
        average_download_mbps: float,
    ) -> None:
        self.chart.add_sample(upload_mbps, download_mbps)
        self.interface_label.setText(f"Interface in use: {interface_name or 'Unavailable'}")
        self.upload_label.setText(f"Upload: {self._format_rate(upload_mbps)}")
        self.download_label.setText(f"Download: {self._format_rate(download_mbps)}")
        self.trend_label.setText(f"Trend: {self._compute_trend()}")
        self.total_upload_label.setText(f"Total Upload: {self._format_bytes(total_upload_bytes)}")
        self.total_download_label.setText(f"Total Download: {self._format_bytes(total_download_bytes)}")
        self.avg_upload_label.setText(f"Avg Upload: {self._format_rate(average_upload_mbps)}")
        self.avg_download_label.setText(f"Avg Download: {self._format_rate(average_download_mbps)}")

    def reset_metrics(self, interface_name: str | None = None) -> None:
        self.chart.clear()
        self.interface_label.setText(f"Interface in use: {interface_name or 'Unavailable'}")
        self.upload_label.setText("Upload: 0 kbps")
        self.download_label.setText("Download: 0 kbps")
        self.trend_label.setText("Trend: Stable")
        self.total_upload_label.setText("Total Upload: 0 B")
        self.total_download_label.setText("Total Download: 0 B")
        self.avg_upload_label.setText("Avg Upload: 0 kbps")
        self.avg_download_label.setText("Avg Download: 0 kbps")

    def _emit_interface_change(self, text: str) -> None:
        if self._suppress_interface_signal:
            return
        if text == self._auto_label:
            self.interface_changed.emit("")
        else:
            self.interface_changed.emit(text)

    def _compute_trend(self) -> str:
        upload_points, download_points = self.chart.samples()
        combined = [u + d for u, d in zip(upload_points, download_points)]
        if len(combined) < 8:
            return "Stable"
        recent = sum(combined[-4:]) / 4
        previous = sum(combined[-8:-4]) / 4
        delta = recent - previous
        if abs(delta) < 0.15:
            return "Stable"
        if delta > 0:
            return "Rising"
        return "Falling"

    @staticmethod
    def _format_rate(value_mbps: float) -> str:
        if value_mbps >= 1.0:
            return f"{value_mbps:.2f} Mbps"
        return f"{value_mbps * 1000:.0f} kbps"

    @staticmethod
    def _format_bytes(value_bytes: int) -> str:
        value = float(max(value_bytes, 0))
        units = ["B", "KB", "MB", "GB", "TB"]
        unit = units[0]
        for unit in units:
            if value < 1024 or unit == units[-1]:
                break
            value /= 1024
        if unit in {"B", "KB"}:
            return f"{value:.0f} {unit}"
        return f"{value:.2f} {unit}"
