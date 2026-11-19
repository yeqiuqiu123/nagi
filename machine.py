"""This computer's CPU, memory, disk and uptime, for the limits response. Linux and macOS only."""
import ctypes
import math
import os
import re
import shutil
import subprocess
import sys
import threading
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


def machine_command(argv, timeout=.8):
    from ci_workspace import env_path
    return subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                          timeout=timeout, check=True, text=True,
                          env={'PATH':env_path(),'LC_ALL':'C'}).stdout

def mac_memory():
    total = int(machine_command(['/usr/sbin/sysctl', '-n', 'hw.memsize']).strip())
    vm = machine_command(['/usr/bin/vm_stat'])
    page = re.search(r'page size of ([0-9]+) bytes', vm)
    counts = dict(re.findall(r'^(Pages [^:]+):\s+([0-9]+)\.', vm, re.M))
    if not page or any(key not in counts for key in ('Pages free', 'Pages inactive', 'Pages speculative')):
        raise ValueError('Memory counters unavailable')
    available = sum(int(counts[key]) for key in ('Pages free', 'Pages inactive', 'Pages speculative')) * int(page[1])
    if not 0 <= available <= total or total <= 0:
        raise ValueError('Invalid memory counters')
    return total, total - available


def mac_memory_uptime():
    total, used = mac_memory()
    boot = machine_command(['/usr/sbin/sysctl', '-n', 'kern.boottime'])
    match = re.fullmatch(r'\{ sec = ([0-9]+), usec = [0-9]+ \}.*\s*', boot)
    if not match:
        raise ValueError('Boot time unavailable')
    return total, used, max(0, int(time.time()) - int(match[1]))


def linux_memory():
    values = {}
    with Path('/proc/meminfo').open() as source:
        for row in source:
            key, _, value = row.partition(':')
            if key in ('MemTotal', 'MemAvailable'):
                values[key] = int(value.split()[0]) * 1024
    total = values['MemTotal']
    return total, total - values['MemAvailable']


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
    total_memory, used_memory = linux_memory()
    disk = shutil.disk_usage(directory)
    return {
        'diskFreeBytes': disk.free,
        'diskUsedBytes': disk.used,
        'diskTotalBytes': disk.total,
        'cpuPercent': round(cpu, 1) if cpu is not None and 0 <= cpu <= 100 else None,
        'memoryUsedBytes': used_memory,
        'memoryTotalBytes': total_memory,
        'uptimeSeconds': int(float(Path('/proc/uptime').read_text().split()[0])),
    }



def cpu_load(platform):
    if platform == 'darwin':
        average, cores = machine_command(['/usr/sbin/sysctl', '-n', 'vm.loadavg', 'hw.logicalcpu']).splitlines()
        load = float(average.strip('{} ').split()[0])
        count = int(cores)
    else:
        with Path('/proc/loadavg').open() as source:
            load = float(source.readline(256).split()[0])
        count = os.cpu_count()
    if not count or not math.isfinite(load) or load < 0:
        raise ValueError('CPU load unavailable')
    return round(100 * load / count, 1)


def nvidia_load():
    from ci_workspace import env_path
    executable = shutil.which('nvidia-smi', path=env_path())
    if not executable:
        return None
    lines = machine_command([executable, '--query-gpu=utilization.gpu,memory.used,memory.total',
                             '--format=csv,noheader,nounits']).splitlines()
    if not 1 <= len(lines) <= 64:
        raise ValueError('GPU counters unavailable')
    samples = []
    for line in lines:
        utilization, used, total = map(int, line.split(','))
        if not 0 <= utilization <= 100 or not 0 <= used <= total or total <= 0:
            raise ValueError('Invalid GPU counters')
        samples.append((utilization, used, total))
    return {'utilizationPercent':max(sample[0] for sample in samples),
            'memoryUsedBytes':sum(sample[1] for sample in samples) * 1024**2,
            'memoryTotalBytes':sum(sample[2] for sample in samples) * 1024**2}


def read_load(platform):
    def memory():
        total, used = mac_memory() if platform == 'darwin' else linux_memory()
        if total <= 0 or not 0 <= used <= total:
            raise ValueError('Invalid memory counters')
        return round(100 * used / total, 1)

    def optional(read):
        try:
            return read()
        except (OSError, ValueError, IndexError, KeyError, subprocess.SubprocessError):
            return None

    return {'cpuLoadPercent':optional(lambda:cpu_load(platform)),
            'memoryPressurePercent':optional(memory), 'gpu':optional(nvidia_load)}


class MachineLoad:
    def __init__(self, clock):
        from agents_service import outcome
        self.clock = clock
        self.lock = threading.Lock()
        self.snapshot = outcome('unavailable', clock().isoformat(), reason='checking')

    def poll(self):
        from agents_service import outcome
        at = self.clock().isoformat()
        if sys.platform not in ('linux', 'darwin'):
            result = outcome('unsupported', at, reason='platform_unsupported')
        else:
            data = read_load(sys.platform)
            result = (outcome('ok', at, at, data=data) if any(v is not None for v in data.values())
                      else outcome('unavailable', at, self.read()['checkedAt'], 'cannot_read_machine'))
        with self.lock:
            self.snapshot = result

    def read(self):
        with self.lock:
            return self.snapshot
