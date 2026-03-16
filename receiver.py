"""
WebRTC P2P file receiver.
Supports NAT traversal and direct peer-to-peer transfer.
"""

import asyncio
import json
import os
import sys

from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription
from tqdm import tqdm
import qrcode

from core.utils import compress_sdp, decompress_sdp, format_size, get_file_hash


class FileReceiver:
    def __init__(self, output_dir="."):
        self.output_dir = output_dir
        self.pc = None
        self.file_handle = None
        self.metadata = None
        self.received_bytes = 0
        self.pbar = None
        self.channel = None
        self.part_path = None
        self.final_path = None

    async def create_answer(self, offer_dict):
        """Create answer based on offer."""
        config = RTCConfiguration(
            [
                RTCIceServer(urls=["stun:stun.l.google.com:19302"]),
                RTCIceServer(urls=["stun:stun1.l.google.com:19302"]),
            ]
        )

        self.pc = RTCPeerConnection(configuration=config)

        @self.pc.on("datachannel")
        def on_datachannel(channel):
            print("Data channel established.")
            self.channel = channel

            @channel.on("message")
            def on_message(message):
                asyncio.create_task(self.handle_message(message))

            @channel.on("close")
            def on_close():
                print("Data channel closed.")
                if self.file_handle:
                    self.file_handle.close()

            @channel.on("error")
            def on_error(error):
                print(f"Receive error: {error}")

        @self.pc.on("connectionstatechange")
        async def on_connectionstatechange():
            print(f"Connection state: {self.pc.connectionState}")
            if self.pc.connectionState == "failed":
                print("Connection failed, NAT traversal might have failed.")
                print("Try using ZeroTier or Tailscale for virtual LAN testing.")
                await self.pc.close()

        offer = RTCSessionDescription(sdp=offer_dict["sdp"], type=offer_dict["type"])
        await self.pc.setRemoteDescription(offer)

        answer = await self.pc.createAnswer()
        await self.pc.setLocalDescription(answer)

        print("Gathering network info...")
        await self._wait_for_ice_gathering()

        return {
            "type": self.pc.localDescription.type,
            "sdp": self.pc.localDescription.sdp,
        }

    async def _wait_for_ice_gathering(self):
        """Wait for ICE gathering completion."""
        while self.pc.iceGatheringState != "complete":
            await asyncio.sleep(0.1)
        print("Network info ready.")

    async def handle_message(self, message):
        """Handle incoming channel messages."""
        try:
            if isinstance(message, str):
                data = json.loads(message)

                if "name" in data:
                    self.metadata = data
                    self.final_path = os.path.join(self.output_dir, "received_" + data["name"])
                    self.part_path = self.final_path + ".part"

                    print(f"\nFile: {data['name']}")
                    print(f"Size: {format_size(data['size'])}")
                    print(f"SHA256: {data['hash']}")
                    print(f"Save path: {self.final_path}\n")

                    existing_size = 0
                    if os.path.exists(self.part_path):
                        existing_size = os.path.getsize(self.part_path)

                    if existing_size > data["size"]:
                        existing_size = 0
                        with open(self.part_path, "wb"):
                            pass

                    if existing_size > 0:
                        self.file_handle = open(self.part_path, "ab")
                    else:
                        self.file_handle = open(self.part_path, "wb")

                    self.received_bytes = existing_size
                    self.pbar = tqdm(
                        total=data["size"],
                        initial=existing_size,
                        unit="B",
                        unit_scale=True,
                        desc="Receiving",
                    )

                    if self.channel:
                        resume_msg = {
                            "type": "RESUME",
                            "offset": existing_size,
                            "name": data["name"],
                            "size": data["size"],
                            "hash": data["hash"],
                        }
                        self.channel.send(json.dumps(resume_msg))

                elif data.get("type") == "EOF":
                    await self.finalize_transfer()

            else:
                if self.file_handle:
                    self.file_handle.write(message)
                    self.received_bytes += len(message)
                    if self.pbar:
                        self.pbar.update(len(message))

        except Exception as exc:
            print(f"\nError while handling message: {exc}")
            import traceback

            traceback.print_exc()

    async def finalize_transfer(self):
        """Finalize transfer and verify file hash."""
        if not self.file_handle:
            return

        self.file_handle.close()
        if self.pbar:
            self.pbar.close()

        print("\nVerifying file hash...")
        file_path = self.part_path or self.file_handle.name

        received_hash = get_file_hash(file_path)
        expected_hash = self.metadata.get("hash", "")

        if received_hash == expected_hash:
            if self.final_path:
                os.replace(file_path, self.final_path)
                print("File received and verified successfully.")
                print(f"Saved to: {self.final_path}")
            else:
                print("File received and verified successfully.")
                print(f"Saved to: {file_path}")
        else:
            print("Hash verification failed, file may be corrupted.")
            print(f"Expected: {expected_hash}")
            print(f"Actual:   {received_hash}")

    async def close(self):
        """Close local resources and peer connection."""
        if self.file_handle:
            self.file_handle.close()
        if self.pc:
            await self.pc.close()


async def main():
    output_dir = "."
    if len(sys.argv) > 1 and sys.argv[1] == "--output":
        output_dir = sys.argv[2] if len(sys.argv) > 2 else "."

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    receiver = FileReceiver(output_dir)

    try:
        print("\n" + "=" * 60)
        print("Waiting for sender offer...")
        print("=" * 60)
        print()

        compressed_offer = input("Paste offer from sender: ").strip()

        try:
            offer_dict = decompress_sdp(compressed_offer)
        except Exception as exc:
            print(f"Failed to parse offer: {exc}")
            sys.exit(1)

        answer_dict = await receiver.create_answer(offer_dict)
        compressed_answer = compress_sdp(answer_dict)

        print("\n" + "=" * 60)
        print("Send this answer string back to sender.")
        print("=" * 60)
        print(compressed_answer)
        print("=" * 60)

        try:
            qr = qrcode.QRCode(version=1, box_size=3, border=2)
            qr.add_data(compressed_answer)
            qr.make(fit=True)
            print("\nOr let sender scan this QR:")
            qr.print_ascii(invert=True)
        except (ImportError, Exception):
            pass

        print("\nWaiting for connection...\n")
        await asyncio.sleep(3600)

    except KeyboardInterrupt:
        print("\n\nReceive cancelled by user.")
    except Exception as exc:
        print(f"\nUnexpected error: {exc}")
        import traceback

        traceback.print_exc()
    finally:
        await receiver.close()


if __name__ == "__main__":
    asyncio.run(main())
