import socket
import asyncio
import re
import logging
from app.db import get_settings

logger = logging.getLogger("ciscotools.terminal")

class TelnetSession:
    def __init__(self, ip: str, port: int = 23):
        self.ip = ip
        self.port = port
        self.sock = None
        self.loop = asyncio.get_event_loop()

    def connect(self, timeout=5.0):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(timeout)
        self.sock.connect((self.ip, self.port))
        self.sock.setblocking(False)

    def filter_telnet_iac(self, data: bytes) -> bytes:
        """Filter out Telnet negotiation IAC sequences (0xFF ...) and respond if needed."""
        clean_buf = bytearray()
        i = 0
        n = len(data)
        while i < n:
            b = data[i]
            if b == 255: # IAC
                if i + 2 < n:
                    cmd = data[i+1]
                    opt = data[i+2]
                    # Respond to WILL/DO with DONT/WONT if needed
                    if cmd in (251, 252): # WILL, WONT -> respond DONT
                        try:
                            self.sock.sendall(bytes([255, 254, opt]))
                        except Exception:
                            pass
                    elif cmd in (253, 254): # DO, DONT -> respond WONT
                        try:
                            self.sock.sendall(bytes([255, 252, opt]))
                        except Exception:
                            pass
                    i += 3
                elif i + 1 < n:
                    i += 2
                else:
                    i += 1
            else:
                clean_buf.append(b)
                i += 1
        return bytes(clean_buf)

    async def read_until(self, patterns, timeout=6.0):
        """Read socket data until one of the regex patterns matches or timeout."""
        buf = ""
        start = self.loop.time()
        while self.loop.time() - start < timeout:
            try:
                raw = await self.loop.sock_recv(self.sock, 1024)
                if not raw:
                    break
                clean = self.filter_telnet_iac(raw).decode('utf-8', errors='ignore')
                buf += clean
                for pat in patterns:
                    if re.search(pat, buf, re.IGNORECASE):
                        return buf, True
            except (BlockingIOError, InterruptedError):
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Error in read_until: {e}")
                break
        return buf, False

    async def auto_login(self, websocket):
        """Perform initial telnet connect and auto-login using stored settings."""
        settings = get_settings()
        username = settings.get("username", "")
        password = settings.get("password", "")

        await websocket.send_text(f"\r\n\x1b[33m📡 Connecting to Cisco Switch at {self.ip}:{self.port}...\x1b[0m\r\n")

        try:
            await self.loop.run_in_executor(None, self.connect)
        except Exception as e:
            await websocket.send_text(f"\r\n\x1b[31m❌ Connection Failed: {str(e)}\x1b[0m\r\n")
            return False

        await websocket.send_text("\x1b[32m✅ Socket Connected. Authenticating...\x1b[0m\r\n\r\n")

        buf, matched = await self.read_until([r"username:", r"password:", r"[>#]"], timeout=5.0)
        if buf:
            await websocket.send_text(buf)

        buf_last = buf
        if re.search(r"username:", buf, re.IGNORECASE) and username:
            await self.loop.sock_sendall(self.sock, (username + "\r\n").encode('utf-8'))
            buf2, _ = await self.read_until([r"password:", r"[>#]"], timeout=5.0)
            if buf2:
                await websocket.send_text(buf2)
                buf_last = buf2
            if password and re.search(r"password:", buf2, re.IGNORECASE):
                await self.loop.sock_sendall(self.sock, (password + "\r\n").encode('utf-8'))
                buf3, _ = await self.read_until([r"[>#]"], timeout=5.0)
                if buf3:
                    await websocket.send_text(buf3)
                    buf_last = buf3
        elif re.search(r"password:", buf, re.IGNORECASE) and password:
            await self.loop.sock_sendall(self.sock, (password + "\r\n").encode('utf-8'))
            buf2, _ = await self.read_until([r"[>#]"], timeout=5.0)
            if buf2:
                await websocket.send_text(buf2)
                buf_last = buf2

        return True

    async def bridge(self, websocket, idle_timeout: float = 600.0):
        """
        Bridge websocket messages with socket bi-directionally.
        Includes idle timeout (default 10 mins) to prevent exhausting Cisco VTY lines.
        """
        last_activity = self.loop.time()

        async def socket_to_ws():
            nonlocal last_activity
            while True:
                try:
                    raw = await self.loop.sock_recv(self.sock, 2048)
                    if not raw:
                        await websocket.send_text("\r\n\x1b[31m❌ Connection closed by remote host.\x1b[0m\r\n")
                        break
                    clean = self.filter_telnet_iac(raw).decode('utf-8', errors='ignore')
                    if clean:
                        last_activity = self.loop.time()
                        await websocket.send_text(clean)
                except Exception:
                    break

        async def ws_to_socket():
            nonlocal last_activity
            while True:
                try:
                    data = await websocket.receive_text()
                    if data:
                        last_activity = self.loop.time()
                        await self.loop.sock_sendall(self.sock, data.encode('utf-8'))
                except Exception:
                    break

        async def idle_checker():
            while True:
                await asyncio.sleep(15)
                if self.loop.time() - last_activity > idle_timeout:
                    try:
                        await websocket.send_text("\r\n\x1b[33m⚠️ Terminal session closed due to inactivity (Idle Timeout).\x1b[0m\r\n")
                    except Exception:
                        pass
                    break

        tasks = [
            asyncio.create_task(socket_to_ws()),
            asyncio.create_task(ws_to_socket()),
            asyncio.create_task(idle_checker())
        ]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()

    def close(self):
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
