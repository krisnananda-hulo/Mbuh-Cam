import time
import cv2
import numpy as np
from PIL import ImageGrab
from PyQt5.QtCore import QThread, pyqtSignal
import pyvirtualcam

try:
    from pygrabber.dshow_graph import FilterGraph
    HAS_PYGRABBER = True
except ImportError:
    HAS_PYGRABBER = False


def get_available_cameras():
    camera_list = [("Layar Utama (Screen)", "screen", None)]

    if HAS_PYGRABBER:
        try:
            graph = FilterGraph()
            devices = graph.get_input_devices()
            for index, name in enumerate(devices):
                if "Unity" not in name:
                    camera_list.append((f"{name} (Index {index})", "cam", index))
            if len(camera_list) > 1:
                return camera_list
        except Exception:
            pass

    for index in range(8):
        try:
            cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
            if cap.isOpened():
                ret, frame = cap.read()
                cap.release()
                if ret:
                    camera_list.append((f"Kamera {index}", "cam", index))
        except Exception:
            pass
                
    return camera_list


class CameraStreamWorker(QThread):
    frame_fetched = pyqtSignal(np.ndarray)
    status_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.running = True
        self.source_type = "screen"
        self.cam_index = None
        self.cap = None
        
        self.use_snapshot_mode = False
        self.bg_frame = None
        
        # Transisi Opacity Simetris
        self.alpha = 0.0          # 0.0 = Full Live Cam, 1.0 = Full BG Kosong
        self.target_alpha = 0.0
        self.fade_speed = 0.1     # Kecepatan transisi identik bolak-balik

    def release_capture(self):
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None

    def set_source(self, source_type, cam_index=None):
        self.source_type = source_type
        self.cam_index = cam_index
        self.release_capture()

        if self.source_type == "cam" and self.cam_index is not None:
            try:
                self.cap = cv2.VideoCapture(self.cam_index, cv2.CAP_DSHOW)
                if self.cap.isOpened():
                    self.status_changed.emit(f"Input: Camera Index {self.cam_index}")
                else:
                    self.status_changed.emit("Kamera Ditolak / Diberhentikan Sistem!")
            except Exception:
                self.status_changed.emit("Gagal Mengakses Kamera!")
        else:
            self.status_changed.emit("Input: Layar Utama (Screen)")

    def set_override_frame(self, frame, enable=True):
        self.bg_frame = frame
        self.use_snapshot_mode = enable
        
        # Mengatur target alpha secara simetris
        if enable:
            self.target_alpha = 1.0
            self.status_changed.emit("Beralih ke Background Kosong...")
        else:
            self.target_alpha = 0.0
            self.status_changed.emit("Kembali ke Live Feed...")

    def run(self):
        target_w, target_h = 1280, 720
        vcam = None
        
        output_backends = ['unityvideo', None]

        for backend in output_backends:
            try:
                vcam = pyvirtualcam.Camera(
                    width=target_w, 
                    height=target_h, 
                    fps=30, 
                    fmt=pyvirtualcam.PixelFormat.RGBA, 
                    backend=backend
                )
                break
            except Exception:
                try:
                    vcam = pyvirtualcam.Camera(
                        width=target_w, 
                        height=target_h, 
                        fps=30, 
                        fmt=pyvirtualcam.PixelFormat.RGB, 
                        backend=backend
                    )
                    break
                except Exception:
                    continue

        if vcam is None:
            self.status_changed.emit("Virtual Cam Driver Gagal Dibuka!")
            return

        self.status_changed.emit(f"Active: {vcam.device} ({target_w}x{target_h})")

        while self.running:
            live_frame = None

            # 1. Pembacaan konstan live camera
            if self.source_type == "cam":
                if self.cap is not None and self.cap.isOpened():
                    try:
                        ret, live_frame = self.cap.read()
                        if not ret or live_frame is None:
                            live_frame = None
                    except Exception:
                        live_frame = None
            elif self.source_type == "screen":
                try:
                    img_pil = ImageGrab.grab()
                    live_frame = np.array(img_pil)
                    live_frame = cv2.cvtColor(live_frame, cv2.COLOR_RGB2BGR)
                except Exception:
                    live_frame = None

            if live_frame is not None:
                h, w = live_frame.shape[:2]
                if w != target_w or h != target_h:
                    live_frame = cv2.resize(live_frame, (target_w, target_h), interpolation=cv2.INTER_AREA)

                # 2. Update progres transisi cepat & simetris di kedua arah
                if self.alpha < self.target_alpha:
                    self.alpha = min(self.alpha + self.fade_speed, 1.0)
                elif self.alpha > self.target_alpha:
                    self.alpha = max(self.alpha - self.fade_speed, 0.0)

                # 3. Blending persentase antara BG Kosong dan Live Cam
                if self.bg_frame is not None:
                    bg_resized = self.bg_frame
                    if bg_resized.shape[:2] != (target_h, target_w):
                        bg_resized = cv2.resize(self.bg_frame, (target_w, target_h), interpolation=cv2.INTER_AREA)
                    
                    weight_bg = self.alpha
                    weight_cam = 1.0 - weight_bg
                    final_frame = cv2.addWeighted(bg_resized, weight_bg, live_frame, weight_cam, 0)
                else:
                    final_frame = live_frame

                # 4. Kirim frame ke Virtual Camera Driver
                try:
                    if vcam.fmt == pyvirtualcam.PixelFormat.RGBA:
                        send_frame = cv2.cvtColor(final_frame, cv2.COLOR_BGR2RGBA)
                    elif vcam.fmt == pyvirtualcam.PixelFormat.RGB:
                        send_frame = cv2.cvtColor(final_frame, cv2.COLOR_BGR2RGB)
                    else:
                        send_frame = final_frame

                    vcam.send(send_frame)
                    vcam.sleep_until_next_frame()

                    # Kirim stream ke GUI preview
                    self.frame_fetched.emit(live_frame)
                except Exception:
                    pass
            else:
                time.sleep(0.03)

        if vcam is not None:
            try:
                vcam.close()
            except Exception:
                pass

    def stop(self):
        self.running = False
        self.release_capture()
        self.wait()