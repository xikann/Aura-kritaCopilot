import os
import shutil
import sys

def deploy():
    # 获取 Windows 系统下的 APPDATA 路径
    appdata = os.environ.get("APPDATA")
    if not appdata:
        print("错误：找不到 APPDATA 环境变量。请确保在 Windows 环境下运行。")
        sys.exit(1)
        
    pykrita_path = os.path.join(appdata, "krita", "pykrita")
    print(f"Krita 插件目标安装路径: {pykrita_path}")
    
    # 如果 pykrita 目录不存在则创建
    if not os.path.exists(pykrita_path):
        os.makedirs(pykrita_path)
        print(f"已创建 Krita 插件专属文件夹: {pykrita_path}")
        
    # 拷贝 .desktop 配置文件
    src_desktop = "ai_copilot.desktop"
    dst_desktop = os.path.join(pykrita_path, "ai_copilot.desktop")
    shutil.copy2(src_desktop, dst_desktop)
    print(f"成功部署配置文件: {src_desktop} -> {dst_desktop}")
    
    # 拷贝 ai_copilot Python 包
    src_folder = "ai_copilot"
    dst_folder = os.path.join(pykrita_path, "ai_copilot")
    if os.path.exists(dst_folder):
        shutil.rmtree(dst_folder)
        print(f"清理了旧版本的插件包文件夹: {dst_folder}")
    shutil.copytree(src_folder, dst_folder)
    print(f"成功部署插件代码包: {src_folder} -> {dst_folder}")
    
    print("\n=======================================================")
    print("【部署完成】")
    print("激活步骤提示:")
    print("1. 打开 Krita，点击菜单栏 [设置] -> [配置 Krita] (Configure Krita)。")
    print("2. 选择 [Python 插件管理器] (Python Plugin Manager)，勾选 [AI Copilot]。")
    print("3. 重启 Krita 以加载该插件。")
    print("4. 重启后，点击菜单栏 [设置] -> [面板] (Dockers)，勾选 [AI Copilot] 即可显示控制台！")
    print("=======================================================")

if __name__ == "__main__":
    deploy()
