import sys
import cv2
from PyQt5.QtCore import Qt, QPoint, QTimer
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QSlider, QSizePolicy, QSizeGrip
)
from PyQt5.QtGui import QImage, QPixmap

from streamer import CameraStreamWorker, get_available_cameras


class MbuhFloatingApp(QWidget):
    def __init__(self):
        super().__init__()
        self.old_pos = None
        self.timer = QTimer()
        self.countdown_val = 3
        self.latest_frame = None
        self.snapshot_frame = None
        self.snapshot_pixmap = None
        self.is_snapshot_active = False
        self.cameras = []

        self.worker = CameraStreamWorker()
        self.worker.frame_fetched.connect(self.update_live_frame)
        self.worker.status_changed.connect(self.update_status_label)
        self.worker.start()

        self.initUI()

    def initUI(self):
        self.setWindowTitle("Mbuh Virtual Cam")
        self.setWindowFlags(
            Qt.FramelessWindowHint | 
            Qt.WindowStaysOnTopHint | 
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.setMinimumSize(220, 430)
        self.resize(260, 480)

        self.setStyleSheet("""
            QWidget {
                background-color: rgba(24, 24, 37, 230);
                border-radius: 12px;
                color: #cdd6f4;
                font-family: Arial, sans-serif;
            }
            QLabel {
                font-size: 11px;
                font-weight: bold;
            }
            QComboBox {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 4px;
            }
            QPushButton {
                background-color: #89b4fa;
                color: #11111b;
                border: none;
                padding: 6px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #b4befe;
            }
            QPushButton#changeBtn {
                background-color: #cba6f7;
                color: #11111b;
            }
            QPushButton#changeBtn:hover {
                background-color: #f5c2e7;
            }
            QPushButton#timerBtn {
                background-color: #a6e3a1;
            }
            QPushButton#timerBtn:hover {
                background-color: #94e2d5;
            }
            QPushButton#closeBtn {
                background-color: #f38ba8;
                color: #ffffff;
            }
            QPushButton#closeBtn:hover {
                background-color: #eba0ac;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #313244;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #89b4fa;
                width: 14px;
                margin-top: -4px;
                margin-bottom: -4px;
                border-radius: 7px;
            }
            QSlider::sub-page:horizontal {
                background: #89b4fa;
                border-radius: 3px;
            }
            QSizeGrip {
                width: 16px;
                height: 16px;
                background-color: transparent;
            }
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Header Title
        title = QLabel("MBUH")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Dropdown Choice Input Source
        lbl_input = QLabel("Pilih Source Input:")
        layout.addWidget(lbl_input)

        self.input_source = QComboBox()
        self.refresh_camera_list()
        self.input_source.currentIndexChanged.connect(self.on_source_changed)
        layout.addWidget(self.input_source)

        # Status Bar Virtual Cam
        self.lbl_vcam_status = QLabel("Mencari Stream Virtual Cam...")
        self.lbl_vcam_status.setStyleSheet("font-size: 10px; color: #a6e3a1;")
        self.lbl_vcam_status.setWordWrap(True)
        self.lbl_vcam_status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_vcam_status)

        # Tombol Beralih ke Background Kosong
        self.btn_change = QPushButton("Hilangkan Tampilan")
        self.btn_change.setObjectName("changeBtn")
        self.btn_change.clicked.connect(self.toggle_snapshot_output)
        layout.addWidget(self.btn_change)

        # Box Pratinjau Snapshot BG Kosong
        self.lbl_preview = QLabel("Preview BG Kosong")
        self.lbl_preview.setAlignment(Qt.AlignCenter)
        self.lbl_preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.lbl_preview.setMinimumHeight(100)
        self.lbl_preview.setStyleSheet("""
            background-color: #1e1e2e; 
            border: 1px dashed #45475a; 
            border-radius: 8px;
            font-size: 11px;
            color: #bac2de;
        """)
        layout.addWidget(self.lbl_preview)

        # Tombol Ambil BG Kosong (3s)
        self.btn_timer_photo = QPushButton("Ambil BG Kosong (3s)")
        self.btn_timer_photo.setObjectName("timerBtn")
        self.btn_timer_photo.clicked.connect(self.start_timer_photo)
        layout.addWidget(self.btn_timer_photo)

        # BAR SETTING OPACITY WINDOW
        opacity_layout = QHBoxLayout()
        opacity_layout.setContentsMargins(0, 4, 0, 4)
        
        self.lbl_opacity = QLabel("Opacity: 90%")
        opacity_layout.addWidget(self.lbl_opacity)

        self.slider_opacity = QSlider(Qt.Horizontal)
        self.slider_opacity.setRange(20, 100)
        self.slider_opacity.setValue(90)
        self.slider_opacity.valueChanged.connect(self.change_opacity)
        opacity_layout.addWidget(self.slider_opacity)

        layout.addLayout(opacity_layout)

        # Baris Bawah: Tombol Tutup + Size Grip
        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        
        btn_close = QPushButton("Tutup")
        btn_close.setObjectName("closeBtn")
        btn_close.clicked.connect(self.close)
        bottom_layout.addWidget(btn_close)

        sizegrip = QSizeGrip(self)
        bottom_layout.addWidget(sizegrip, 0, Qt.AlignBottom | Qt.AlignRight)

        layout.addLayout(bottom_layout)

        self.setLayout(layout)
        self.setWindowOpacity(0.9)

        if self.cameras:
            self.on_source_changed(0)

    def toggle_snapshot_output(self):
        if not self.is_snapshot_active:
            if self.snapshot_frame is not None:
                self.is_snapshot_active = True
                self.worker.set_override_frame(self.snapshot_frame, True)
                self.btn_change.setText("Tampilkan Kembali")
                self.btn_change.setStyleSheet("""
                    QPushButton#changeBtn {
                        background-color: #fab387;
                        color: #11111b;
                    }
                    QPushButton#changeBtn:hover {
                        background-color: #f9e2af;
                    }
                """)
            else:
                self.update_status_label("Ambil BG Kosong Dulu!")
        else:
            self.is_snapshot_active = False
            self.worker.set_override_frame(None, False)
            self.btn_change.setText("Hilangkan Tampilan")
            self.btn_change.setStyleSheet("""
                QPushButton#changeBtn {
                    background-color: #cba6f7;
                    color: #11111b;
                }
                QPushButton#changeBtn:hover {
                    background-color: #f5c2e7;
                }
            """)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.snapshot_pixmap is not None:
            scaled = self.snapshot_pixmap.scaled(
                self.lbl_preview.width(), 
                self.lbl_preview.height(), 
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            )
            self.lbl_preview.setPixmap(scaled)

    def change_opacity(self, value):
        opacity = value / 100.0
        self.setWindowOpacity(opacity)
        self.lbl_opacity.setText(f"Opacity: {value}%")

    def refresh_camera_list(self):
        self.cameras = get_available_cameras()
        self.input_source.clear()
        for label, stype, idx in self.cameras:
            self.input_source.addItem(label)

    def update_live_frame(self, frame):
        self.latest_frame = frame

    def update_status_label(self, message):
        self.lbl_vcam_status.setText(message)

    def on_source_changed(self, index):
        if 0 <= index < len(self.cameras):
            _, stype, idx = self.cameras[index]
            if self.is_snapshot_active:
                self.toggle_snapshot_output()
            self.worker.set_source(stype, idx)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.old_pos = event.globalPos()

    def mouseMoveEvent(self, event):
        if self.old_pos is not None:
            delta = QPoint(event.globalPos() - self.old_pos)
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPos()

    def mouseReleaseEvent(self, event):
        self.old_pos = None

    def take_snapshot(self):
        if self.latest_frame is not None:
            self.snapshot_frame = self.latest_frame.copy()

            rgb_image = cv2.cvtColor(self.latest_frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_image.shape
            bytes_per_line = ch * w
            q_img = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
            self.snapshot_pixmap = QPixmap.fromImage(q_img)
            
            scaled = self.snapshot_pixmap.scaled(
                self.lbl_preview.width(), 
                self.lbl_preview.height(), 
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            )
            self.lbl_preview.setPixmap(scaled)

            if self.is_snapshot_active:
                self.worker.set_override_frame(self.snapshot_frame, True)

    def start_timer_photo(self):
        self.countdown_val = 3
        self.btn_timer_photo.setEnabled(False)
        self.btn_timer_photo.setText(f"Proses... ({self.countdown_val}s)")
        
        self.timer.timeout.connect(self.update_countdown)
        self.timer.start(1000)

    def update_countdown(self):
        self.countdown_val -= 1
        if self.countdown_val > 0:
            self.btn_timer_photo.setText(f"Proses... ({self.countdown_val}s)")
        else:
            self.timer.stop()
            self.timer.timeout.disconnect(self.update_countdown)
            self.btn_timer_photo.setText("Ambil BG Kosong (3s)")
            self.btn_timer_photo.setEnabled(True)
            self.take_snapshot()

    def closeEvent(self, event):
        self.worker.stop()
        self.latest_frame = None
        self.snapshot_frame = None
        QApplication.quit()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    mbuh_app = MbuhFloatingApp()
    mbuh_app.show()
    sys.exit(app.exec_())