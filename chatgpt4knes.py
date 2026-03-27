#!/usr/bin/env python3
"""
ChatGPT's FCEUX – Tkinter UI + pure‑Python stub with optional Cython acceleration.

Requirements:
  * Python 3.6+ (any recent CPython)
  * Optional: Cython (`pip install cython`) and a working compiler
    (MSVC on Windows, gcc/clang on macOS/Linux).

The CPU loop is a dummy that just increments the PC; no real emulation
happens.  It’s meant to show how you could plug a full NES core in place.
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading

# ------------------------------------------------------------------
# Optional Cython acceleration --------------------------------------
try:
    from Cython import inline  # runtime compilation helper
except Exception:              # pragma: no cover – fallback handled later
    inline = None

# Cython source that implements a tiny 6502‑style CPU loop.
CYTHON_CODE = """
cdef class NESCPU:
    cdef unsigned short pc
    cdef bytes rom
    cdef bint running

    def __init__(self, rom):
        self.rom = rom
        self.pc = 0x8000          # NES start address
        self.running = False

    def run(self):
        import time                # release GIL during sleep
        self.running = True
        cdef unsigned short pc_local = self.pc

        while self.running:
            pc_local += 1
            if pc_local & 0x1FF == 0:   # every 512 cycles
                time.sleep(0.001)       # give GUI a chance to update

        self.pc = pc_local

    def stop(self):
        self.running = False
"""

# Compile the Cython code on demand.
if inline is not None:
    try:
        cython_mod = inline(CYTHON_CODE)
        NESCPU_Cython = getattr(cython_mod, "NESCPU")
    except Exception as e:
        # Compilation failed – fall back to pure‑Python.
        NESCPU_Cython = None
else:
    NESCPU_Cython = None

# ------------------------------------------------------------------
class NESCore:
    """
    Minimal stub of a 6502‑based NES core.
    Only iNES header parsing and a dummy run loop are implemented.
    """
    def __init__(self):
        self.pr_print = False          # Print ROM header flag
        self.rom_data = None           # Raw ROM bytes
        self.prg_rom = b""
        self.chr_rom = b""
        self.mapper = 0
        self.running_flag = False      # Stop‑signal for the run loop

    def set_print_rom(self, flag: bool):
        self.pr_print = flag

    def load_rom(self, data: bytes):
        if len(data) < 16:
            raise ValueError("ROM too small to contain a valid header")

        header = data[:16]
        if header[0:4] != b"NES\x1a":
            raise ValueError("Missing NES magic bytes")

        prg_size = header[4] * 16 * 1024   # PRG ROM size in bytes
        chr_size = header[5] * 8 * 1024    # CHR ROM size in bytes

        self.mapper = ((header[6] >> 4) | (header[7] & 0xF0))
        self.prg_rom = data[16:16 + prg_size]
        self.chr_rom = data[16 + prg_size:16 + prg_size + chr_size]
        self.rom_data = data

        if self.pr_print:
            print("=== iNES Header ===")
            print(f"  PRG ROM: {len(self.prg_rom)} bytes")
            print(f"  CHR ROM: {len(self.chr_rom)} bytes")
            print(f"  Mapper:  {self.mapper}")
            print("====================")

    # ------------------------------------------------------------------
    def run(self):
        """Delegate to the Cython CPU driver if available."""
        if NESCPU_Cython is not None:
            # Instantiate the Cython CPU with the loaded PRG ROM.
            self.cpu = NESCPU_Cython(self.prg_rom)
            try:
                self.cpu.run()
            except Exception as e:
                print(f"Cython CPU error: {e}")
        else:
            # Fallback pure‑Python dummy loop.
            self._run_python_loop()

    def _run_python_loop(self):
        """Original dummy loop – kept only for safety."""
        self.running_flag = True
        pc = 0x8000
        while self.running_flag:
            pc = (pc + 1) & 0xFFFF
            if pc % 0x200 == 0:
                threading.Event().wait(0.001)

    def stop(self):
        """Signal the core to exit its loop and wait for the thread."""
        self.running_flag = False
        if hasattr(self, "cpu") and NESCPU_Cython is not None:
            self.cpu.stop()
# ------------------------------------------------------------------
class EmulatorApp:
    """
    FCEUX‑style UI that plugs the NESCore stub into Tkinter.
    """
    def __init__(self, master):
        self.master = master
        master.title("ChatGPT's FCEUX")          # <- window title
        master.geometry("520x480")

        # ----- 1️⃣ Menu bar --------------------------------------------------
        menubar = tk.Menu(master)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Load ROM", command=self.select_rom)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=master.quit)
        menubar.add_cascade(label="File", menu=file_menu)

        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Start", command=self.start_emulation)
        tools_menu.add_command(label="Stop", command=self.stop_emulation, state=tk.DISABLED)
        menubar.add_cascade(label="Tools", menu=tools_menu)

        master.config(menu=menubar)            # attach to root

        # ----- 2️⃣ Toolbar ---------------------------------------------------
        toolbar = ttk.Frame(master)
        self.load_btn = ttk.Button(toolbar, text="Load ROM", command=self.select_rom)
        self.start_btn = ttk.Button(toolbar, text="Start", command=self.start_emulation)
        self.stop_btn  = ttk.Button(toolbar, text="Stop", command=self.stop_emulation,
                                    state=tk.DISABLED)
        self.load_btn.pack(side=tk.LEFT, padx=2, pady=2)
        self.start_btn.pack(side=tk.LEFT, padx=2, pady=2)
        self.stop_btn.pack(side=tk.LEFT, padx=2, pady=2)
        toolbar.pack(fill=tk.X)

        # ----- 3️⃣ Video canvas (placeholder) --------------------------------
        self.video_canvas = tk.Canvas(master, width=256*2, height=240*2,
                                      bg='black', highlightthickness=0)
        self.video_canvas.pack(expand=True, fill=tk.BOTH)

        # ----- 4️⃣ Status bar -------------------------------------------------
        self.status_lbl = ttk.Label(master, text="No ROM loaded",
                                    relief=tk.SUNKEN, anchor='w')
        self.status_lbl.pack(side=tk.BOTTOM, fill=tk.X)

        # ----- 5️⃣ Core & thread state ---------------------------------------
        self.emu = NESCore()
        self.emulation_thread = None
        self.running = False

    # ------------------------------------------------------------------
    def select_rom(self):
        rom_path = filedialog.askopenfilename(
            title="Select NES ROM",
            filetypes=[("NES files", "*.nes")]
        )
        if not rom_path:
            return

        try:
            with open(rom_path, "rb") as f:
                rom_data = f.read()
            # Print header if the checkbox is ticked (optional)
            self.emu.set_print_rom(self.pr_checkbox_is_on())
            self.emu.load_rom(rom_data)
            filename = rom_path.split('/')[-1]
            self.status_lbl.config(text=f"Loaded: {filename}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load ROM:\n{e}")

    # Helper for the “Print ROM header” checkbox (kept from original stub)
    def pr_checkbox_is_on(self):
        # In the simplified UI we just always print – or you can add a checkbox.
        return False

    # ------------------------------------------------------------------
    def start_emulation(self):
        if self.running:
            return
        if not self.emu.prg_rom:
            messagebox.showwarning("No ROM", "Please load a ROM first.")
            return

        self.running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)

        # Run the emulator in a separate thread so the GUI stays responsive
        self.emulation_thread = threading.Thread(target=self.run_loop, daemon=True)
        self.emulation_thread.start()

    def run_loop(self):
        try:
            # Run the stub CPU loop until stop() is called
            self.emu.run()
        except Exception as e:
            print(f"Emulation error: {e}")
        finally:
            self.master.after(0, self.emulation_finished)

    def emulation_finished(self):
        self.running = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

    # ------------------------------------------------------------------
    def stop_emulation(self):
        if not self.running:
            return
        # Tell the core to exit its loop and wait for the thread.
        self.emu.stop()
        if self.emulation_thread:
            self.emulation_thread.join(timeout=0.1)
        self.emulation_finished()
# ----------------------------------------------------------------------
if __name__ == "__main__":
    root = tk.Tk()
    app = EmulatorApp(root)
    root.mainloop()
