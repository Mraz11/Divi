# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The data folder and the provenance file after the rename: nothing is moved, nothing is lost."""

from pathlib import Path

from avispria.app.paths import OLD_PROVENANCE, PROVENANCE, app_home, provenance_file


def test_a_new_install_uses_divi(tmp_path: Path) -> None:
    assert app_home(tmp_path) == tmp_path / "Divi"


def test_old_data_is_kept_where_it_is(tmp_path: Path) -> None:
    old = tmp_path / "Avispria"
    (old / "phone-backups").mkdir(parents=True)
    assert app_home(tmp_path) == old and old.is_dir()  # used, not moved
    (tmp_path / "Divi").mkdir()
    assert app_home(tmp_path) == tmp_path / "Divi"  # the new folder wins once it exists


def test_a_source_checkout_is_never_taken_for_the_data_folder(tmp_path: Path) -> None:
    clone = tmp_path / "Avispria"
    (clone / ".git").mkdir(parents=True)
    (clone / "settings.json").write_text("{}")
    assert app_home(tmp_path) == tmp_path / "Divi" and (clone / ".git").is_dir()
    (tmp_path / "Other").mkdir()
    assert app_home(tmp_path / "Other") == tmp_path / "Other" / "Divi"  # an empty home


def test_provenance_old_name_is_still_read(tmp_path: Path) -> None:
    assert provenance_file(tmp_path) == tmp_path / PROVENANCE
    (tmp_path / OLD_PROVENANCE).write_text("{}")
    assert provenance_file(tmp_path) == tmp_path / OLD_PROVENANCE
    (tmp_path / PROVENANCE).write_text("{}")
    assert provenance_file(tmp_path) == tmp_path / PROVENANCE


def test_a_console_without_accents_does_not_crash() -> None:
    import io
    import sys

    from avispria.app.cli._base import tolerate_any_console

    raw = io.BytesIO()
    narrow = io.TextIOWrapper(raw, encoding="cp1252")
    real = sys.stdout
    sys.stdout = narrow
    try:
        tolerate_any_console()
        print("Dīvi")
        narrow.flush()
    finally:
        sys.stdout = real
    assert raw.getvalue() == b"D?vi\r\n" or raw.getvalue() == b"D?vi\n"
