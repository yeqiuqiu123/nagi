"""Owner-authenticated terminal status for shell prompts, tmux and Waybar."""
import argparse
from datetime import UTC, datetime
import json
import os
import signal
from urllib.request import Request

from jsonio import strict_json_loads
from owner_auth import authenticated_open
from status_summary import STATUS_PATH

BYTE_LIMIT = 64 * 1024


def deadline(_signal, _frame):
    raise TimeoutError()


def read_status(port, *, directory=None):
    request = Request(f'http://127.0.0.1:{port}{STATUS_PATH}')
    previous = signal.signal(signal.SIGALRM, deadline)
    # One wall-clock budget for owner proof, request, body and decoding.
    signal.setitimer(signal.ITIMER_REAL, .85)
    try:
        with authenticated_open(request, directory, timeout=.8) as reply:
            value = strict_json_loads(reply.read(BYTE_LIMIT + 1), BYTE_LIMIT)
        if value['version'] != 1:
            raise ValueError('Unsupported status version')
        return value
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def status_line(status):
    if not status:
        return 'nagi ?'
    counts = status['agents']
    parts = [f"{counts['running']} running" if counts is not None else 'nagi ?']
    if counts and counts['waitingOnYou']:
        parts.append(f"{counts['waitingOnYou']} asks you")
    if counts and status['partial']:
        parts.append('partial')
    if status['ci']['state']=='failed':
        repos = status['ci']['failedRepos']
        extra = f' +{len(repos)-1}' if len(repos)>1 else ''
        parts.append(f"CI ✗ {repos[0].split('/', 1)[1]}{extra}")
    elif status['ci']['state']=='unknown':
        parts.append('CI ?')
    if status['claudeRemainingPercent'] is not None:
        parts.append(f"Claude {status['claudeRemainingPercent']:g}%")
    return ' · '.join(parts)


def available(status):
    return (status is not None and status['agents'] is not None
            and not status['partial'] and status['ci']['state']!='unknown')


def main(argv=None):
    parser = argparse.ArgumentParser(prog='nagi')
    commands = parser.add_subparsers(dest='command', required=True)
    command = commands.add_parser('status', help='Read a quick status from the local reader')
    output = command.add_mutually_exclusive_group()
    output.add_argument('--json', action='store_true')
    output.add_argument('--waybar', action='store_true')
    output.add_argument('--quiet', '-q', action='store_true', help='Exit 0 for clear, 1 for an alert, 2 for unknown')
    command.add_argument('--port', type=int, default=os.environ.get('NAGI_PORT', '47831'))
    args = parser.parse_args(argv)
    if not 1024 <= args.port <= 65535:
        command.error('use a port between 1024 and 65535')
    try:
        status = read_status(args.port)
        line = status_line(status)
        alerts = status['alerts']
        known = available(status)
    except (OSError, ValueError, KeyError, TypeError, IndexError, RecursionError):
        status, line, alerts, known = None, 'nagi ?', [], False
    if args.quiet:
        return 1 if alerts else 0 if known else 2
    if args.json:
        print(json.dumps(status if status is not None else {
            'version':1, 'agents':None, 'partial':True, 'ci':{'state':'unknown','failedRepos':[]},
            'claudeRemainingPercent':None, 'alerts':[], 'machine':{
                'status':'unavailable','attemptedAt':datetime.now(UTC).isoformat(),'checkedAt':None,'reason':'reader_unavailable','data':None
            }}, ensure_ascii=False))
    elif args.waybar:
        classes = list(alerts)
        if not known:
            classes.append('unavailable')
        print(json.dumps({'text':line, 'tooltip':line, 'class':classes or ['normal']}, ensure_ascii=False))
    else:
        print(line)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
