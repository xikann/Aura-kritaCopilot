import os
import sys
import warnings

# 修复 Windows 终端中文乱码：强制 stdout/stderr 使用 UTF-8
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# 屏蔽 Windows 下无关紧要的软链接警告
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# 屏蔽 timm 的 FutureWarning
warnings.filterwarnings("ignore", category=FutureWarning, module=r"timm\..*")

import re
import cv2
import torch
import numpy as np
import base64
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import torchvision.models as models
import torchvision.transforms as transforms

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# 引入 anime-segmentation
anime_seg_dir = os.path.join(BASE_DIR, "anime-segmentation")
if anime_seg_dir not in sys.path:
    sys.path.append(anime_seg_dir)
try:
    from model import ISNetDIS
except ImportError as e:
    print(f"[!] 无法引入 ISNetDIS: {e}")
    ISNetDIS = None

# 声明全局模型变量
cnn_model = None
isnet_model = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global cnn_model, isnet_model
    print(f"[*] 启动 FastAPI 服务，当前计算设备: {device}")
    
    # ---------------------------------------------------------
    # 加载 ISNetDIS 动漫高精度分割模型 (用于铺底色)
    # ---------------------------------------------------------
    print("[*] 正在加载 ISNetDIS 视觉模型用于铺底色...")
    if ISNetDIS is not None:
        try:
            isnet_model = ISNetDIS()
            ckpt_path = os.path.join(BASE_DIR, 'isnetis.ckpt')
            if os.path.exists(ckpt_path):
                checkpoint = torch.load(ckpt_path, map_location='cpu')
                state_dict = checkpoint.get('state_dict', checkpoint)
                clean_state_dict = {k.replace('net.', ''): v for k, v in state_dict.items() if not k.startswith('gt_encoder.')}
                isnet_model.load_state_dict(clean_state_dict, strict=False)
                if device.type == 'cuda':
                    isnet_model.to(device)  # Removed .half() to avoid NaN, let autocast handle it
                    print("[*] ISNetDIS 铺底色模型 (GPU 混合精度) 加载成功")
                else:
                    isnet_model.to(device)
                    print("[*] ISNetDIS 铺底色模型 (CPU FP32) 加载成功")
                isnet_model.eval()
            else:
                print(f"[!] 未找到权重文件 {ckpt_path}")
        except Exception as e:
            print(f"[!] 视觉模型加载失败: {e}")

    # ---------------------------------------------------------
    # 加载图层分类微型 CNN (MobileNetV3)
    # ---------------------------------------------------------
    print("[*] 正在初始化图层分类微型 CNN...")
    cnn_model = models.mobilenet_v3_small(weights=None)
    cnn_model.classifier[3] = torch.nn.Linear(cnn_model.classifier[3].in_features, 3)
    try:
        cnn_ckpt_path = os.path.join(BASE_DIR, 'layer_classifier.pth')
        if os.path.exists(cnn_ckpt_path):
            cnn_model.load_state_dict(torch.load(cnn_ckpt_path, map_location=device))
            print("[*] 成功加载本地图层分类器权重！")
        else:
            print("[!] 未找到 layer_classifier.pth，已创建一个未训练的占位 CNN 网络。")
    except Exception as e:
        print(f"[!] 加载微型 CNN 权重失败: {e}")
    cnn_model.to(device)
    cnn_model.eval()
    
    yield
    
    # 退出时释放资源
    print("[*] 正在释放模型显存...")
    cnn_model = None
    isnet_model = None
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

app = FastAPI(title="AI Copilot Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# CNN 预处理
cnn_transform = transforms.Compose([
    transforms.ToPILImage(),
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
])
cnn_classes = ["Lineart", "FlatColor", "Draft"]

# ---------------------------------------------------------
# 请求模型
# ---------------------------------------------------------
class ChatRequest(BaseModel):
    text: str

class FlatColorRequest(BaseModel):
    image: str
    target_color: str

class LayerRequest(BaseModel):
    image: str

# ---------------------------------------------------------
# 核心辅助函数: 零显存意图解析引擎
# ---------------------------------------------------------
def hex_to_bgr(hex_str: str) -> tuple:
    hex_color = hex_str.lstrip('#')
    if len(hex_color) != 6:
        return (107, 107, 255)
    return (int(hex_color[4:6], 16), int(hex_color[2:4], 16), int(hex_color[0:2], 16))

def parse_intent_local(prompt: str) -> dict:
    """零显存本地意图解析：提取颜色"""
    color_map = {
        "红": "#FF0000", "灰": "#808080", "黑": "#000000", "白": "#FFFFFF", 
        "蓝": "#0000FF", "绿": "#008000", "黄": "#FFFF00", "紫": "#800080",
        "阴影": "#2A002A", "藏青": "#000080", "深棕": "#654321", "金黄": "#FFD700"
    }
    color_hex = "#FF6B6B" # 兜底颜色
    for zh, hex_val in color_map.items():
        if zh in prompt:
            color_hex = hex_val
            break
    return {"action_type": "fill_color", "color_hex": color_hex}

# ---------------------------------------------------------
# API 路由
# ---------------------------------------------------------

@app.post("/api/flat-color")
def flat_color(request: FlatColorRequest):
    """基于 Anime-Segmentation 的高级智能铺底色"""
    try:
        if isnet_model is None:
            return {"status": "error", "message": "底色 AI 模型未加载！"}

        img_bytes = base64.b64decode(request.image)
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_UNCHANGED)
        if img is None:
            return {"status": "error", "message": "图像解码失败"}
            
        b_val, g_val, r_val = hex_to_bgr(request.target_color)
        h, w = img.shape[:2]
        
        # 如果是带有 Alpha 的 RGBA 图像，合并到白色背景转 RGB
        if len(img.shape) == 3 and img.shape[2] == 4:
            alpha = img[:, :, 3]
            rgb = img[:, :, :3]
            white_bg = np.ones_like(rgb) * 255
            alpha_factor = (alpha / 255.0)[:, :, np.newaxis]
            rgb_img_white_bg = (rgb * alpha_factor + white_bg * (1.0 - alpha_factor)).astype(np.uint8)
            rgb_img_model = cv2.cvtColor(rgb_img_white_bg, cv2.COLOR_BGR2RGB)
        else:
            rgb_img_model = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # 准备 ISNetDIS 模型推理的张量数据
        input_size = (1024, 1024)
        resized_img = cv2.resize(rgb_img_model, input_size, interpolation=cv2.INTER_LINEAR)
        img_tensor = torch.from_numpy(resized_img).float() / 255.0
        img_tensor = (img_tensor - 0.5) / 0.5
        img_tensor = img_tensor.permute(2, 0, 1).unsqueeze(0).to(device)
        
        # Removed img_tensor.half() to avoid NaN; autocast expects float32 inputs by default
        
        # Model inference
        with torch.no_grad():
            if device.type == 'cuda':
                with torch.autocast('cuda'):
                    preds = isnet_model(img_tensor)
            else:
                preds = isnet_model(img_tensor)
            mask_tensor = preds[0][0]
            
        # 后处理与渲染
        mask_array = mask_tensor.squeeze().cpu().float().numpy()
        mask_resized = cv2.resize(mask_array, (w, h), interpolation=cv2.INTER_LINEAR)
        
        # 【关键修复】极值归一化：将弱激活（如线稿的极低置信度）放大到 0-1 范围
        max_val = np.max(mask_resized)
        min_val = np.min(mask_resized)
        print(f"[*] AI 预测掩码极值: min={min_val:.4f}, max={max_val:.4f}")
        
        if np.isnan(min_val) or np.isnan(max_val):
            return {"status": "error", "message": "模型计算出现异常 (NaN)，可能是显卡精度溢出，请联系开发者。"}
            
        if max_val > min_val:
            mask_normalized = (mask_resized - min_val) / (max_val - min_val)
        else:
            mask_normalized = mask_resized
            
        # ---------------------------------------------------------
        # 1. 导向滤波边缘吸附 (Guided Filter Snapping)
        # ---------------------------------------------------------
        # 将原图转为灰度并归一化，作为导向图 (Guide Image)
        gray_guide = cv2.cvtColor(rgb_img_model, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
        
        def guided_filter(I, p, r, eps):
            """
            手写的高性能 Guided Filter (导向滤波)
            I: Guide Image (0~1 float32)
            p: Input Probability Map (0~1 float32)
            """
            window = (2 * r + 1, 2 * r + 1)
            mean_I = cv2.boxFilter(I, cv2.CV_32F, window)
            mean_p = cv2.boxFilter(p, cv2.CV_32F, window)
            mean_Ip = cv2.boxFilter(I * p, cv2.CV_32F, window)
            cov_Ip = mean_Ip - mean_I * mean_p

            mean_II = cv2.boxFilter(I * I, cv2.CV_32F, window)
            var_I = mean_II - mean_I * mean_I

            a = cov_Ip / (var_I + eps)
            b = mean_p - a * mean_I

            mean_a = cv2.boxFilter(a, cv2.CV_32F, window)
            mean_b = cv2.boxFilter(b, cv2.CV_32F, window)

            q = mean_a * I + mean_b
            return q
            
        # 应用导向滤波，强行把模型输出的软边拉扯到草稿线的梯度上
        # r=8: 滤波半径，适配相对宽泛的模型边；eps=1e-3: 对边缘敏感度
        filtered_mask = guided_filter(gray_guide, mask_normalized, r=8, eps=1e-3)
        filtered_mask = np.clip(filtered_mask, 0.0, 1.0)

        # ---------------------------------------------------------
        # 2. 高阈值二值化 (Thresholding)
        # ---------------------------------------------------------
        # 提高阈值至 0.7（原为0.3），强力收缩“膨胀一圈”的毛病
        threshold = 0.7
        binary_mask = (filtered_mask > threshold).astype(np.uint8) * 255

        # ---------------------------------------------------------
        # 3. 形态学后处理 (Morphology Opening & Closing)
        # ---------------------------------------------------------
        # 开运算 (Opening)：kernel=3，先腐蚀后膨胀，剃除边缘外凸的锯齿和毛刺
        kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        mask_opened = cv2.morphologyEx(binary_mask, cv2.MORPH_OPEN, kernel_open)
        
        # 闭运算 (Closing)：kernel=5，先膨胀后腐蚀，修补细小断点，尽量保留发丝等细长结构
        kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask_closed = cv2.morphologyEx(mask_opened, cv2.MORPH_CLOSE, kernel_close)
        
        if np.sum(mask_closed) == 0:
            return {"status": "error", "message": "未能提取出有效主体，请调整模型置信度阈值！"}
            
        # 轻微的高斯模糊，让上色边缘有极其自然的羽化过渡，防狗牙
        smoothed_mask = cv2.GaussianBlur(mask_closed, (3, 3), 0)
            
        out_img = np.zeros((h, w, 4), dtype=np.uint8)
        out_img[:, :, 0] = b_val
        out_img[:, :, 1] = g_val
        out_img[:, :, 2] = r_val
        out_img[:, :, 3] = smoothed_mask
        
        _, buffer = cv2.imencode(".png", out_img)
        png_base64 = base64.b64encode(buffer).decode("utf-8")
        
        return {"status": "success", "image": png_base64}
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

@app.post("/api/chat")
def chat(request: ChatRequest):
    """统一聊天入口"""
    prompt = request.text
    print(f"\n[*] 收到聊天指令: '{prompt}'")
    
    if "新建" in prompt or "建个" in prompt:
        target_name = "新建图层"
        match = re.search(r'(名叫|叫|名字是|名字叫)(.*?)(的|新|图层)', prompt)
        if match:
            target_name = match.group(2).strip()
        elif "线稿" in prompt:
            target_name = "线稿"
        return {
            "reply": f"好的，马上为您新建名为 '{target_name}' 的图层。",
            "action": "create_layer",
            "target_name": target_name
        }
    
    if "删" in prompt and any(k in prompt for k in ["空", "杂点", "没用", "多余"]):
        return {
            "reply": "好的，正在为您扫描并清理文档中所有的空图层和极微小杂点图层...",
            "action": "cleanup_layers"
        }
        
    if ("放大" in prompt or "大一点" in prompt) and "笔刷" in prompt:
        return {
            "reply": "收到，正在为您放大笔刷...",
            "action": "resize_brush",
            "direction": "up"
        }
        
    if ("缩小" in prompt or "小一点" in prompt) and "笔刷" in prompt:
        return {
            "reply": "收到，正在为您缩小笔刷...",
            "action": "resize_brush",
            "direction": "down"
        }
    
    if any(w in prompt for w in ["铺底", "底色", "平铺", "铺色"]):
        intent = parse_intent_local(prompt)
        color_hex = intent.get("color_hex", "#FF6B6B")
        return {
            "reply": f"收到！正在为选区提取 AI 剪影并铺底色 ({color_hex})...",
            "action": "flat_color",
            "target_color": color_hex
        }
        
    return {
        "reply": "我目前专注处理绘画指令（如“铺底色”、“新建图层”）。暂不支持闲聊！",
        "action": "none"
    }

@app.post("/api/auto-name-layer")
def auto_name_layer(request: LayerRequest):
    """图层自动命名"""
    try:
        img_bytes = base64.b64decode(request.image)
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return {"status": "error", "message": "图像解码失败"}
            
        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 1, 255, cv2.THRESH_BINARY)
        pts = cv2.findNonZero(thresh)
        if pts is not None:
            x, y, w, h = cv2.boundingRect(pts)
            rgb_img = rgb_img[y:y+h, x:x+w]
            
        input_tensor = cnn_transform(rgb_img).unsqueeze(0).to(device)
        
        with torch.no_grad():
            outputs = cnn_model(input_tensor)
            probabilities = torch.nn.functional.softmax(outputs[0], dim=0)
            best_idx = torch.argmax(probabilities).item()
            best_class = cnn_classes[best_idx]
            confidence = probabilities[best_idx].item()
            
        return {"status": "success", "layer_name": best_class, "confidence": confidence}
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

@app.post("/api/clean-layer")
def clean_layer(request: LayerRequest):
    """空图层查杀与杂点清理"""
    try:
        img_bytes = base64.b64decode(request.image)
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_UNCHANGED)
        if img is None or img.shape[2] != 4:
            return {"status": "error", "message": "图像解码失败或没有Alpha通道"}
            
        alpha = img[:, :, 3]
        if np.sum(alpha) == 0:
            return {"status": "success", "action": "delete_layer", "message": "检测到全空图层，建议直接删除。"}
            
        _, thresh = cv2.threshold(alpha, 1, 255, cv2.THRESH_BINARY)
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(thresh, connectivity=8)
        
        cleaned_alpha = alpha.copy()
        noise_removed = 0
        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            if area < 10:
                cleaned_alpha[labels == i] = 0
                noise_removed += 1
                
        if noise_removed > 0:
            img[:, :, 3] = cleaned_alpha
            _, buffer = cv2.imencode(".png", img)
            png_base64 = base64.b64encode(buffer).decode("utf-8")
            return {"status": "success", "action": "update_layer", "image": png_base64, "message": f"清除了 {noise_removed} 处杂点。"}
            
        return {"status": "success", "action": "none", "message": "图层很干净。"}
        
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
