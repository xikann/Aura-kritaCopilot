from krita import Krita
from .ai_copilot import AICopilotExtension

# 向 Krita 实例注册插件扩展
Krita.instance().addExtension(AICopilotExtension(Krita.instance()))
