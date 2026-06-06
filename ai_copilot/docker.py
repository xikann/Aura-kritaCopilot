import json
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTextBrowser, QLineEdit, QPushButton, QLabel
from PyQt5.QtCore import Qt, QUrl, QByteArray, QBuffer, QIODevice
from PyQt5.QtGui import QImage
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply, QNetworkProxy
from krita import DockWidget

class AICopilotDocker(DockWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Copilot")
        
        # 主 Widget
        self.main_widget = QWidget(self)
        self.setWidget(self.main_widget)
        
        # 布局
        self.layout = QVBoxLayout(self.main_widget)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(8)
        
        # 顶部标题栏
        self.header = QLabel("AI Copilot", self.main_widget)
        self.header.setStyleSheet("font-weight: bold; font-size: 13px; color: #89b4fa;")
        self.layout.addWidget(self.header)
        
        # 聊天历史显示框
        self.chat_history = QTextBrowser(self.main_widget)
        self.chat_history.setReadOnly(True)
        self.chat_history.setStyleSheet("""
            QTextBrowser {
                background-color: #1e1e2e;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                font-family: 'Segoe UI', 'Microsoft YaHei';
                font-size: 12px;
                padding: 6px;
            }
        """)
        self.layout.addWidget(self.chat_history)
        
        # 底部输入框与发送按钮
        self.input_layout = QHBoxLayout()
        self.input_layout.setSpacing(6)
        
        self.input_box = QLineEdit(self.main_widget)
        self.input_box.setPlaceholderText("输入指令（铺底色、新建图层等）...")
        self.input_box.setStyleSheet("""
            QLineEdit {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 4px;
                padding: 6px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1px solid #89b4fa;
            }
        """)
        self.input_layout.addWidget(self.input_box)
        
        self.send_button = QPushButton("发送", self.main_widget)
        self.send_button.setStyleSheet("""
            QPushButton {
                background-color: #89b4fa;
                color: #11111b;
                font-weight: bold;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #b4befe;
            }
            QPushButton:pressed {
                background-color: #74c7ec;
            }
        """)
        self.input_layout.addWidget(self.send_button)
        
        self.layout.addLayout(self.input_layout)
        
        # 信号绑定
        self.send_button.clicked.connect(self.send_message)
        self.input_box.returnPressed.connect(self.send_message)
        
        # 异步网络请求管理器 (强制不走系统代理)
        self.network_manager = QNetworkAccessManager(self)
        self.network_manager.setProxy(QNetworkProxy(QNetworkProxy.NoProxy))
        self.network_manager.finished.connect(self.on_network_reply)
        
        # 记录最近选区的局部坐标
        self.last_selection_coords = None
        
        self.append_message("AI", "AI Copilot 已就绪。输入指令即可（铺底色、新建图层等）")

    def canvasChanged(self, canvas):
        pass

    def append_message(self, sender, text):
        html_text = text.replace('\n', '<br>')
        if sender == "我":
            msg_html = '<p align="right" style="margin: 4px 0;"><font color="#89b4fa"><b>我：</b></font><font color="#cdd6f4">{}</font></p>'.format(html_text)
        elif sender == "AI":
            msg_html = '<p align="left" style="margin: 4px 0;"><font color="#a6e3a1"><b>AI：</b></font><font color="#cdd6f4">{}</font></p>'.format(html_text)
        else:
            msg_html = '<p align="center" style="margin: 4px 0;"><font color="#f38ba8"><i>[ {} ]</i></font></p>'.format(html_text)
        self.chat_history.append(msg_html)

    def send_message(self):
        text = self.input_box.text().strip()
        if not text:
            return
        
        self.append_message("我", text)
        self.input_box.clear()
        
        url = QUrl("http://127.0.0.1:8000/api/chat")
        request = QNetworkRequest(url)
        request.setHeader(QNetworkRequest.ContentTypeHeader, "application/json")
        
        data = {"text": text}
        json_bytes = json.dumps(data).encode("utf-8")
        self.network_manager.post(request, QByteArray(json_bytes))

    def on_network_reply(self, reply):
        req_path = reply.url().path()
        error = reply.error()
        
        if "/api/flat-color" in req_path:
            if error == QNetworkReply.NoError:
                try:
                    response_bytes = reply.readAll()
                    response_str = str(response_bytes, "utf-8")
                    response_json = json.loads(response_str)
                    if response_json.get("status") == "success":
                        base64_img = response_json.get("image")
                        self.apply_flat_color_to_krita(base64_img)
                    else:
                        self.append_message("系统", "铺底色失败: {}".format(response_json.get('message')))
                except Exception as e:
                    self.append_message("系统", "解析铺底色响应失败: {}".format(str(e)))
            else:
                self.append_message("系统", "铺底色请求失败 ({})".format(reply.errorString()))
        else:
            # 统一聊天入口：解析后端返回的 action 并自动调度
            if error == QNetworkReply.NoError:
                try:
                    response_bytes = reply.readAll()
                    response_str = str(response_bytes, "utf-8")
                    response_json = json.loads(response_str)
                    reply_text = response_json.get("reply", "")
                    self.append_message("AI", reply_text)
                    
                    action = response_json.get("action")
                    if action == "create_layer":
                        target_name = response_json.get("target_name", "新建图层")
                        self.execute_create_layer(target_name)
                    elif action == "flat_color":
                        target_color = response_json.get("target_color", "#FF6B6B")
                        self.flat_color_selection(target_color)
                except Exception as e:
                    self.append_message("系统", "解析响应失败: {}".format(str(e)))
            else:
                self.append_message("系统", "连接后端失败 ({})，请确保 server.py 已启动".format(reply.errorString()))
        
        reply.deleteLater()

    def execute_create_layer(self, target_name):
        try:
            from krita import Krita
            doc = Krita.instance().activeDocument()
            if not doc:
                self.append_message("系统", "创建失败：未找到活跃的图像文档。")
                return
            
            new_layer = doc.createNode(target_name, "paintlayer")
            current_node = doc.activeNode()
            if current_node:
                parent = current_node.parentNode()
                parent.addChildNode(new_layer, current_node)
            else:
                doc.rootNode().addChildNode(new_layer, None)
            
            doc.refreshProjection()
            self.append_message("AI", "已新建图层: '{}'".format(target_name))
        except Exception as e:
            self.append_message("系统", "新建图层失败: {}".format(str(e)))

    def flat_color_selection(self, target_color="#FF6B6B"):
        try:
            from krita import Krita
            doc = Krita.instance().activeDocument()
            if not doc:
                self.append_message("系统", "铺底色失败：未找到活跃文档，请先打开画布！")
                return
            
            selection = doc.selection()
            if not selection:
                self.append_message("系统", "请先用选区工具框选要铺色的区域！")
                return
                
            x = selection.x()
            y = selection.y()
            w = selection.width()
            h = selection.height()
            
            if w <= 0 or h <= 0:
                self.append_message("系统", "选区无效（宽或高为0）")
                return
                
            node = doc.activeNode()
            if not node:
                self.append_message("系统", "没有选中活跃图层")
                return
                
            pixel_data = doc.pixelData(x, y, w, h)
            self._current_pixel_bytes = pixel_data.data()  # Keep a reference to prevent GC
            image = QImage(self._current_pixel_bytes, w, h, QImage.Format_RGBA8888)
            
            ba = QByteArray()
            buffer = QBuffer(ba)
            buffer.open(QIODevice.WriteOnly)
            image.save(buffer, "PNG")
            base64_data = ba.toBase64().data().decode("utf-8")
            
            self.last_selection_coords = (x, y, w, h)
            self.append_message("系统", "正在上传选区 ({}x{}) 进行铺色...".format(w, h))
            
            url = QUrl("http://127.0.0.1:8000/api/flat-color")
            request = QNetworkRequest(url)
            request.setHeader(QNetworkRequest.ContentTypeHeader, "application/json")
            
            data = {
                "image": base64_data,
                "target_color": target_color
            }
            json_bytes = json.dumps(data).encode("utf-8")
            self.network_manager.post(request, QByteArray(json_bytes))
            
        except Exception as e:
            self.append_message("系统", "铺底色发送失败: {}".format(str(e)))

    def apply_flat_color_to_krita(self, base64_img):
        try:
            from krita import Krita
            doc = Krita.instance().activeDocument()
            if not doc or not self.last_selection_coords:
                self.append_message("系统", "写回失败：文档已关闭或丢失选区。")
                return
                
            x, y, w, h = self.last_selection_coords
            
            img_bytes = QByteArray.fromBase64(base64_img.encode("utf-8"))
            image = QImage()
            image.loadFromData(img_bytes, "PNG")
            
            image = image.convertToFormat(QImage.Format_RGBA8888)
            raw_bits = image.constBits()
            raw_bits.setsize(w * h * 4)
            pixel_bytes = QByteArray(raw_bits.asstring())
            
            flat_layer = doc.createNode("Flatting", "paintlayer")
            
            current_node = doc.activeNode()
            if current_node:
                parent = current_node.parentNode()
                siblings = parent.childNodes()
                try:
                    idx = siblings.index(current_node)
                    if idx > 0:
                        parent.addChildNode(flat_layer, siblings[idx - 1])
                    else:
                        parent.addChildNode(flat_layer, None)
                except ValueError:
                    parent.addChildNode(flat_layer, None)
            else:
                doc.rootNode().addChildNode(flat_layer, None)
                
            flat_layer.setPixelData(pixel_bytes, x, y, w, h)
            doc.refreshProjection()
            self.append_message("AI", "铺底色完成！已在线稿层下方创建 Flatting 图层。")
            
        except Exception as e:
            self.append_message("系统", "铺底色写回失败: {}".format(str(e)))
