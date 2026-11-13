"""Resolve the client-side loopback socket owner; Linux fails closed."""
import ipaddress
import os
from pathlib import Path
import sys


def endpoint(value, ipv6):
    address, port = value.split(':')
    raw = bytes.fromhex(address)
    if len(raw) != (16 if ipv6 else 4):
        raise ValueError('Invalid socket address')
    if ipv6:
        raw = b''.join(raw[i:i + 4][::-1] for i in range(0, 16, 4))
        host = ipaddress.IPv6Address(raw)
        host = host.ipv4_mapped or host
    else:
        host = ipaddress.IPv4Address(raw[::-1])
    return str(host), int(port, 16)


def peer_uid(client, local):
    """Match the CLIENT entry, never the reader's reverse entry or listener UID."""
    try:
        client_host = ipaddress.ip_address(client[0])
        local_host = ipaddress.ip_address(local[0])
        client_host = getattr(client_host, 'ipv4_mapped', None) or client_host
        local_host = getattr(local_host, 'ipv4_mapped', None) or local_host
        if not client_host.is_loopback or not local_host.is_loopback:
            return None
        wanted = ((str(client_host), client[1]), (str(local_host), local[1]))
        owners = set()
        for name, ipv6 in (('/proc/net/tcp', False), ('/proc/net/tcp6', True)):
            try:
                with Path(name).open() as table:
                    next(table, None)
                    for row in table:
                        fields = row.split()
                        if len(fields) < 10 or fields[3] != '01':
                            continue
                        try:
                            pair = endpoint(fields[1], ipv6), endpoint(fields[2], ipv6)
                            if pair == wanted:
                                try:
                                    uid = int(fields[7])
                                except ValueError:
                                    return None
                                if uid < 0:
                                    return None
                                owners.add(uid)
                        except (ValueError, IndexError):
                            continue
            except OSError:
                continue
        return next(iter(owners)) if len(owners) == 1 else None
    except (ValueError, TypeError, IndexError, AttributeError):
        return None


def same_user(client, local):
    return sys.platform != 'linux' or peer_uid(client, local) == os.getuid()
