import os
import sys
import time
import socket
import re
import subprocess

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(('8.8.8.8', 53))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"

def is_port_open(port=8000):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        res = s.connect_ex(('127.0.0.1', port))
        return res == 0
    finally:
        s.close()

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base_dir)

    print("\n" + "=" * 64)
    print("       ReelForge Studio - Going Live on Any Device")
    print("=" * 64 + "\n")

    # 1. Check or start uvicorn
    if not is_port_open(8000):
        print("[1/3] Starting ReelForge local engine...")
        subprocess.Popen([sys.executable, "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"])
        for _ in range(15):
            time.sleep(0.5)
            if is_port_open(8000):
                break
    else:
        print("[1/3] ReelForge local engine is active on port 8000.")

    # 2. Local Wi-Fi URL
    local_ip = get_local_ip()
    wifi_url = f"http://{local_ip}:8000"

    # 3. Cloudflare tunnel
    cloudflared_bin = os.path.join(base_dir, "cloudflared.exe")
    if not os.path.exists(cloudflared_bin):
        print("[2/3] Downloading Cloudflare helper (one-time setup)...")
        subprocess.run(["curl.exe", "-L", "-o", "cloudflared.exe", "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"])

    print("[2/3] Connecting to global Cloudflare network...")
    cmd = [cloudflared_bin, "tunnel", "--url", "http://localhost:8000"]
    proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, errors="ignore")

    public_url = None
    t_end = time.time() + 15
    while time.time() < t_end:
        line = proc.stderr.readline()
        if "trycloudflare.com" in line:
            m = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
            if m:
                public_url = m.group(0)
                break

    print("[3/3] Ready!\n", flush=True)
    print("*" * 64, flush=True)
    print("  >> PUBLIC INTERNET LINK (Works on ANY phone/tablet worldwide):", flush=True)
    print(f"     URL:  {public_url or 'Connecting...'}", flush=True)
    print("\n  >> LOCAL WI-FI LINK (Devices connected to your Wi-Fi):", flush=True)
    print(f"     URL:  {wifi_url}", flush=True)
    print("\n  >> THIS COMPUTER:", flush=True)
    print("     URL:  http://localhost:8000", flush=True)
    print("*" * 64, flush=True)
    print("\n[!] Keep this window open. Press Ctrl+C at any time to stop.\n", flush=True)

    try:
        while proc.poll() is None:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping live tunnel...")
        proc.terminate()

if __name__ == "__main__":
    main()
