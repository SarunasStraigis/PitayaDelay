#!/bin/sh
# Called by Bazaar on tile open (after rmoverlay.sh) and by control.py Start.
# Load pitaya_delay.bin. Never call overlay.sh v0.94.
set -e
APPDIR=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
BIN="$APPDIR/fpga/pitaya_delay.bin"
if [ ! -s "$BIN" ] && [ -s /root/pitaya_delay.bin ]; then
    BIN=/root/pitaya_delay.bin
fi
LOG=/tmp/pitaya_delay_fpga.log
MGR=/sys/class/fpga_manager/fpga0
PY=/usr/bin/python3
export PATH=/usr/bin:/bin:/sbin:/opt/redpitaya/sbin:/opt/redpitaya/bin:$PATH

exec 8>/tmp/pitaya_delay.fpga.lock
if ! flock -w 60 8; then
    echo "fpga lock timeout" >&2
    exit 1
fi

{
echo "---- $(date) ----"
echo "APPDIR=$APPDIR BIN=$BIN"

verify_id() {
    $PY - <<'PY'
import os, mmap, struct, sys
try:
    fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
    mem = mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=0x40700000)
    ident = struct.unpack_from("<I", mem, 0)[0]
    mem.close()
    os.close(fd)
except Exception as exc:
    print("ID read failed: %s" % exc)
    sys.exit(2)
print("TDC ID=0x%08X" % ident)
sys.exit(0 if ident == 0x54444331 else 1)
PY
}

stop_stock_scpi() {
    systemctl stop redpitaya_scpi.service >/dev/null 2>&1 || true
    systemctl reset-failed redpitaya_scpi.service >/dev/null 2>&1 || true
}

load_bin() {
    if [ ! -s "$BIN" ]; then
        echo "missing $BIN"
        return 1
    fi
    if [ ! -d "$MGR" ]; then
        echo "no $MGR"
        return 1
    fi
    cp "$BIN" /lib/firmware/pitaya_delay.bin
    sync
    echo 0 > "$MGR/flags"
    echo pitaya_delay.bin > "$MGR/firmware"
    i=0
    while [ "$i" -lt 40 ]; do
        st=$(cat "$MGR/state" 2>/dev/null || echo unknown)
        echo "fpga_manager state=$st"
        if [ "$st" = "operating" ]; then
            return 0
        fi
        i=$((i + 1))
        sleep 0.1
    done
    echo "fpga_manager did not reach operating"
    return 1
}

kill_old_tdc() {
    pkill -f '/opt/redpitaya/www/apps/pitaya_tdc/tdc_server.py' >/dev/null 2>&1 || true
}

server_alive() {
    if ps -eo args | grep -F 'server.py --host 0.0.0.0 --port 8080' | grep -v grep >/dev/null 2>&1; then
        return 0
    fi
    return 1
}

start_server() {
    kill_old_tdc
    if server_alive; then
        echo "server.py already running"
        return 0
    fi
    if [ ! -f /root/pitaya_delay/server.py ]; then
        echo "missing /root/pitaya_delay/server.py"
        return 1
    fi
    cd /root/pitaya_delay
    nohup $PY server.py --host 0.0.0.0 --port 8080 --udp-port 8081 --base 0x40700000 >/tmp/pitaya_delay.log 2>&1 8>&- &
    echo $! > /tmp/pitaya_delay.server.pid
    i=0
    while [ "$i" -lt 40 ]; do
        if $PY - <<'PY'
import sys, urllib.request
try:
    urllib.request.urlopen("http://127.0.0.1:8080/api/health", timeout=0.5).read()
except Exception:
    sys.exit(1)
sys.exit(0)
PY
        then
            echo "server.py health ok"
            return 0
        fi
        i=$((i + 1))
        sleep 0.25
    done
    echo "server.py health failed"
    tail -n 40 /tmp/pitaya_delay.log || true
    return 1
}

start_scpi() {
    if verify_id \
        && systemctl is-active --quiet pitaya-scpi-safe.service \
        && ss -lntp | grep -q ':5000'; then
        echo "safe SCPI already up"
        return 0
    fi
    verify_id
    pkill -x scpi-server >/dev/null 2>&1 || true
    systemctl stop redpitaya_scpi.service >/dev/null 2>&1 || true
    systemctl reset-failed pitaya-scpi-safe.service >/dev/null 2>&1 || true
    systemctl stop pitaya-scpi-safe.service >/dev/null 2>&1 || true
    systemd-run --unit=pitaya-scpi-safe --collect \
        -E PATH_REDPITAYA=/opt/redpitaya \
        -E LD_LIBRARY_PATH=/opt/redpitaya/lib \
        -E PATH=/sbin:/usr/sbin:/bin:/usr/bin:/opt/redpitaya/sbin:/opt/redpitaya/bin \
        /opt/redpitaya/bin/scpi-server 8>&-
    i=0
    while [ "$i" -lt 20 ]; do
        if ss -lntp | grep -q ':5000'; then
            echo "SCPI listening"
            if ! verify_id; then
                echo "TDC ID changed after SCPI; stopping pitaya-scpi-safe"
                systemctl stop pitaya-scpi-safe.service >/dev/null 2>&1 || true
                return 1
            fi
            echo "TDC after SCPI ok"
            return 0
        fi
        i=$((i + 1))
        sleep 0.15
    done
    echo "SCPI not listening"
    verify_id || true
    return 1
}

start_control() {
    if ss -lnt | grep -q '127.0.0.1:12781'; then
        echo "control.py already listening"
        return 0
    fi
    nohup $PY "$APPDIR/control.py" >>/tmp/pitaya_delay_control.log 2>&1 8>&- &
    sleep 0.2
}

start_control
stop_stock_scpi
if ! verify_id; then
    echo "loading $BIN"
    load_bin
    sleep 0.3
    verify_id
fi
start_server
start_scpi
echo "fpga.sh done"
} >>"$LOG" 2>&1
