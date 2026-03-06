"""
工具函数模块
"""
import os
import hashlib
import json
import base64
import gzip


def get_file_hash(file_path, algorithm='sha256'):
    """计算文件哈希值"""
    h = hashlib.new(algorithm)
    with open(file_path, 'rb') as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def format_size(bytes_size):
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} PB"


def compress_sdp(sdp_dict):
    """压缩 SDP 信息以便传输"""
    json_str = json.dumps(sdp_dict)
    compressed = gzip.compress(json_str.encode('utf-8'))
    return base64.b64encode(compressed).decode('utf-8')


def decompress_sdp(compressed_str):
    """解压 SDP 信息"""
    compressed = base64.b64decode(compressed_str.encode('utf-8'))
    json_str = gzip.decompress(compressed).decode('utf-8')
    return json.loads(json_str)


def get_local_ip():
    """获取本机 IP 地址"""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"
