# Aura Krita AI Copilot

Aura 是一款专为 Krita 设计的 AI 辅助线稿/上色插件，支持通过纯后端的 AI 模型驱动进行极速图像处理。

## 项目特点
- 针对**极其杂乱、断线的二次元单色线稿**做了深度的计算机视觉后处理。
- 完全摒弃了传统依赖闭合连通域的分水岭算法（Watershed）。
- 利用纯数学的**高斯概率矩阵**与**导向滤波（Guided Filter）**吸附，实现完美贴边的主体切割与底色铺设。

## 目录结构
- `ai_copilot/`：Krita 前端交互插件。
- `server.py`：后端算力引擎（依赖 FastAPI 提供接口）。
- `deploy.py`：Krita 插件的一键部署脚本。
- `anime-segmentation/`：核心深度学习图像分割网络实现。

## 模型下载
> **注意**：由于 GitHub 的容量限制，本项目并未包含体积庞大的模型权重文件。你需要自行准备以下模型权重放置于根目录：
> - `isnetis.ckpt`
> - `mobile_sam.pt`

## 协议与致谢 (Acknowledgements)

- 本项目的图像分割网络部分（`anime-segmentation` 目录）基于 [skytnt/anime-segmentation](https://github.com/skytnt/anime-segmentation) 项目的架构。我们完整保留了原项目的协议文件与代码结构，在此向原作者优秀的开源工作表示最诚挚的感谢！
- Krita 是一款卓越的开源数字绘图软件，感谢 Krita 社区提供的强大插件 API 支持。
