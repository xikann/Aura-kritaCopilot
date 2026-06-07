import json
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTextBrowser, QLineEdit, QPushButton, QLabel
from PyQt5.QtCore import Qt, QUrl, QByteArray, QBuffer, QIODevice
from PyQt5.QtGui import QImage
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply, QNetworkProxy
from krita import DockWidget

class AICopilotDocker(DockWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Aura Copilot")
        
        # 主 Widget
        self.main_widget = QWidget(self)
        self.setWidget(self.main_widget)
        
        # 布局
        self.layout = QVBoxLayout(self.main_widget)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(8)
        
        # 顶部标题栏
        self.header = QLabel("Aura Copilot", self.main_widget)
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
        
        self.append_message("Aura", "Aura Copilot 已就绪。输入指令即可（铺底色、清理图层等）")

    def canvasChanged(self, canvas):
        pass

    def append_message(self, sender, text):
        html_text = text.replace('\n', '<br>')
        if sender == "我":
            msg_html = '<p align="right" style="margin: 4px 0;"><font color="#89b4fa"><b>我：</b></font><font color="#cdd6f4">{}</font></p>'.format(html_text)
        elif sender == "Aura":
            msg_html = '<p align="left" style="margin: 4px 0;"><font color="#a6e3a1"><b>Aura：</b></font><font color="#cdd6f4">{}</font></p>'.format(html_text)
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
                    self.append_message("Aura", reply_text)
                    
                    action = response_json.get("action")
                    if action == "create_layer":
                        target_name = response_json.get("target_name", "新建图层")
                        self.execute_create_layer(target_name)
                    elif action == "cleanup_layers":
                        self.execute_cleanup_layers()
                    elif action == "resize_brush":
                        direction = response_json.get("direction", "up")
                        self.execute_resize_brush(direction)
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
            self.append_message("Aura", "已新建图层: '{}'".format(target_name))
        except Exception as e:
            self.append_message("系统", "新建图层失败: {}".format(str(e)))

    def execute_cleanup_layers(self):
        try:
            from krita import Krita
            doc = Krita.instance().activeDocument()
            if not doc:
                self.append_message("系统", "执行失败：未找到活跃文档。")
                return
                
            def remove_noise(node):
                removed_count = 0
                stray_count = 0
                children = node.childNodes()[:] # 拷贝一份列表以安全删除
                for child in children:
                    if child.locked():
                        continue
                        
                    if child.type() == "paintlayer":
                        bounds = child.bounds()
                        if bounds.isEmpty() or bounds.width() == 0 or bounds.height() == 0:
                            node.removeChildNode(child)
                            removed_count += 1
                        else:
                            # 读取边框内所有像素
                            data = child.pixelData(bounds.x(), bounds.y(), bounds.width(), bounds.height())
                            b = data.data()
                            # 提取所有 alpha 通道字节（索引3开始，步长为4）
                            alphas = b[3::4]
                            # 在 Python 3 中，使用 count 统计空字节数极其快，相当于底层的 C 循环
                            num_transparent = alphas.count(0)
                            num_visible = len(alphas) - num_transparent
                            
                            # 如果总可见像素小于20，判定为误触杂点层
                            if num_visible < 20:
                                node.removeChildNode(child)
                                stray_count += 1
                                
                    elif child.type() == "grouplayer":
                        res = remove_noise(child)
                        removed_count += res[0]
                        stray_count += res[1]
                return removed_count, stray_count
                
            removed_empty, removed_stray = remove_noise(doc.rootNode())
            doc.refreshProjection()
            if removed_empty > 0 or removed_stray > 0:
                self.append_message("Aura", f"清理完毕！共删除 {removed_empty} 个全空图层，以及 {removed_stray} 个仅含微小杂点的多余图层。")
            else:
                self.append_message("Aura", "扫描完毕，当前文档中非常干净，没有空图层或杂点图层哦。")
        except Exception as e:
            self.append_message("系统", "清理图层失败: {}".format(str(e)))

    def execute_resize_brush(self, direction):
        try:
            from krita import Krita
            action_name = 'increase_brush_size' if direction == 'up' else 'decrease_brush_size'
            action = Krita.instance().action(action_name)
            if action:
                # 循环触发几次，因为单击一次调整幅度较小
                for _ in range(10):
                    action.trigger()
                self.append_message("Aura", f"已帮您{'放大' if direction == 'up' else '缩小'}笔刷！")
            else:
                # 尝试备用动作名
                fallback_name = 'KritaToolSizeIncrease' if direction == 'up' else 'KritaToolSizeDecrease'
                fallback_action = Krita.instance().action(fallback_name)
                if fallback_action:
                    for _ in range(10):
                        fallback_action.trigger()
                    self.append_message("Aura", f"已帮您{'放大' if direction == 'up' else '缩小'}笔刷！")
                else:
                    self.append_message("系统", "找不到笔刷调整动作指令，可能是 Krita 版本差异或快捷键未绑定。")
        except Exception as e:
            self.append_message("系统", "调整笔刷失败: {}".format(str(e)))

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
            self.append_message("Aura", "铺底色完成！已在线稿层下方创建 Flatting 图层。")
            
        except Exception as e:
            self.append_message("系统", "铺底色写回失败: {}".format(str(e)))
