"""
基于 WebRTC 的文件发送端
支持 NAT 穿透和直接 P2P 传输
"""
import asyncio
import os
import json
import sys
from aiortc import RTCPeerConnection, RTCConfiguration, RTCIceServer
from tqdm import tqdm
import qrcode
from core.utils import get_file_hash, format_size, compress_sdp, decompress_sdp


class FileSender:
    def __init__(self, file_path):
        self.file_path = file_path
        self.pc = None
        self.channel = None
        self.file_size = os.path.getsize(file_path)
        self.file_name = os.path.basename(file_path)
        self.chunk_size = 64000  # WebRTC DataChannel 推荐大小

    async def create_offer(self):
        """创建 Offer 并等待 ICE 收集完成"""
        # 配置 STUN 服务器（使用 Google 的免费服务）
        config = RTCConfiguration([
            RTCIceServer(urls=["stun:stun.l.google.com:19302"]),
            RTCIceServer(urls=["stun:stun1.l.google.com:19302"]),
        ])

        self.pc = RTCPeerConnection(configuration=config)

        # 创建数据通道（可靠传输模式）
        self.channel = self.pc.createDataChannel("file_transfer")

        # 设置数据通道事件
        @self.channel.on("open")
        async def on_open():
            print(f"✓ 连接已建立，开始传输...")
            await self.send_file()

        @self.channel.on("close")
        def on_close():
            print("连接已关闭")

        @self.channel.on("error")
        def on_error(error):
            print(f"✗ 传输错误: {error}")

        # 监听连接状态
        @self.pc.on("connectionstatechange")
        async def on_connectionstatechange():
            print(f"连接状态: {self.pc.connectionState}")
            if self.pc.connectionState == "failed":
                print("✗ 连接失败，可能是 NAT 穿透失败")
                print("建议使用 ZeroTier 或 Tailscale 创建虚拟局域网")
                await self.pc.close()

        # 创建 Offer
        offer = await self.pc.createOffer()
        await self.pc.setLocalDescription(offer)

        # 等待 ICE 收集完成（重要！）
        print("正在收集网络信息...")
        await self._wait_for_ice_gathering()

        # 生成包含完整 ICE candidates 的 SDP
        offer_dict = {
            "type": self.pc.localDescription.type,
            "sdp": self.pc.localDescription.sdp
        }

        return offer_dict

    async def _wait_for_ice_gathering(self):
        """等待 ICE 收集完成"""
        # 等待 ICE gathering 状态变为 complete
        while self.pc.iceGatheringState != "complete":
            await asyncio.sleep(0.1)
        print("✓ 网络信息收集完成")

    async def set_answer(self, answer_dict):
        """设置 Answer"""
        from aiortc import RTCSessionDescription
        answer = RTCSessionDescription(
            sdp=answer_dict["sdp"],
            type=answer_dict["type"]
        )
        await self.pc.setRemoteDescription(answer)
        print("✓ 已接收对方响应，等待连接建立...")

    async def send_file(self):
        """发送文件"""
        try:
            # 计算文件哈希
            print(f"正在计算文件校验和...")
            file_hash = get_file_hash(self.file_path)

            # 发送文件元数据
            metadata = {
                "name": self.file_name,
                "size": self.file_size,
                "hash": file_hash,
                "algorithm": "sha256"
            }
            self.channel.send(json.dumps(metadata))
            print(f"\n文件名: {self.file_name}")
            print(f"大小: {format_size(self.file_size)}")
            print(f"SHA256: {file_hash}\n")

            # 等待接收端确认
            await asyncio.sleep(0.5)

            # 发送文件数据
            with open(self.file_path, 'rb') as f:
                with tqdm(total=self.file_size, unit='B', unit_scale=True, desc="发送进度") as pbar:
                    while True:
                        chunk = f.read(self.chunk_size)
                        if not chunk:
                            break

                        # 发送数据块
                        self.channel.send(chunk)
                        pbar.update(len(chunk))

                        # 简单的流控：等待缓冲区不要太满
                        while self.channel.bufferedAmount > self.chunk_size * 4:
                            await asyncio.sleep(0.01)

            # 发送结束标记
            self.channel.send(json.dumps({"type": "EOF"}))
            print("\n✓ 文件传输完成！")

        except Exception as e:
            print(f"\n✗ 传输失败: {e}")
            raise

    async def close(self):
        """关闭连接"""
        if self.pc:
            await self.pc.close()


async def main():
    if len(sys.argv) < 2:
        print("用法: python sender.py <文件路径>")
        sys.exit(1)

    file_path = sys.argv[1]

    if not os.path.exists(file_path):
        print(f"✗ 文件不存在: {file_path}")
        sys.exit(1)

    if os.path.isdir(file_path):
        print("✗ 暂不支持文件夹传输，请先打包成 zip")
        sys.exit(1)

    sender = FileSender(file_path)

    try:
        # 创建 Offer
        offer_dict = await sender.create_offer()

        # 压缩并显示 Offer
        compressed_offer = compress_sdp(offer_dict)

        print("\n" + "="*60)
        print("请将以下信息发送给接收端（可以通过微信、QQ 等方式）")
        print("="*60)
        print(compressed_offer)
        print("="*60)

        # 生成二维码（可选）
        try:
            qr = qrcode.QRCode(version=1, box_size=3, border=2)
            qr.add_data(compressed_offer)
            qr.make(fit=True)
            print("\n或者扫描以下二维码:")
            qr.print_ascii(invert=True)
        except (ImportError, Exception) as e:
            # 二维码生成失败不影响主要功能
            pass

        print("\n")

        # 等待接收端的 Answer
        compressed_answer = input("请输入接收端返回的信息: ").strip()

        try:
            answer_dict = decompress_sdp(compressed_answer)
            await sender.set_answer(answer_dict)
        except Exception as e:
            print(f"✗ 解析响应失败: {e}")
            sys.exit(1)

        # 等待传输完成（使用事件机制会更好，这里简化处理）
        await asyncio.sleep(3600)  # 最多等待1小时

    except KeyboardInterrupt:
        print("\n\n用户取消传输")
    except Exception as e:
        print(f"\n✗ 发生错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await sender.close()


if __name__ == "__main__":
    asyncio.run(main())
