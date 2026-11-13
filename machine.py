"""This computer's CPU, memory, disk and uptime, for the limits response. Linux and macOS only."""
import ctypes
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path


def cpu_ticks():
    with Path('/proc/stat').open() as source:
        fields = source.readline().split()
    if fields[0] != 'cpu' or len(fields) < 9:
        raise ValueError('CPU counters unavailable')
    ticks = list(map(int, fields[1:9]))
    return sum(ticks), ticks[3] + ticks[4]


def mac_cpu_ticks():
    # Mach host_statistics(HOST_CPU_LOAD_INFO): user, system, idle, nice ticks.
    library = ctypes.CDLL('/usr/lib/libSystem.B.dylib')
    library.mach_host_self.restype = ctypes.c_uint
    library.host_statistics.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_uint)]
    library.mach_port_deallocate.argtypes = [ctypes.c_uint, ctypes.c_uint]
    counters = (ctypes.c_int * 4)()
    count = ctypes.c_uint(4)
    host = library.mach_host_self()
    try:
        if library.host_statistics(host, 3, counters, ctypes.byref(count)) != 0 or count.value != 4:
            raise OSError('CPU counters unavailable')
        ticks = [ctypes.c_uint(value).value for value in counters]
        return sum(ticks), ticks[2]
    finally:
        task = ctypes.c_uint.in_dll(library, 'mach_task_self_').value
        library.mach_port_deallocate(task, host)


def mac_memory_uptime():
    def output(args):
        return subprocess.run(args, capture_output=True, text=True, timeout=2, check=True).stdout
    total = int(output(['/usr/sbin/sysctl', '-n', 'hw.memsize']).strip())
    boot = output(['/usr/sbin/sysctl', '-n', 'kern.boottime'])
    match = re.fullmatch(r'\{ sec = ([0-9]+), usec = [0-9]+ \}.*\s*', boot)
    if not match:
        raise ValueError('Boot time unavailable')
    vm = output(['/usr/bin/vm_stat'])
    page = re.search(r'page size of ([0-9]+) bytes', vm)
    counts = dict(re.findall(r'^(Pages [^:]+):\s+([0-9]+)\.', vm, re.M))
    if not page or any(key not in counts for key in ('Pages free', 'Pages inactive', 'Pages speculative')):
        raise ValueError('Memory counters unavailable')
    available = sum(int(counts[key]) for key in ('Pages free', 'Pages inactive', 'Pages speculative')) * int(page[1])
    if not 0 <= available <= total or total <= 0:
        raise ValueError('Invalid memory counters')
    return total, total - available, max(0, int(time.time()) - int(match[1]))


def host_metrics(directory):
    if sys.platform not in ('linux', 'darwin'):
        return {'status': 'unsupported'}
    if sys.platform == 'darwin':
        total_memory, used_memory, uptime = mac_memory_uptime()
        disk = shutil.disk_usage(directory)
        try:
            total, idle = mac_cpu_ticks()
            time.sleep(.12)
            next_total, next_idle = mac_cpu_ticks()
            span = next_total - total
            cpu = 100 * (span - (next_idle - idle)) / span if span > 0 else None
        except (OSError, ValueError, AttributeError):
            cpu = None
        return {'diskFreeBytes': disk.free, 'diskUsedBytes': disk.used, 'diskTotalBytes': disk.total,
                'cpuPercent': round(cpu, 1) if cpu is not None and 0 <= cpu <= 100 else None,
                'memoryUsedBytes': used_memory, 'memoryTotalBytes': total_memory, 'uptimeSeconds': uptime}
    total, idle = cpu_ticks()
    time.sleep(.12)
    next_total, next_idle = cpu_ticks()
    span = next_total - total
    cpu = 100 * (span - (next_idle - idle)) / span if span > 0 else None
    values = {}
    with Path('/proc/meminfo').open() as source:
        for row in source:
            key, _, value = row.partition(':')
            if key in ('MemTotal', 'MemAvailable'):
                values[key] = int(value.split()[0]) * 1024
    disk = shutil.disk_usage(directory)
    return {
        'diskFreeBytes': disk.free,
        'diskUsedBytes': disk.used,
        'diskTotalBytes': disk.total,
        'cpuPercent': round(cpu, 1) if cpu is not None and 0 <= cpu <= 100 else None,
        'memoryUsedBytes': values['MemTotal'] - values['MemAvailable'],
        'memoryTotalBytes': values['MemTotal'],
        'uptimeSeconds': int(float(Path('/proc/uptime').read_text().split()[0])),
    }
