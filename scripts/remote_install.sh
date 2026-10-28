#!/bin/sh
set -e
mkdir -p /root/pitaya_delay
mv /root/server.py /root/dmtd.py /root/combine.py /root/tdc_server.py /root/tdc_regs.py /root/tdc_nutt.py /root/bit_to_bin.py /root/version.py /root/VERSION /root/pitaya_delay/ 2>/dev/null || true
if [ -f /root/pitaya_delay.bin ]; then
    cp /root/pitaya_delay.bin /root/pitaya_delay/pitaya_delay.bin
    cp /root/pitaya_delay.bin /lib/firmware/pitaya_delay.bin
fi
pkill -f '/opt/redpitaya/www/apps/pitaya_tdc/tdc_server.py' >/dev/null 2>&1 || true
pkill -f '/root/pitaya_delay/server.py' >/dev/null 2>&1 || true
pkill -f 'tdc_server.py' >/dev/null 2>&1 || true
sleep 0.3
echo 0 > /sys/class/fpga_manager/fpga0/flags
echo pitaya_delay.bin > /sys/class/fpga_manager/fpga0/firmware
i=0
while [ "$i" -lt 40 ]; do
    st=$(cat /sys/class/fpga_manager/fpga0/state 2>/dev/null || echo unknown)
    echo "fpga_manager state=$st"
    if [ "$st" = "operating" ]; then
        break
    fi
    i=$((i + 1))
    sleep 0.1
done
python3 -c 'import os,mmap,struct,sys; fd=os.open("/dev/mem",os.O_RDWR|os.O_SYNC); m=mmap.mmap(fd,4096,mmap.MAP_SHARED,mmap.PROT_READ|mmap.PROT_WRITE,offset=0x40700000); ident=struct.unpack_from("<I",m,0)[0]; m.close(); os.close(fd); print("TDC ID=0x%08X"%ident); sys.exit(0 if ident==0x54444331 else 1)'
cd /root/pitaya_delay
nohup python3 server.py --host 0.0.0.0 --port 8080 --udp-port 8081 --base 0x40700000 >/tmp/pitaya_delay.log 2>&1 &
sleep 8
python3 -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8080/api/health",timeout=5).read().decode())' || { echo "health failed"; cat /tmp/pitaya_delay.log; }
# SCPI is started by rp_app/pitaya_delay/fpga.sh (pitaya-scpi-safe).
# Do not systemctl start redpitaya_scpi — that unit runs overlay.sh v0.94 and wipes this image.
