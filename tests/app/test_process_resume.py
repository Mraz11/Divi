# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A processing job that stopped half way is continued from its results folder."""

import json
import threading
from pathlib import Path

import pytest
from typer.testing import CliRunner

from avispria.adapters import system_probe
from avispria.app import process_workflow
from avispria.app.cli import app
from avispria.app.process_work import (
    WORK_FILE,
    WorkError,
    load_work,
    prepare_photos,
    save_work,
)
from avispria.app.process_workflow import ProcessRequest, request_from_work, run_process
from avispria.core.feasibility import SystemSpec
from fakes.nodeodx import fake_engine
from photobuild import make_dji_jpeg

runner = CliRunner()
PC = SystemSpec("Windows 11", 12, 16.0, 8.0, 15.0, 200.0)


def photo_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "flight"
    folder.mkdir()
    for i in range(6):
        make_dji_jpeg(
            folder / f"DJI_{i:04d}.JPG",
            size=(800, 600),
            lat=22.2820 + (i % 3) * 0.0001,
            lon=91.7790 + (i // 3) * 0.0002,
        )
    return folder


def _patch(monkeypatch: pytest.MonkeyPatch, port: int, token: str) -> None:
    local = system_probe.LocalNode(f"http://127.0.0.1:{port}", token, 99, None)
    monkeypatch.setattr(process_workflow.system_probe, "find_local_node", lambda: local)
    monkeypatch.setattr(process_workflow.system_probe, "probe_system", lambda path: PC)
    monkeypatch.setattr(process_workflow, "DEFAULT_POLL_S", 0.05)


class Reporter:
    def __init__(self, stop: threading.Event | None = None) -> None:
        self.stop, self.lines = stop, []  # type: ignore[var-annotated]

    def step(self, title: str) -> None:
        self.lines.append(title)

    def info(self, text: str) -> None:
        self.lines.append(text)

    def warn(self, text: str) -> None:
        self.lines.append(text)

    def upload(self, percent: float) -> None: ...

    def progress(self, percent: float, status: str) -> None:
        if self.stop is not None:
            self.stop.set()  # Stop is pressed as soon as processing starts


def stopped_job(tmp_path: Path, port: int, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder, out = photo_folder(tmp_path), tmp_path / "out"
    _patch(monkeypatch, port, "t")
    stop = threading.Event()
    request = ProcessRequest(folder=folder, out_dir=out, preset="fast", resize_mp=0.12, cancel=stop)
    assert not run_process(request, Reporter(stop)).completed
    return out


def test_a_stopped_job_continues_on_the_engine_without_sending_the_photos_again(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    with fake_engine("t", outcome="hang") as (port, state):
        out = stopped_job(tmp_path, port, monkeypatch)
        record = load_work(out)
        assert record.step == "uploaded" and record.task_uuid == state.uuid
        assert record.settings["preset"] == "fast" and record.settings["resize_mp"] == 0.12
        assert not (out / ".avispria-upload").exists()  # the engine has the photos
        reporter = Reporter()
        outcome = run_process(request_from_work(out), reporter)
        assert outcome.completed and state.restarts == 1 and state.uploads == 6
    assert any("processing starts again" in line for line in reporter.lines)
    assert load_work(out).step == "done" and (out / "results").is_dir()


def test_downloaded_results_are_not_downloaded_again(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    folder, out = photo_folder(tmp_path), tmp_path / "out"
    with fake_engine("t") as (port, state):
        _patch(monkeypatch, port, "t")
        run_process(ProcessRequest(folder=folder, out_dir=out, resize_mp=None), Reporter())
        assert state.downloads == 1
        record = load_work(out)
        save_work(out, record, "downloaded")  # as if it stopped before unpacking
        import shutil

        shutil.rmtree(out / "results")
        outcome = run_process(request_from_work(out), Reporter())
        assert outcome.completed and state.downloads == 1 and state.uploads == 6
    assert (out / "results" / "odm_report" / "stats.json").is_file()


def test_a_task_the_engine_no_longer_has_is_sent_again(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    with fake_engine("t", outcome="hang") as (port, state):
        out = stopped_job(tmp_path, port, monkeypatch)
        record = load_work(out)
        record.task_uuid = "gone-from-the-engine"
        save_work(out, record)
        state.outcome, state.cancelled, state.polls = "complete", False, 0  # a fresh task
        reporter = Reporter()
        assert run_process(request_from_work(out), reporter).completed
        assert state.uploads == 12  # sent twice
    assert any("no longer has the earlier task" in line for line in reporter.lines)


def test_photos_made_smaller_before_a_stop_are_kept(tmp_path: Path) -> None:
    folder = photo_folder(tmp_path)
    files = sorted(folder.iterdir())
    said: list[str] = []
    first = prepare_photos(files, folder, tmp_path / "up", 0.12, said.append)
    (tmp_path / "up" / first[0].name).unlink()  # this one had not been made yet
    prepare_photos(files, folder, tmp_path / "up", 0.12, said.append)
    assert "5 photos were already prepared" in said[-1]
    assert not list((tmp_path / "up").glob("*.part"))


def test_there_must_be_a_record_and_the_photos(tmp_path: Path) -> None:
    with pytest.raises(WorkError, match="no Dīvi work record"):
        load_work(tmp_path)
    (tmp_path / WORK_FILE).write_text("{not json", encoding="utf-8")
    with pytest.raises(WorkError, match="could not be read"):
        load_work(tmp_path)
    record = {"folder": str(tmp_path / "moved"), "settings": {}, "step": "uploaded"}
    (tmp_path / WORK_FILE).write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(WorkError, match="not there any more"):
        request_from_work(tmp_path)
    (tmp_path / WORK_FILE).write_text(json.dumps(record | {"step": "flying"}), encoding="utf-8")
    with pytest.raises(WorkError, match="unknown step"):
        load_work(tmp_path)


def test_the_resume_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    result = runner.invoke(app, ["resume", str(tmp_path)])
    assert result.exit_code == 1 and "no Dīvi work record" in result.output
    with fake_engine("t", outcome="hang") as (port, state):
        out = stopped_job(tmp_path, port, monkeypatch)
        result = runner.invoke(app, ["resume", str(out)])
    assert result.exit_code == 0, result.output
    assert "continuing the earlier job" in result.output and state.restarts == 1


def test_the_maps_are_cut_after_stitching_and_the_cut_survives_a_resume(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    folder, out = photo_folder(tmp_path), tmp_path / "out"
    area = tmp_path / "area.geojson"
    ring = [[91.7789, 22.2819], [91.7795, 22.2819], [91.7795, 22.2823], [91.7789, 22.2823]]
    area.write_text(json.dumps({"type": "Polygon", "coordinates": [[*ring, ring[0]]]}), "utf-8")
    with fake_engine("t", dsm_elevation=130.0) as (port, _):
        _patch(monkeypatch, port, "t")
        reporter = Reporter()
        request = ProcessRequest(
            folder=folder, out_dir=out, resize_mp=None, clip_file=area, clip_buffer_m=2.0
        )
        assert run_process(request, reporter).completed
    assert any(line.startswith("cut to area.geojson") for line in reporter.lines)
    assert (out / "results" / "odm_dem" / "dsm.full.tif").is_file()
    assert not any("were not cut" in line for line in reporter.lines)
    again = request_from_work(out)
    assert again.clip_file == area
    assert again.clip_buffer_m == 2.0
