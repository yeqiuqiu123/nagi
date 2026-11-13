# Contributing

Thanks for helping. Issues and pull requests are welcome.

## Add a source
Nagi reads each agent app through an adapter.
1. **Start with the contract.** [design/sources-contract.md](design/sources-contract.md) covers what an adapter must report, and [design/sources-api.md](design/sources-api.md) has the exact shapes.
2. **Copy a working adapter.** `claude_source.py`, `codex_source.py` and `cursor_source.py` are the direct, on-this-computer ones; `source_adapters.py` holds T3 Code's.
3. **Stay read-only.** Report only what the app really says. If the app can't tell you something, mark that capability unsupported rather than guessing.
4. **Add tests with invented data.** See `tests/test_direct_*.py`.

## Before you open a pull request
```sh
python3 -B -m pytest tests -q
node --test tests/*.test.cjs
```
The Mac app has its own tests: `mac/test.sh`.

Please read [AGENTS.md](AGENTS.md). It holds the few rules every change keeps.
