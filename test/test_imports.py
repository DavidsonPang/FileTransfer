"""
简单测试 - 只测试能否导入模块
"""
print("开始测试...")

# 测试 1: 基础库
try:
    import sys
    import os
    import json
    import gzip
    import base64
    print("✓ Python 标准库")
except Exception as e:
    print(f"✗ Python 标准库: {e}")
    exit(1)

# 测试 2: cryptography
try:
    import cryptography
    print("✓ cryptography")
except ImportError:
    print("✗ cryptography 未安装")
    print("  执行: pip install cryptography")
    exit(1)

# 测试 3: tqdm
try:
    from tqdm import tqdm
    print("✓ tqdm")
except ImportError:
    print("✗ tqdm 未安装")
    print("  执行: pip install tqdm")
    exit(1)

# 测试 4: qrcode
try:
    import qrcode
    print("✓ qrcode")
except ImportError:
    print("✗ qrcode 未安装")
    print("  执行: pip install qrcode Pillow")
    exit(1)

# 测试 5: aiortc (最关键的)
try:
    import aiortc
    print(f"✓ aiortc (版本: {aiortc.__version__})")
except ImportError as e:
    print(f"✗ aiortc 未安装或安装失败")
    print(f"  错误: {e}")
    print("\naiortc 需要编译，请确保:")
    print("  Windows: 安装 Visual Studio Build Tools")
    print("  Mac: 安装 Xcode Command Line Tools (xcode-select --install)")
    print("  Linux: sudo apt-get install python3-dev libavformat-dev libavdevice-dev")
    print("\n然后执行: pip install aiortc")
    exit(1)

# 测试 6: 工具函数
try:
    from core.utils import format_size
    print("✓ core.utils")
    print(f"  测试: 1GB = {format_size(1024*1024*1024)}")
except Exception as e:
    print(f"✗ core.utils: {e}")
    exit(1)

print("\n所有依赖检查通过！可以使用程序了。")
