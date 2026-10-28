# Build on the Pitaya (the dashboard lists only apps that have controllerhf.so):
#   cd /opt/redpitaya/www/apps/pitaya_delay
#   make

CXX ?= g++
CFLAGS = -Wall -Wextra -fPIC -O2
LDFLAGS = -shared -fPIC

.PHONY: all clean

all: controllerhf.so

controllerhf.so: src/main.cpp
	$(CXX) $(CFLAGS) $(LDFLAGS) -o $@ $<

clean:
	rm -f controllerhf.so src/*.o
