"""
基于 WebRTC 的文件接收端
支持 NAT 穿透和直接 P2P 传输
"""
import asyncio
import json
import sys
import os
from aiortc import RTCPeerConnection, RTCConfiguration, RTCIceServer, RTCSessionDescription
from tqdm import tqdm
import qrcode
from core.utils import get_file_hash, format_size, compress_sdp, decompress_sdp


class FileReceiver:
    def __init__(self, output_dir="."):
        self.output_dir = output_dir
        self.pc = None
        self.file_handle = None
        self.metadata = None
        self.received_bytes = 0
        self.pbar = None

    async def create_answer(self, offer_dict):
        """根据 Offer 创建 Answer"""
        # 配置 STUN 服务器
        config = RTCConfiguration([
            RTCIceServer(urls=["stun:stun.l.google.com:19302"]),
            RTCIceServer(urls=["stun:stun1.l.google.com:19302"]),
        ])

        self.pc = RTCPeerConnection(configuration=config)

        # 监听数据通道
        @self.pc.on("datachannel")
        def on_datachannel(channel):
            print("✓ 数据通道已建立")

            @channel.on("message")
            def on_message(message):
                asyncio.create_task(self.handle_message(message))

            @channel.on("close")
            def on_close():
                print("数据通道已关闭")
                if self.file_handle:
                    self.file_handle.close()

            @channel.on("error")
            def on_error(error):
                print(f"✗ 接收错误: {error}")

        # 监听连接状态
        @self.pc.on("connectionstatechange")
        async def on_connectionstatechange():
            print(f"连接状态: {self.pc.connectionState}")
            if self.pc.connectionState == "failed":
                print("✗ 连接失败，可能是 NAT 穿透失败")
                print("建议使用 ZeroTier 或 Tailscale 创建虚拟局域网")
                await self.pc.close()

        # 设置远程描述
        offer = RTCSessionDescription(
            sdp=offer_dict["sdp"],
            type=offer_dict["type"]
        )
        await self.pc.setRemoteDescription(offer)

        # 创建 Answer
        answer = await self.pc.createAnswer()
        await self.pc.setLocalDescription(answer)

        # 等待 ICE 收集完成
        print("正在收集网络信息...")
        await self._wait_for_ice_gathering()

        answer_dict = {
            "type": self.pc.localDescription.type,
            "sdp": self.pc.localDescription.sdp
        }

        return answer_dict

    async def _wait_for_ice_gathering(self):
        """等待 ICE 收集完成"""
        while self.pc.iceGatheringState != "complete":
            await asyncio.sleep(0.1)
        print("✓ 网络信息收集完成")

    async def handle_message(self, message):
        """处理接收到的消息"""
        try:
            if isinstance(message, str):
                # JSON 消息（元数据或控制信息）
                data = json.loads(message)

                if "name" in data:
                    # 文件元数据
                    self.metadata = data
                    output_path = os.path.join(self.output_dir, "received_" + data["name"])

                    print(f"\n文件名: {data['name']}")
                    print(f"大小: {format_size(data['size'])}")
                    print(f"SHA256: {data['hash']}")
                    print(f"保存路径: {output_path}\n")

                    self.file_handle = open(output_path, 'wb')
                    self.pbar = tqdm(total=data['size'], unit='B', unit_scale=True, desc="接收进度")

                elif data.get("type") == "EOF":
                    # 文件传输完成
                    await self.finalize_transfer()

            else:
                # 二进制数据（文件内容）
                if self.file_handle:
                    self.file_handle.write(message)
                    self.received_bytes += len(message)
                    if self.pbar:
                        self.pbar.update(len(message))

        except Exception as e:
            print(f"\n✗ 处理消息时出错: {e}")
            import traceback
            traceback.print_exc()

    async def finalize_transfer(self):
        """完成传输并校验"""
        if self.file_handle:
            self.file_handle.close()
            if self.pbar:
                self.pbar.close()

            print("\n正在校验文件...")
            file_path = self.file_handle.name

            # 校验文件哈希
            received_hash = get_file_hash(file_path)
            expected_hash = self.metadata.get("hash", "")

            if received_hash == expected_hash:
                print(f"✓ 文件接收完成且校验通过！")
                print(f"✓ 文件已保存到: {file_path}")
            else:
                print(f"✗ 校验失败！文件可能损坏")
                print(f"  期望: {expected_hash}")
                print(f"  实际: {received_hash}")

    async def close(self):
        """关闭连接"""
        if self.file_handle:
            self.file_handle.close()
        if self.pc:
            await self.pc.close()


async def main():
    # 解析参数
    output_dir = "."
    if len(sys.argv) > 1 and sys.argv[1] == "--output":
        output_dir = sys.argv[2] if len(sys.argv) > 2 else "."

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    receiver = FileReceiver(output_dir)

    try:
        print("\n" + "="*60)
        print("等待发送端的连接信息...")
        print("="*60)
        print()

        # 接收 Offer
        compressed_offer = input("请输入发送端提供的信息: ").strip()

        try:
            offer_dict = decompress_sdp(compressed_offer)
        except Exception as e:
            print(f"✗ 解析连接信息失败: {e}")
            sys.exit(1)

        # 创建 Answer
        answer_dict = await receiver.create_answer(offer_dict)

        # 压缩并显示 Answer
        compressed_answer = compress_sdp(answer_dict)

        print("\n" + "="*60)
        print("请将以下信息发送给发送端")
        print("="*60)
        print(compressed_answer)
        print("="*60)

        # 生成二维码（可选）
        try:
            qr = qrcode.QRCode(version=1, box_size=3, border=2)
            qr.add_data(compressed_answer)
            qr.make(fit=True)
            print("\n或者让对方扫描以下二维码:")
            qr.print_ascii(invert=True)
        except (ImportError, Exception) as e:
            # 二维码生成失败不影响主要功能
            pass

        print("\n✓ 等待连接建立...\n")

        # 等待接收完成
        await asyncio.sleep(3600)  # 最多等待1小时

    except KeyboardInterrupt:
        print("\n\n用户取消接收")
    except Exception as e:
        print(f"\n✗ 发生错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await receiver.close()


if __name__ == "__main__":
    asyncio.run(main())
