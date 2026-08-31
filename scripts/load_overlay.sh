#!/bin/sh
# Load the versioned overlay via fpga_manager and check TDC ID at 0x40700000.
set -e
APPDIR=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
REPO=$(CDPATH= cd -- "$APPDIR/.." && pwd)
VER=$(tr -d '\r' < "$REPO/VERSION" | head -n 1)
BIT="$REPO/fpga/releases/$VER/pitaya_delay.bit"
BIN="$REPO/fpga/output/pitaya_delay.bin"
if [ -f "$BIT" ]; then
    mkdir -p "$REPO/fpga/output"
    python3 "$REPO/sw/bit_to_bin.py" "$BIT" "$BIN"
elif [ ! -f "$BIN" ] && [ -f "$APPDIR/fpga/pitaya_delay.bin" ]; then
    BIN="$APPDIR/fpga/pitaya_delay.bin"
fi
if [ ! -f "$BIN" ]; then
    echo "missing overlay for $VER (fpga/releases/$VER/pitaya_delay.bit)" >&2
    exit 1
fi
MGR=/sys/class/fpga_manager/fpga0
cp "$BIN" /lib/firmware/pitaya_delay.bin
echo 0 > "$MGR/flags"
echo pitaya_delay.bin > "$MGR/firmware"
python3 - <<'PY'
import os, mmap, struct, sys, time
time.sleep(0.3)
fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
mem = mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=0x40700000)
ident = struct.unpack_from("<I", mem, 0)[0]
mem.close()
os.close(fd)
print("TDC ID=0x%08X" % ident)
sys.exit(0 if ident == 0x54444331 else 1)
PY
