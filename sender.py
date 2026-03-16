"""
WebRTC P2P file sender.
Supports NAT traversal and direct peer-to-peer transfer.
"""

import asyncio
import json
import os
import sys

from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection
from tqdm import tqdm
import qrcode

from core.utils import compress_sdp, decompress_sdp, format_size, get_file_hash


class FileSender:
    def __init__(self, file_path):
        self.file_path = file_path
        self.pc = None
        self.channel = None
        self.file_size = os.path.getsize(file_path)
        self.file_name = os.path.basename(file_path)
        self.chunk_size = 64000  # Recommended DataChannel chunk size.
        self.file_hash = None
        self.resume_offset = 0
        self.resume_event = asyncio.Event()
        self.transfer_started = False

    async def create_offer(self):
        """Create offer and wait for ICE gathering to complete."""
        config = RTCConfiguration(
            [
                RTCIceServer(urls=["stun:stun.l.google.com:19302"]),
                RTCIceServer(urls=["stun:stun1.l.google.com:19302"]),
            ]
        )

        self.pc = RTCPeerConnection(configuration=config)

        # Reliable data channel.
        self.channel = self.pc.createDataChannel("file_transfer")

        @self.channel.on("open")
        async def on_open():
            print("Connection established, start transfer.")
            await self.send_file()

        @self.channel.on("close")
        def on_close():
            print("Connection closed.")

        @self.channel.on("error")
        def on_error(error):
            print(f"Transfer error: {error}")

        @self.channel.on("message")
        def on_message(message):
            if isinstance(message, str):
                self._handle_control_message(message)

        @self.pc.on("connectionstatechange")
        async def on_connectionstatechange():
            print(f"Connection state: {self.pc.connectionState}")
            if self.pc.connectionState == "failed":
                print("Connection failed, NAT traversal might have failed.")
                print("Try using ZeroTier or Tailscale for virtual LAN testing.")
                await self.pc.close()

        offer = await self.pc.createOffer()
        await self.pc.setLocalDescription(offer)

        print("Gathering network info...")
        await self._wait_for_ice_gathering()

        return {
            "type": self.pc.localDescription.type,
            "sdp": self.pc.localDescription.sdp,
        }

    def _handle_control_message(self, message):
        try:
            data = json.loads(message)
        except Exception:
            return

        if data.get("type") != "RESUME":
            return

        if self.transfer_started:
            return

        expected_name = data.get("name")
        expected_size = data.get("size")
        expected_hash = data.get("hash")
        offset = data.get("offset", 0)

        if (
            expected_name != self.file_name
            or expected_size != self.file_size
            or expected_hash != self.file_hash
        ):
            self.resume_offset = 0
            self.resume_event.set()
            return

        if not isinstance(offset, int) or offset < 0 or offset > self.file_size:
            self.resume_offset = 0
            self.resume_event.set()
            return

        self.resume_offset = offset
        self.resume_event.set()

    async def _wait_for_ice_gathering(self):
        """Wait for ICE gathering completion."""
        while self.pc.iceGatheringState != "complete":
            await asyncio.sleep(0.1)
        print("Network info ready.")

    async def set_answer(self, answer_dict):
        """Set remote answer."""
        from aiortc import RTCSessionDescription

        answer = RTCSessionDescription(sdp=answer_dict["sdp"], type=answer_dict["type"])
        await self.pc.setRemoteDescription(answer)
        print("Answer received, waiting for data channel to open...")

    async def send_file(self):
        """Send file over data channel."""
        try:
            print("Calculating file hash...")
            self.file_hash = get_file_hash(self.file_path)

            metadata = {
                "name": self.file_name,
                "size": self.file_size,
                "hash": self.file_hash,
                "algorithm": "sha256",
            }
            self.channel.send(json.dumps(metadata))

            print(f"\nFile: {self.file_name}")
            print(f"Size: {format_size(self.file_size)}")
            print(f"SHA256: {self.file_hash}\n")

            # Wait for optional RESUME request from receiver.
            try:
                await asyncio.wait_for(self.resume_event.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                pass

            with open(self.file_path, "rb") as file_obj:
                if self.resume_offset >= self.file_size:
                    self.transfer_started = True
                    self.channel.send(json.dumps({"type": "EOF"}))
                    print("\nFile already complete on receiver, no resend needed.")
                    return

                if self.resume_offset > 0:
                    file_obj.seek(self.resume_offset)
                    print(f"Resume from {format_size(self.resume_offset)}")

                self.transfer_started = True
                with tqdm(
                    total=self.file_size,
                    initial=self.resume_offset,
                    unit="B",
                    unit_scale=True,
                    desc="Sending",
                ) as pbar:
                    while True:
                        chunk = file_obj.read(self.chunk_size)
                        if not chunk:
                            break

                        self.channel.send(chunk)
                        pbar.update(len(chunk))

                        # Basic backpressure control.
                        while self.channel.bufferedAmount > self.chunk_size * 4:
                            await asyncio.sleep(0.01)

            self.channel.send(json.dumps({"type": "EOF"}))
            print("\nTransfer complete.")

        except Exception as exc:
            print(f"\nTransfer failed: {exc}")
            raise

    async def close(self):
        """Close peer connection."""
        if self.pc:
            await self.pc.close()


async def main():
    if len(sys.argv) < 2:
        print("Usage: python sender.py <file_path>")
        sys.exit(1)

    file_path = sys.argv[1]

    if not os.path.exists(file_path):
        print(f"File does not exist: {file_path}")
        sys.exit(1)

    if os.path.isdir(file_path):
        print("Directory transfer is not supported. Pack it as zip first.")
        sys.exit(1)

    sender = FileSender(file_path)

    try:
        offer_dict = await sender.create_offer()
        compressed_offer = compress_sdp(offer_dict)

        print("\n" + "=" * 60)
        print("Send this offer string to the receiver.")
        print("=" * 60)
        print(compressed_offer)
        print("=" * 60)

        try:
            qr = qrcode.QRCode(version=1, box_size=3, border=2)
            qr.add_data(compressed_offer)
            qr.make(fit=True)
            print("\nOr let receiver scan this QR:")
            qr.print_ascii(invert=True)
        except (ImportError, Exception):
            pass

        print()
        compressed_answer = input("Paste answer from receiver: ").strip()

        try:
            answer_dict = decompress_sdp(compressed_answer)
            await sender.set_answer(answer_dict)
        except Exception as exc:
            print(f"Failed to parse answer: {exc}")
            sys.exit(1)

        await asyncio.sleep(3600)

    except KeyboardInterrupt:
        print("\n\nTransfer cancelled by user.")
    except Exception as exc:
        print(f"\nUnexpected error: {exc}")
        import traceback

        traceback.print_exc()
    finally:
        await sender.close()


if __name__ == "__main__":
    asyncio.run(main())
