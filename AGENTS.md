# Working on Nagi

- **Nagi is read-only.** The glance and the tray never stop, send to or approve anything in an agent app. Don't add controls.
- **Keep the owner check on every private route** (`owner_auth.py`): loopback only, exact Host and Origin, same-user peer, no cookies.
- **Never read or log secrets.** Raw prompts, transcripts, credentials and tool output never enter an API response, a log or the journal. Tests must not touch real sign-ins (`tests/conftest.py` isolates HOME and blocks the network).
- **Say what's known, and nothing more.** A failed read shows "couldn't check" with the time it tried, never a 0. Anything unbuilt is labelled "coming soon".
- **Standard library only,** Python 3.11+. Run `python3 -B -m pytest tests -q` and `node --test tests/*.test.cjs` before a pull request; for the Mac app, `mac/test.sh`.
- **The website (`site/`)** runs the real panel from `web/`. After changing the panel, run `node site/scripts/sync-panel.mjs`.
