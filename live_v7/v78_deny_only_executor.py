#!/usr/bin/env python3
"""V78 isolated executor staging: deliberately NO execution capabilities.

This tiny worker proves Linux/systemd isolation only; it never receives
broker credentials, opens network sockets, reads live services, or places orders.
"""
import os
import signal
import time

running = True

def stop(_signum, _frame):
    global running
    running = False

signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)

print("V78_STAGING_STARTED ROLE=optionx-executor LIVE_ORDERS=OFF DB_ACCESS=OFF", flush=True)
while running:
    time.sleep(5)
print("V78_STAGING_STOPPED NO_BROKER_ORDERS", flush=True)
