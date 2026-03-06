"""
基本功能测试脚本
不需要实际建立 WebRTC 连接，只测试核心逻辑
"""
import sys
import os

print("="*60)
print("FileTransfer 基础功能测试")
print("="*60)

# 测试 1: 导入检查
print("\n[测试 1] 检查依赖导入...")
try:
    import cryptography
    print("  ✓ cryptography")
except ImportError as e:
    print(f"  ✗ cryptography: {e}")
    sys.exit(1)

try:
    import tqdm
    print("  ✓ tqdm")
except ImportError as e:
    print(f"  ✗ tqdm: {e}")
    sys.exit(1)

try:
    import qrcode
    print("  ✓ qrcode")
except ImportError as e:
    print(f"  ✗ qrcode: {e}")
    sys.exit(1)

try:
    import aiortc
    print(f"  ✓ aiortc (版本: {aiortc.__version__})")
except ImportError as e:
    print(f"  ✗ aiortc: {e}")
    print("\n提示: aiortc 安装可能需要编译，请确保已安装:")
    print("  - Windows: Visual C++ Build Tools")
    print("  - Mac: Xcode Command Line Tools")
    print("  - Linux: python3-dev, libavformat-dev, libavdevice-dev")
    sys.exit(1)

# 测试 2: 工具函数
print("\n[测试 2] 测试工具函数...")
try:
    from core.utils import get_file_hash, format_size, compress_sdp, decompress_sdp
    print("  ✓ 工具函数导入成功")

    # 创建测试文件
    test_file = "test_temp.txt"
    with open(test_file, "w") as f:
        f.write("Hello FileTransfer!")

    # 测试哈希
    hash_val = get_file_hash(test_file)
    print(f"  ✓ 文件哈希: {hash_val[:16]}...")

    # 测试大小格式化
    size_str = format_size(1234567890)
    print(f"  ✓ 格式化大小: {size_str}")

    # 测试压缩/解压
    test_data = {"type": "offer", "sdp": "v=0\r\no=test 123456 2 IN IP4 127.0.0.1\r\n"}
    compressed = compress_sdp(test_data)
    decompressed = decompress_sdp(compressed)
    assert decompressed == test_data
    print(f"  ✓ SDP 压缩/解压缩正常")
    print(f"    原始长度: {len(str(test_data))} → 压缩后: {len(compressed)} (压缩率: {(1-len(compressed)/len(str(test_data)))*100:.1f}%)")

    # 清理
    os.remove(test_file)

except Exception as e:
    print(f"  ✗ 错误: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 测试 3: 类结构检查
print("\n[测试 3] 检查发送端和接收端类...")
try:
    # 检查发送端
    with open("sender.py", "r", encoding="utf-8") as f:
        sender_code = f.read()
        assert "class FileSender" in sender_code
        assert "create_offer" in sender_code
        assert "send_file" in sender_code
        print("  ✓ FileSender 类结构正常")

    # 检查接收端
    with open("receiver.py", "r", encoding="utf-8") as f:
        receiver_code = f.read()
        assert "class FileReceiver" in receiver_code
        assert "create_answer" in receiver_code
        assert "handle_message" in receiver_code
        print("  ✓ FileReceiver 类结构正常")

except Exception as e:
    print(f"  ✗ 错误: {e}")
    sys.exit(1)

# 测试 4: WebRTC 基础测试
print("\n[测试 4] WebRTC 基础功能测试...")
try:
    from aiortc import RTCPeerConnection, RTCConfiguration, RTCIceServer

    # 创建配置
    config = RTCConfiguration([
        RTCIceServer(urls=["stun:stun.l.google.com:19302"])
    ])

    # 创建 PeerConnection
    pc = RTCPeerConnection(configuration=config)
    print(f"  ✓ RTCPeerConnection 创建成功")
    print(f"  ✓ 连接状态: {pc.connectionState}")
    print(f"  ✓ ICE 收集状态: {pc.iceGatheringState}")

    # 清理
    import asyncio
    async def cleanup():
        await pc.close()
    asyncio.run(cleanup())
    print(f"  ✓ RTCPeerConnection 关闭成功")

except Exception as e:
    print(f"  ✗ 错误: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "="*60)
print("✓ 所有基础测试通过！")
print("="*60)
print("\n提示: 要测试完整的文件传输功能，需要:")
print("  1. 在一台机器上运行: python receiver.py")
print("  2. 在另一台机器上运行: python sender.py <文件>")
print("  3. 按照提示交换连接信息")
print("\n如果在同一台机器测试，也可以:")
print("  1. 打开两个终端窗口")
print("  2. 分别运行接收端和发送端")
print("  3. 手动复制粘贴连接信息")
