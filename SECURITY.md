# Security and safety policy

## Supported versions
Pre-1.0: only the latest tagged release and `main` receive fixes.

## Reporting a vulnerability
Use GitHub's private vulnerability reporting (repository **Security** tab,
**Report a vulnerability**). Please do not open a public issue for
exploitable bugs.

## Flight-safety defects
Anything that could make a generated mission fly unsafely (wrong heights,
wrong coordinates, a linter rule that fails to catch a bad file) is treated
with the same priority as a security bug. Report it privately first.

## How Dīvi protects you

Dīvi runs on your own computer. These are the doors it keeps shut:

| Risk | What Dīvi does |
|---|---|
| Someone on the same network opening Dīvi | The window's server listens on 127.0.0.1 only: nothing on the network can reach it. |
| A website in your browser reaching Dīvi (DNS rebinding, cross-site connections) | Requests that do not name 127.0.0.1 or localhost are refused, and the live connection behind each screen accepts only Dīvi's own pages (`app/ui/guard.py`). |
| A crafted mission, KML, KMZ, shapefile or ZIP | XML is read without document type declarations, entities or network access; archives are read with limits on entries, size and expansion (zip bombs) and with no names that climb out of a folder (`adapters/safe_files.py`, `core/wpml/kmz.py`). |
| A mission that would fly unsafely | Every mission is checked (`core/wpml/lint.py`) before it is written or sent; a failed check stops it. |
| The phone over Wi-Fi | Only Android's paired wireless debugging (a pairing code, encrypted); Dīvi never switches on open network debugging. |
| The processing engine (WebODM/NodeODM) | Run it on this computer only: `docker run -p 127.0.0.1:3000:3000 ...`. NodeODM has no login of its own; published on all addresses, anyone on your network could use it and download your maps. An engine on another computer receives your photos: use https or a network you trust. |
| Known holes in libraries Dīvi uses | Locked versions (`uv.lock`), checked against the Python advisory database on every change and weekly (`.github/workflows/security.yml`); Dependabot proposes fixes. |
| Coordinates and photos leaving your computer | Nothing is sent anywhere unless you ask: the map background and place search contact OpenStreetMap only when used. Project records and reports hold paths and dates, never coordinates. |

What Dīvi does not do: it has no licence check or copy protection. It is open source under the
AGPL; the licence and the commercial licence terms (COMMERCIAL.md) are the control, and a check in
local Python code could not be enforced anyway.

## Scope notes
- The project never needs your DJI account, passwords or API keys.
- Third-party tools (WebODM/NodeODX, DJI apps) have their own policies.
