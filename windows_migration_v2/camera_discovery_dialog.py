from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QListWidget, QProgressDialog, QMessageBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject
import socket
import ipaddress

class _RtspPortScanner(QObject):
    update = pyqtSignal(str)
    finished = pyqtSignal(list)

    def __init__(self, subnet_cidr: str, port: int = 554, timeout: float = 0.3, username: str = "", password: str = ""):
        super().__init__()
        self.subnet_cidr = subnet_cidr
        self.port = port
        self.timeout = timeout
        self.username = username
        self.password = password
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        candidates = []
        try:
            net = ipaddress.ip_network(self.subnet_cidr, strict=False)
        except Exception:
            self.finished.emit([])
            return
        for ip in net.hosts():
            if getattr(self, '_cancelled', False):
                break
            host = str(ip)
            self.update.emit(f"Scanning {host}:{self.port}")
            s = socket.socket()
            s.settimeout(self.timeout)
            try:
                s.connect((host, self.port))
                s.close()
                # Build a base RTSP URL; path typically needs to be added by user
                auth = f"{self.username}:{self.password}@" if self.username or self.password else ""
                candidates.append(f"rtsp://{auth}{host}:{self.port}/")
            except Exception:
                try:
                    s.close()
                except Exception:
                    pass
                continue
        self.finished.emit(candidates)


class _OnvifScanner(QObject):
    update = pyqtSignal(str)
    finished = pyqtSignal(list)  # list of dicts: {url, host, profile, width, height, encoding}

    def __init__(self, username: str = "", password: str = ""):
        super().__init__()
        self.username = username
        self.password = password
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        candidates = []
        try:
            from wsdiscovery.discovery import ThreadedWSDiscovery as WSDiscovery
            from onvif import ONVIFCamera
        except Exception as e:
            self.finished.emit([])
            return

        try:
            wsd = WSDiscovery()
            wsd.start()
            services = wsd.searchServices()
            for s in services:
                if getattr(self, '_cancelled', False):
                    break
                xaddrs = s.getXAddrs()
                for x in xaddrs:
                    if getattr(self, '_cancelled', False):
                        break
                    self.update.emit(f"ONVIF: probing {x}")
                    try:
                        # Parse host/port from XAddr (e.g., http://ip:port/onvif/device_service)
                        import urllib.parse as up
                        pu = up.urlparse(x)
                        host = pu.hostname
                        port = pu.port or 80
                        # Connect camera
                        cam = ONVIFCamera(host, port, self.username or '', self.password or '')
                        media = cam.create_media_service()
                        profiles = media.GetProfiles()
                        for p in profiles:
                            try:
                                # Gather details
                                enc = None
                                width = None
                                height = None
                                try:
                                    if hasattr(p, 'VideoEncoderConfiguration') and p.VideoEncoderConfiguration:
                                        vcfg = p.VideoEncoderConfiguration
                                        enc = getattr(vcfg, 'Encoding', None)
                                        if hasattr(vcfg, 'Resolution') and vcfg.Resolution:
                                            width = getattr(vcfg.Resolution, 'Width', None)
                                            height = getattr(vcfg.Resolution, 'Height', None)
                                except Exception:
                                    pass

                                uri = media.GetStreamUri({
                                    'StreamSetup': {
                                        'Stream': 'RTP-Unicast',
                                        'Transport': {'Protocol': 'RTSP'}
                                    },
                                    'ProfileToken': p.token
                                })
                                if uri and getattr(uri, 'Uri', None):
                                    candidates.append({
                                        'url': uri.Uri,
                                        'host': host,
                                        'profile': getattr(p, 'Name', getattr(p, 'token', '')),
                                        'width': width,
                                        'height': height,
                                        'encoding': enc
                                    })
                            except Exception:
                                continue
                    except Exception:
                        continue
            wsd.stop()
        except Exception:
            pass
        # Deduplicate by URL
        uniq = []
        seen = set()
        for c in candidates:
            url = c['url'] if isinstance(c, dict) else c
            if url in seen:
                continue
            seen.add(url)
            uniq.append(c)
        self.finished.emit(uniq)


def _guess_local_cidr(default="192.168.1.0/24"):
    try:
        # Use a UDP connect trick to discover local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        parts = local_ip.split('.')
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
    except Exception:
        pass
    return default

class CameraDiscoveryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_url = None
        self._thread = None
        self._worker = None
        self.initUI()

    def closeEvent(self, event):
        try:
            if self._worker and hasattr(self._worker, 'cancel'):
                self._worker.cancel()
            if self._thread and self._thread.isRunning():
                self._thread.quit()
                self._thread.wait(500)
        except Exception:
            pass
        super().closeEvent(event)

    def initUI(self):
        self.setWindowTitle("Discover IP Cameras (RTSP)")
        self.setMinimumWidth(500)
        layout = QVBoxLayout(self)

        # Subnet
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Subnet (CIDR):"))
        self.subnet_edit = QLineEdit(_guess_local_cidr())
        row1.addWidget(self.subnet_edit)
        layout.addLayout(row1)

        # Auth
        row2 = QHBoxLayout()
        self.user_edit = QLineEdit()
        self.user_edit.setPlaceholderText("username (optional)")
        self.pass_edit = QLineEdit()
        self.pass_edit.setPlaceholderText("password (optional)")
        self.pass_edit.setEchoMode(QLineEdit.Password)
        row2.addWidget(self.user_edit)
        row2.addWidget(self.pass_edit)
        layout.addLayout(row2)

        # Actions
        row3 = QHBoxLayout()
        self.scan_btn = QPushButton("Scan RTSP:554")
        self.scan_btn.clicked.connect(self.start_scan)
        self.onvif_btn = QPushButton("Scan ONVIF")
        self.onvif_btn.clicked.connect(self.start_onvif_scan)
        self.use_btn = QPushButton("Use Selected")
        self.use_btn.clicked.connect(self.use_selected)
        self.use_btn.setEnabled(False)
        row3.addWidget(self.scan_btn)
        row3.addWidget(self.onvif_btn)
        row3.addWidget(self.use_btn)
        layout.addLayout(row3)

        # Results
        self.result_list = QListWidget()
        self.result_list.itemSelectionChanged.connect(lambda: self.use_btn.setEnabled(self.result_list.currentItem() is not None))
        layout.addWidget(self.result_list)

    def start_scan(self):
        subnet = self.subnet_edit.text().strip()
        if not subnet:
            QMessageBox.information(self, "Scan", "Please enter a subnet in CIDR format (e.g., 192.168.1.0/24)")
            return
        self.result_list.clear()
        self.scan_btn.setEnabled(False)
        progress = QProgressDialog("Scanning network...", "Cancel", 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.show()

        self._thread = QThread()
        self._worker = _RtspPortScanner(
            subnet, 554, 0.3, self.user_edit.text().strip(), self.pass_edit.text().strip()
        )
        self._worker.moveToThread(self._thread)
        self._worker.update.connect(lambda msg: self._safe_progress_update(progress, msg))

        def on_finished(candidates):
            self._thread.quit()
            try:
                progress.close()
            except RuntimeError:
                pass
            self.scan_btn.setEnabled(True)
            if not candidates:
                if self.isVisible():
                    try:
                        QMessageBox.information(self, "Scan", "No RTSP candidates found. You may still enter a URL manually.")
                    except RuntimeError:
                        pass
                return
            for url in candidates:
                self.result_list.addItem(url)

        def on_canceled():
            try:
                if self._worker and hasattr(self._worker, 'cancel'):
                    self._worker.cancel()
                self._thread.quit()
            except Exception:
                pass

        progress.canceled.connect(on_canceled)
        self._worker.finished.connect(on_finished)
        self._thread.started.connect(self._worker.run)
        self._thread.start()

    def start_onvif_scan(self):
        self.result_list.clear()
        self.scan_btn.setEnabled(False)
        self.onvif_btn.setEnabled(False)
        progress = QProgressDialog("Scanning ONVIF devices...", "Cancel", 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.show()

        self._thread = QThread()
        self._worker = _OnvifScanner(self.user_edit.text().strip(), self.pass_edit.text().strip())
        self._worker.moveToThread(self._thread)
        self._worker.update.connect(lambda msg: self._safe_progress_update(progress, msg))

        def on_finished(candidates):
            self._thread.quit()
            try:
                progress.close()
            except RuntimeError:
                pass
            self.scan_btn.setEnabled(True)
            self.onvif_btn.setEnabled(True)
            if not candidates:
                if self.isVisible():
                    try:
                        QMessageBox.information(self, "ONVIF Scan", "No ONVIF RTSP URLs found. Try RTSP scan or check credentials.")
                    except RuntimeError:
                        pass
                return
            # Decorate and list
            from PyQt5.QtCore import Qt as _Qt
            from PyQt5.QtWidgets import QListWidgetItem
            user = self.user_edit.text().strip()
            pwd = self.pass_edit.text().strip()
            for entry in candidates:
                if isinstance(entry, dict):
                    url = self._with_auth(entry.get('url', ''), user, pwd)
                    w = entry.get('width')
                    h = entry.get('height')
                    enc = entry.get('encoding') or ''
                    prof = entry.get('profile') or ''
                    host = entry.get('host') or ''
                    label = f"{host} | {enc} {w or ''}x{h or ''} | {prof}\n{url}"
                    item = QListWidgetItem(label)
                    item.setData(_Qt.UserRole, {'url': url, **entry})
                    self.result_list.addItem(item)
                else:
                    item = QListWidgetItem(entry)
                    item.setData(_Qt.UserRole, {'url': entry})
                    self.result_list.addItem(item)

        def on_canceled():
            try:
                if self._worker and hasattr(self._worker, 'cancel'):
                    self._worker.cancel()
                self._thread.quit()
            except Exception:
                pass

        progress.canceled.connect(on_canceled)
        self._worker.finished.connect(on_finished)
        self._thread.started.connect(self._worker.run)
        self._thread.start()

    def use_selected(self):
        item = self.result_list.currentItem()
        if not item:
            return
        # Prefer stored URL in item data
        from PyQt5.QtCore import Qt as _Qt
        data = item.data(_Qt.UserRole)
        if isinstance(data, dict) and 'url' in data:
            self._selected_url = data['url']
        else:
            self._selected_url = item.text()
        self.accept()

    def get_selected_url(self):
        return self._selected_url

    def _safe_progress_update(self, progress, msg):
        """Safely update progress dialog text, ignoring if dialog is deleted"""
        try:
            progress.setLabelText(msg)
        except RuntimeError:
            pass  # Dialog already deleted

    @staticmethod
    def _with_auth(url: str, user: str, pwd: str) -> str:
        if not url:
            return url
        if not user:
            return url
        try:
            import urllib.parse as up
            pu = up.urlparse(url)
            if pu.username:
                return url
            netloc = pu.netloc
            if '@' in netloc:
                return url
            auth = f"{user}:{pwd}@" if pwd else f"{user}@"
            netloc = auth + netloc
            return up.urlunparse((pu.scheme, netloc, pu.path, pu.params, pu.query, pu.fragment))
        except Exception:
            return url
