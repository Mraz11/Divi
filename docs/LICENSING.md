# Licensing policy

- Project license: **AGPL-3.0-or-later**, with a separate commercial licence for those who
  cannot meet its conditions (dual licensing; decided November 2026). The policy, the price
  rule and the citation request are in [COMMERCIAL.md](../COMMERCIAL.md).
- Full license text: the `LICENSE` file (canonical text from
  https://www.gnu.org/licenses/agpl-3.0.txt).

## SPDX header policy
Every source file in `src/`, `tests/` and `scripts/` starts with:

    # SPDX-FileCopyrightText: <year> Dīvi contributors
    # SPDX-License-Identifier: AGPL-3.0-or-later

## Third-party code
- Do not paste code from other projects without recording its license and
  origin in the commit message (and, later, in docs/THIRD_PARTY.md).
- Never copy GPL or AGPL code from other projects into Dīvi: code that someone else owns
  under those licences cannot be offered under the commercial licence. Patterns and file
  formats are fine to learn from; code is not. Dependencies must have a permissive licence
  (MIT, BSD, Apache-2.0, HPND) and stay separate packages.
- NodeODX/ODX run as separate processes reached over HTTP (keep that boundary).
- Record each DEM and basemap source's license in the provenance bundle.

## Dual licensing: what must stay true

- One party holds the rights to all of Dīvi's own code. Outside contributions are merged only
  with a signed contributor agreement that allows both licences.
- `CITATION.cff` names the author and, after release, the DOI of the archived version. Fill in
  the author name before the first tagged release.
- The licence of a version already released under the AGPL cannot be withdrawn: anyone may keep
  using that version under the AGPL.
- Local software cannot enforce who uses it. The licences and the citation request are the
  control; there is no licence check in the program.
