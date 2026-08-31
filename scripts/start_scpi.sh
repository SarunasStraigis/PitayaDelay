#!/bin/sh
set -e
python3 -c 'import os,mmap,struct,sys; fd=os.open("/dev/mem",os.O_RDWR|os.O_SYNC); m=mmap.mmap(fd,4096,mmap.MAP_SHARED,mmap.PROT_READ|mmap.PROT_WRITE,offset=0x40700000); ident=struct.unpack_from("<I",m,0)[0]; m.close(); os.close(fd); print("TDC ID=0x%08X"%ident); sys.exit(0 if ident==0x54444331 else 1)'
pkill -x scpi-server >/dev/null 2>&1 || true
systemctl stop redpitaya_scpi.service >/dev/null 2>&1 || true
systemctl reset-failed pitaya-scpi-safe.service >/dev/null 2>&1 || true
systemctl stop pitaya-scpi-safe.service >/dev/null 2>&1 || true
systemd-run --unit=pitaya-scpi-safe --collect \
  -E PATH_REDPITAYA=/opt/redpitaya \
  -E LD_LIBRARY_PATH=/opt/redpitaya/lib \
  -E PATH=/sbin:/usr/sbin:/bin:/usr/bin:/opt/redpitaya/sbin:/opt/redpitaya/bin \
  /opt/redpitaya/bin/scpi-server
sleep 1.2
ss -lntp | grep 5000
python3 -c 'import os,mmap,struct; fd=os.open("/dev/mem",os.O_RDWR|os.O_SYNC); m=mmap.mmap(fd,4096,mmap.MAP_SHARED,mmap.PROT_READ|mmap.PROT_WRITE,offset=0x40700000); print("TDC after SCPI=0x%08X"%struct.unpack_from("<I",m,0)[0]); m.close(); os.close(fd)'
