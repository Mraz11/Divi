# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The work record of a processing job, so a job stopped half way can be continued.

Every results folder gets ``divi_work.json``: the photo folder, the settings, the engine task and
how far the job got. It is written after each step that takes long (photos prepared, photos sent,
processing finished, results downloaded, results unpacked), so whatever stops the job (the Stop
button, a closed window, a crash, the computer switched off) only loses the step it was in.

Continuing reads the record and runs the same steps again, skipping what is already done:
photos already made smaller are kept; a task the engine still has is followed again (one that
was stopped is restarted on the engine, with the photos it already holds); a downloaded result is
not downloaded again. The photos are checked again every time, as that is quick and the results
need it.
"""

from __future__ import annotations

import json
import shutil
import time
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from avispria.adapters.engine import EngineError, reattach
from avispria.adapters.resize import resize_photo

WORK_FILE = "divi_work.json"
SETTINGS = (
    "preset", "recursive", "resize_mp", "keep_repeats", "profile", "url", "name", "trees",
    "clip_file", "clip_buffer_m",
)  # fmt: skip
STEPS = ("started", "uploaded", "processed", "downloaded", "extracted", "done")
STEP_TEXT = {
    "started": "the photos were checked; they were not all sent to the engine yet",
    "uploaded": "the photos were sent to the engine; processing had not finished",
    "processed": "the engine finished; the results were not downloaded yet",
    "downloaded": "the results were downloaded; they were not unpacked yet",
    "extracted": "the results were unpacked; the quality check and analysis had not finished",
    "done": "everything was finished",
}


class WorkError(ValueError):
    """There is no work to continue here; the message says why in plain words."""


@dataclass
class WorkRecord:
    folder: str
    settings: dict[str, Any]
    step: str = "started"
    task_uuid: str | None = None
    name: str = ""
    started: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)

    def reached(self, step: str) -> bool:
        return STEPS.index(self.step) >= STEPS.index(step)

    def describe(self) -> str:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(self.updated))
        return f"Last worked on {when}: {STEP_TEXT.get(self.step, self.step)}."


def work_file(out_dir: Path) -> Path:
    return out_dir / WORK_FILE


def load_work(out_dir: Path) -> WorkRecord:
    path = work_file(out_dir)
    if not path.is_file():
        raise WorkError(
            f"There is no Dīvi work record ({WORK_FILE}) in {out_dir}. Choose the results folder "
            "of a job that was started with this version of Dīvi."
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        record = WorkRecord(**{k: raw[k] for k in WorkRecord.__dataclass_fields__ if k in raw})
    except (ValueError, TypeError, KeyError) as exc:
        raise WorkError(f"The work record in {out_dir} could not be read: {exc}") from None
    if record.step not in STEPS:
        raise WorkError(f"The work record in {out_dir} has an unknown step {record.step!r}.")
    return record


def save_work(out_dir: Path, record: WorkRecord, step: str | None = None) -> None:
    """Write the record (moving it on to ``step``); a half-written file never replaces it."""
    if step is not None:
        record.step = step
    record.updated = time.time()
    out_dir.mkdir(parents=True, exist_ok=True)
    part = work_file(out_dir).with_suffix(".part")
    part.write_text(json.dumps(asdict(record), indent=2), encoding="utf-8")
    part.replace(work_file(out_dir))


def record_for(
    out_dir: Path, folder: Path, settings: dict[str, Any], name: str, *, resume: bool
) -> WorkRecord:
    """The job's record: the earlier one when continuing the same photos, else a new one."""
    if resume:
        record = load_work(out_dir)
        if Path(record.folder).resolve() == folder.resolve():
            return record
    return WorkRecord(folder=str(folder.resolve()), settings=settings, name=name)


def follow_task(
    node: Any, record: WorkRecord, info: Callable[[str], None], warn: Callable[[str], None]
) -> Any:
    """The engine task of an earlier run if the engine still has it (restarted if it had
    stopped), or None: then the photos are sent again."""
    if record.task_uuid is None:
        return None
    try:
        task, status = reattach(node, record.task_uuid)
    except EngineError as exc:
        warn(f"the engine no longer has the earlier task ({exc}); the photos are sent again")
        record.task_uuid = None
        return None
    info(
        "the engine still has the photos of the earlier run: "
        + ("processing starts again" if status == "restarted" else f"the task is {status}")
    )
    return task


def prepare_photos(
    files: Sequence[Path],
    folder: Path,
    upload_dir: Path,
    max_mp: float,
    info: Callable[[str], None],
) -> list[Path]:
    """Smaller copies of the photos to send; copies made by an earlier run are kept."""
    to_send: list[Path] = []
    resized = kept = 0
    for f in files:
        dst = upload_dir / f.relative_to(folder).as_posix().replace("/", "__")
        if dst.is_file() and dst.stat().st_mtime >= f.stat().st_mtime:
            kept += 1
        else:
            part = dst.with_name(dst.name + ".part")
            resized += resize_photo(f, part, max_mp)[2]
            part.replace(dst)  # only a finished copy has the photo's name
        to_send.append(dst)
    info(f"resized {resized} of {len(files)} photos to at most {max_mp:g} MP")
    if kept:
        info(f"{kept} photos were already prepared by the earlier run and are used as they are")
    return to_send


def extract(zip_path: Path, dest: Path, unsafe: Callable[[str], Exception]) -> list[Path]:
    """Unpack the results archive; a name that would land outside ``dest`` stops it."""
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    out: list[Path] = []
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            target = (dest / member.filename).resolve()
            if not target.is_relative_to(root):
                raise unsafe(f"unsafe path in results archive: {member.filename}")
            if member.is_dir():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            out.append(target)
    return out


def unpacked(results_dir: Path) -> list[Path]:
    """The files already unpacked into ``results_dir`` (an earlier run's)."""
    return sorted(p for p in results_dir.rglob("*") if p.is_file())
