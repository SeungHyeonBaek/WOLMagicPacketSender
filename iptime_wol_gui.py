# iptime_wol_gui.py
# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import json
import os
import re
import socket
import struct
import subprocess
import sys
from pathlib import Path

APP_NAME = "WOL_Magic_Packet_Sender"
DEFAULT_PORTS = [7, 9]  # Default ports when no port is specified
CONFIG_DIR = Path(os.getenv("APPDATA") or Path.home() / "AppData/Roaming") / APP_NAME
CONFIG_PATH = CONFIG_DIR / "config.json"

# -----------------------------
# Utils: Configuration Save/Load
# -----------------------------
def load_config():
    try:
        if CONFIG_PATH.exists():
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {
        "router_ip": "http://192.168.0.1/",
        "port": "",  # Empty string means use default ports
        "mac": ""
    }

def save_config(cfg):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

# -----------------------------
# Utils: MAC Address String Normalization/Validation
# -----------------------------
def normalize_mac(mac_str: str) -> str:
    mac = mac_str.strip().upper().replace("-", ":")
    if re.fullmatch(r"([0-9A-F]{2}:){5}[0-9A-F]{2}", mac):
        return mac
    raise ValueError("Invalid MAC address format. Example: AA:BB:CC:DD:EE:FF")

# -----------------------------
# WOL Transmission Method (Direct UDP)
# -----------------------------
def send_magic_packet_advanced(mac: str, host: str, port_input: str):
    """Send Magic Packet to user-specified port(s)"""
    # Parse port input - if empty, use default ports
    if not port_input.strip():
        ports = DEFAULT_PORTS
    else:
        try:
            port = int(port_input.strip())
            ports = [port]
        except ValueError:
            raise ValueError(f"Invalid port number: {port_input}")
    
    # MAC address normalization
    mac_clean = mac.replace(":", "").replace("-", "").upper()
    if len(mac_clean) != 12 or not all(c in "0123456789ABCDEF" for c in mac_clean):
        raise ValueError(f"Invalid MAC address format: {mac}")
    
    # Generate Magic Packet
    mac_bytes = bytes.fromhex(mac_clean)
    magic_packet = b"\xff" * 6 + mac_bytes * 16
    
    success_count = 0
    results = []
    
    for port in ports:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(3)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                
                # Send 3 times consecutively
                sent_count = 0
                for i in range(3):
                    try:
                        bytes_sent = sock.sendto(magic_packet, (host, port))
                        if bytes_sent == len(magic_packet):
                            sent_count += 1
                    except Exception:
                        pass
                    time.sleep(0.1)
                
                if sent_count > 0:
                    success_count += 1
                    results.append(f"Port {port}: {sent_count}/3 transmission success")
                else:
                    results.append(f"Port {port}: transmission failed")
                    
        except Exception as e:
            results.append(f"Port {port}: Error - {e}")
        
        time.sleep(0.3)
    
    return success_count > 0, results

# -----------------------------
# Ping for Wake-up Confirmation (Windows/Other OS Support)
# -----------------------------
def ping_once(host: str, timeout_ms=1000):
    # Windows: ping -n 1 -w 1000
    # Linux/Mac: ping -c 1 -W 1
    is_windows = os.name == "nt"
    if is_windows:
        cmd = ["ping", "-n", "1", "-w", str(timeout_ms), host]
    else:
        cmd = ["ping", "-c", "1", "-W", str(max(1, timeout_ms // 1000)), host]
    try:
        return subprocess.run(cmd, capture_output=True).returncode == 0
    except Exception:
        return False

# -----------------------------
# GUI Application
# -----------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("WOL Magic Packet Sender")
        self.geometry("520x400")
        self.resizable(False, False)

        self.cfg = load_config()

        # Input fields
        padd = {"padx": 8, "pady": 6}
        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, **padd)

        self.var_router_ip = tk.StringVar(value=self.cfg.get("router_ip", "http://192.168.0.1/"))
        self.var_port = tk.StringVar(value=str(self.cfg.get("port", "")))  # Empty for default ports
        self.var_mac = tk.StringVar(value=self.cfg.get("mac", ""))

        row = 0
        ttk.Label(frm, text="Router/Target Address (e.g. http://192.168.0.1/)").grid(row=row, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.var_router_ip, width=46).grid(row=row, column=1, sticky="we")
        row += 1
        ttk.Label(frm, text="WOL Port (default 7,9)").grid(row=row, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.var_port, width=10).grid(row=row, column=1, sticky="w")
        row += 1
        ttk.Label(frm, text="MAC Address (AA:BB:CC:DD:EE:FF)").grid(row=row, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.var_mac, width=46).grid(row=row, column=1, sticky="we")
        row += 1

        # Execute/Save buttons
        btn_frm = ttk.Frame(frm)
        btn_frm.grid(row=row, column=0, columnspan=2, sticky="we")
        self.btn_save = ttk.Button(btn_frm, text="Save Config", command=self.on_save)
        self.btn_save.pack(side="left", padx=4)
        self.btn_run = ttk.Button(btn_frm, text="Execute WOL", command=self.on_run)
        self.btn_run.pack(side="left", padx=4)
        self.btn_check = ttk.Button(btn_frm, text="Wake Check(Ping)", command=self.on_check)
        self.btn_check.pack(side="left", padx=4)
        row += 1

        # Progress status
        ttk.Label(frm, text="Progress Status").grid(row=row, column=0, sticky="w", pady=(8, 2))
        row += 1
        self.progress = ttk.Progressbar(frm, mode="determinate", maximum=100)
        self.progress.grid(row=row, column=0, columnspan=2, sticky="we")
        row += 1
        self.log = tk.Text(frm, height=12, state="disabled")
        self.log.grid(row=row, column=0, columnspan=2, sticky="we", pady=(4,0))
        row += 1

        for i in range(2):
            frm.columnconfigure(i, weight=1)

    def log_line(self, msg: str):
        self.log.config(state="normal")
        self.log.insert("end", f"{msg}\n")
        self.log.see("end")
        self.log.config(state="disabled")
        self.update_idletasks()

    def set_progress(self, val):
        self.progress["value"] = val
        self.update_idletasks()

    # ------ Button Handlers ------
    def on_save(self):
        try:
            port_value = self.var_port.get().strip()
            cfg = {
                "router_ip": self.var_router_ip.get().strip(),
                "port": port_value,  # Keep as string, empty means default
                "mac": normalize_mac(self.var_mac.get())
            }
            save_config(cfg)
            self.log_line("✓ Configuration saved successfully")
        except Exception as e:
            messagebox.showerror("Save Failed", str(e))

    def on_run(self):
        # Execute in background thread (prevent GUI freeze)
        threading.Thread(target=self._run_task, daemon=True).start()

    def _run_task(self):
        try:
            self.set_progress(0)
            router_ip = self.var_router_ip.get().strip()
            port_input = self.var_port.get().strip()
            mac = normalize_mac(self.var_mac.get())

            # Host normalization (remove http://)
            clean_host = router_ip.replace("http://", "").replace("https://", "").strip("/")

            # Show which ports will be used
            if not port_input:
                port_display = f"{DEFAULT_PORTS} (default)"
            else:
                port_display = port_input

            self.log_line(f"Started: Magic Packet direct transmission, target={clean_host}, MAC={mac}, ports={port_display}")
            self.set_progress(10)

            # Magic Packet transmission
            self.log_line("Transmitting Magic Packet...")
            success, results = send_magic_packet_advanced(mac, clean_host, port_input)
            self.set_progress(40)
            
            for result in results:
                self.log_line(f"  {result}")
            
            if success:
                self.log_line("✅ Magic Packet transmission successful!")
            else:
                raise RuntimeError("Transmission failed on all ports")
            self.set_progress(70)

            self.log_line("Transmission successful: Please check if PC is turning on.")
            self.set_progress(85)

            messagebox.showinfo("Success", "WOL packet transmission completed!")
            self.set_progress(100)
        except Exception as e:
            self.log_line(f"Failed: {e}")
            messagebox.showerror("Failed", f"WOL execution failed: {e}")
            self.set_progress(0)

    def on_check(self):
        # Ask for ping target (recommend entering PC's private IP instead of router address)
        PingDialog(self, on_ok=self._do_ping)

    def _do_ping(self, host: str):
        self.log_line(f"Ping check started: {host}")
        self.set_progress(10)
        def task():
            ok = False
            for i in range(10):
                self.log_line(f"Ping attempt {i+1}/10 ...")
                self.set_progress(10 + i*8)
                if ping_once(host, timeout_ms=1000):
                    ok = True
                    break
                time.sleep(1.0)
            if ok:
                self.log_line("✓ PC is responding (wake-up confirmed).")
                messagebox.showinfo("Wake Confirmed", "Success: PC is responding.")
                self.set_progress(100)
            else:
                self.log_line("✗ No response yet. Please try again later.")
                messagebox.showwarning("Check Failed", "No response yet. Please wait a bit longer and try again.")
                self.set_progress(0)
        threading.Thread(target=task, daemon=True).start()

class PingDialog(tk.Toplevel):
    def __init__(self, master, on_ok):
        super().__init__(master)
        self.title("Enter Ping Target (PC's private IP recommended)")
        self.resizable(False, False)
        self.on_ok = on_ok
        self.var_host = tk.StringVar(value="192.168.0.100")  # Example

        ttk.Label(self, text="Target IP/Host to ping").pack(padx=10, pady=8)
        ttk.Entry(self, textvariable=self.var_host, width=30).pack(padx=10, pady=4)
        frm = ttk.Frame(self)
        frm.pack(pady=10)
        ttk.Button(frm, text="OK", command=self._ok).pack(side="left", padx=4)
        ttk.Button(frm, text="Cancel", command=self.destroy).pack(side="left", padx=4)

    def _ok(self):
        host = self.var_host.get().strip()
        if not host:
            messagebox.showerror("Error", "Please enter a target.")
            return
        try:
            self.on_ok(host)
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error", str(e))

if __name__ == "__main__":
    app = App()
    app.mainloop()


