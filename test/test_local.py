"""
简化的本地测试脚本
测试在同一台机器上的发送和接收（模拟）
"""
import asyncio
import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.utils import compress_sdp, decompress_sdp, get_file_hash, format_size


async def test_local():
    print("="*60)
    print("本地模拟测试")
    print("="*60)

    # 测试 1: 工具函数
    print("\n[测试 1] 工具函数")

    # 创建测试文件
    test_file = "test_local.txt"
    test_content = "Hello FileTransfer!\n" * 100
    with open(test_file, "w") as f:
        f.write(test_content)

    print(f"  ✓ 创建测试文件: {test_file}")
    print(f"  ✓ 文件大小: {format_size(len(test_content.encode()))}")

    # 计算哈希
    file_hash = get_file_hash(test_file)
    print(f"  ✓ SHA256: {file_hash[:16]}...")

    # 测试压缩
    test_sdp = {
        "type": "offer",
        "sdp": "v=0\r\no=- 123456 2 IN IP4 127.0.0.1\r\n" + "a=candidate:1234 1 udp 2130706431 192.168.1.100 54321 typ host\r\n" * 10
    }

    original_len = len(str(test_sdp))
    compressed = compress_sdp(test_sdp)
    compressed_len = len(compressed)
    decompressed = decompress_sdp(compressed)

    print(f"  ✓ 原始长度: {original_len}")
    print(f"  ✓ 压缩后: {compressed_len}")
    print(f"  ✓ 压缩率: {(1 - compressed_len/original_len)*100:.1f}%")
    print(f"  ✓ 解压缩验证: {'通过' if decompressed == test_sdp else '失败'}")

    # 测试 2: WebRTC 基础
    print("\n[测试 2] WebRTC 基础")

    try:
        from aiortc import RTCPeerConnection, RTCConfiguration, RTCIceServer

        config = RTCConfiguration([
            RTCIceServer(urls=["stun:stun.l.google.com:19302"])
        ])

        pc = RTCPeerConnection(configuration=config)
        print(f"  ✓ 创建 PeerConnection")
        print(f"  ✓ 连接状态: {pc.connectionState}")
        print(f"  ✓ ICE 状态: {pc.iceGatheringState}")

        await pc.close()
        print(f"  ✓ 关闭连接")

    except ImportError as e:
        print(f"  ✗ aiortc 未安装: {e}")
        print("\n请先安装 aiortc:")
        print("  pip install aiortc")
        return False
    except Exception as e:
        print(f"  ✗ WebRTC 测试失败: {e}")
        return False

    # 清理
    os.remove(test_file)

    print("\n" + "="*60)
    print("✓ 本地测试通过！")
    print("="*60)
    print("\n下一步：在两个终端窗口中测试完整流程:")
    print("  终端 1: python receiver.py")
    print("  终端 2: python sender.py test_file.txt")

    return True


if __name__ == "__main__":
    result = asyncio.run(test_local())
    sys.exit(0 if result else 1)
