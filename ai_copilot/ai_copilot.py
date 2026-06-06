from krita import Extension, Krita, DockWidgetFactory, DockWidgetFactoryBase
from .docker import AICopilotDocker

class AICopilotExtension(Extension):
    def __init__(self, parent):
        super().__init__(parent)

    def setup(self):
        # 注册停靠窗口（Docker）工厂，默认放在右侧停靠区
        Krita.instance().addDockWidgetFactory(
            DockWidgetFactory(
                "ai_copilot_docker",
                DockWidgetFactoryBase.DockRight,
                AICopilotDocker
            )
        )

    def createActions(self, window):
        pass
