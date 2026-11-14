# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""`avispria process`: photo folder -> checked -> engine -> results + provenance."""

from __future__ import annotations

import math
import re
import shutil
import statistics
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Protocol

from avispria.adapters import system_probe
from avispria.adapters.engine import (
    EngineInfo,
    TaskOutcome,
    connect,
    describe,
    download_results,
    submit,
    wait,
)
from avispria.adapters.photos import photo_files, scan_photos
from avispria.app.canopy_workflow import CANOPY_DIR
from avispria.app.capture_workflow import camera_chooser
from avispria.app.clip_workflow import cut_step
from avispria.app.inventory_workflow import TreeInputs
from avispria.app.process_record import sun_record, write_provenance
from avispria.app.process_work import (
    SETTINGS,
    WorkError,
    extract,
    follow_task,
    load_work,
    prepare_photos,
    record_for,
    save_work,
    unpacked,
)
from avispria.app.result_quality import read_stats, report_quality, summarize_result
from avispria.app.surface_workflow import ANALYSIS_DIR, analysis_step
from avispria.core.canopy import CanopyStats
from avispria.core.capture import analyse_capture
from avispria.core.feasibility import Assessment, JobSpec, SystemSpec, assess, gb
from avispria.core.processing import (
    DEFAULT_RESIZE_MP,
    MIN_PHOTOS,
    PRESETS,
    PresetName,
    build_options,
    effective_gsd_cm,
)
from avispria.core.quality import ReconstructionSummary
from avispria.core.safety import Issue
from avispria.core.sequence import analyse_sequence
from avispria.core.sun import local_offset, photo_light

GB = 1024**3
UPLOAD_DIR = ".avispria-upload"
DEFAULT_POLL_S = 3.0
GENERIC_FOLDER = re.compile(r"^(images?|photos?|pictures?|imgs?|dcim|\d{3}media)$", re.IGNORECASE)


def task_name(folder: Path) -> str:
    """Folder name, or its parent's when the folder has a generic name like 'images'."""
    path = folder.resolve()
    for part in (path, *path.parents):
        if part.name and not GENERIC_FOLDER.match(part.name):
            return part.name
    return "divi"


class Reporter(Protocol):
    def step(self, title: str) -> None: ...
    def info(self, text: str) -> None: ...
    def warn(self, text: str) -> None: ...
    def upload(self, percent: float) -> None: ...
    def progress(self, percent: float, status: str) -> None: ...


class ProcessBlockedError(RuntimeError):
    """Processing was not started; ``assessment`` holds alternatives if it is a capacity issue."""

    def __init__(self, reason: str, assessment: Assessment | None = None) -> None:
        super().__init__(reason)
        self.assessment = assessment


@dataclass(frozen=True)
class ProcessRequest:
    folder: Path
    out_dir: Path
    preset: PresetName = "standard"
    recursive: bool = False
    resize_mp: float | None = DEFAULT_RESIZE_MP
    force: bool = False
    keep_repeats: bool = False  # True: also send photos taken while hovering or in a repeat pass
    profile: str = "forest"  # what was mapped: forest, farm or urban (core/profiles.py)
    url: str | None = None
    token: str | None = None
    name: str | None = None
    poll_s: float | None = None  # None: DEFAULT_POLL_S
    cancel: threading.Event | None = None  # set it to stop a running job
    resume: bool = False  # continue the job recorded in out_dir (see process_work.py)
    trees: TreeInputs = field(default_factory=TreeInputs)  # inputs of the tree inventory
    clip_file: Path | None = None  # cut the stitched maps to this area (KML, SHP, ...)
    clip_buffer_m: float = 0.0


@dataclass(frozen=True)
class ProcessOutcome:
    completed: bool
    task: TaskOutcome
    zip_path: Path | None
    results_dir: Path | None
    provenance_path: Path


def _label(path: Path, req: ProcessRequest) -> str:
    """The name a photo has in its metadata record (see ``scan_photos``)."""
    return path.relative_to(req.folder).as_posix() if req.recursive else path.name


def _extract(zip_path: Path, dest: Path) -> list[Path]:
    return extract(zip_path, dest, ProcessBlockedError)


def request_from_work(
    out_dir: Path,
    *,
    token: str | None = None,
    cancel: threading.Event | None = None,
    force: bool = False,
) -> ProcessRequest:
    """The request that continues the job recorded in ``out_dir``, with its own settings."""
    record = load_work(out_dir)
    folder = Path(record.folder)
    if not folder.is_dir():
        raise WorkError(
            f"The photo folder of this job is not there any more: {folder}. Put it back where it "
            "was (or connect the drive it is on) to continue."
        )
    settings: dict[str, Any] = {k: v for k, v in record.settings.items() if k in SETTINGS}
    if settings.get("clip_file"):
        settings["clip_file"] = Path(settings["clip_file"])
    if "trees" in settings:
        settings["trees"] = TreeInputs.from_record(settings["trees"])
    return ProcessRequest(
        folder=folder,
        out_dir=out_dir,
        token=token,
        cancel=cancel,
        force=force,
        resume=True,
        **settings,
    )


def _engine(
    req: ProcessRequest, rep: Reporter, find_node: Callable[[], object]
) -> tuple[object, EngineInfo]:
    url, token = req.url, req.token
    if url is None:
        local = find_node()
        if local is None:
            raise ProcessBlockedError(
                "no processing engine was found. Start WebODM (its Windows app, or its Docker "
                "version, which listens at http://localhost:3000), or give the engine address "
                "in the advanced settings"
            )
        url, token = local.url, token or local.token  # type: ignore[attr-defined]
        if local.pid:  # type: ignore[attr-defined]
            rep.info(f"using WebODM's local engine at {url} (token read from the running engine)")
        else:
            rep.info(f"using the processing node at {url}")
    node = connect(url, token)
    info = describe(node)
    rep.info(f"{info.engine} {info.engine_version}, {info.cpu_cores or '?'} cores")
    if info.queue:
        rep.warn(f"the engine already has {info.queue} task(s); this one will wait its turn")
    return node, info


def run_process(
    req: ProcessRequest,
    rep: Reporter,
    *,
    probe: Callable[[Path], SystemSpec] | None = None,
    find_node: Callable[[], object] | None = None,
) -> ProcessOutcome:
    probe = probe or system_probe.probe_system
    find_node = find_node or system_probe.find_engine
    started = time.time()
    name = req.name or task_name(req.folder)
    settings = {k: getattr(req, k) for k in SETTINGS} | {
        "trees": req.trees.record(),
        "clip_file": None if req.clip_file is None else str(req.clip_file),
    }
    record = record_for(req.out_dir, req.folder, settings, name, resume=req.resume)
    name = record.name or name
    if req.resume:
        rep.info(f"continuing the earlier job. {record.describe()}")

    rep.step("Photos")
    files = photo_files(req.folder, recursive=req.recursive)
    if len(files) < MIN_PHOTOS:
        raise ProcessBlockedError(f"found {len(files)} photo(s); at least {MIN_PHOTOS} are needed")
    records, skipped = scan_photos(req.folder, recursive=req.recursive)
    sizes = [r.width_px * r.height_px for r in records if r.width_px and r.height_px]
    native_mp = statistics.median(sizes) / 1e6 if sizes else 0.0
    input_gb = sum(f.stat().st_size for f in files) / GB
    rep.info(f"{len(files)} photos, {native_mp:.1f} MP, {input_gb:.2f} GB")
    for file_name, reason in skipped:
        rep.warn(f"{file_name}: unreadable metadata ({reason})")
    sequence = analyse_sequence(records)
    light = photo_light(records, local_offset())
    leave_out = set() if req.keep_repeats else set(sequence.leave_out)
    if leave_out:
        files = [f for f in files if _label(f, req) not in leave_out]
        records = [r for r in records if r.name not in leave_out]
        rep.info(f"left out {len(leave_out)} repeated photos; {len(files)} photos go to the engine")
        if len(files) < MIN_PHOTOS:
            raise ProcessBlockedError(f"only {len(files)} photo(s) left after the repeats")

    rep.step("Capture check")
    notes: list[Issue] = []
    qa = analyse_capture(records, camera_chooser(None, notes))
    if "area_pct_min_views" in qa.stats:
        rep.info(
            f"GSD {qa.stats['gsd_cm_median']:.2f} cm/px, "
            f"{qa.stats['area_pct_min_views']:.0f}% of the area seen by 3+ photos"
        )
    # QA is advisory here: an assessment that could not be made is a warning, not an error
    qa_issues = [
        replace(i, level="warning") for i in [*qa.issues, *notes, *sequence.issues, *light.issues]
    ]
    for issue in qa_issues:
        rep.warn(f"{issue.code}: {issue.message}")

    rep.step("Processing engine")
    node, info = _engine(req, rep, find_node)

    rep.step("This computer")
    system = probe(req.out_dir if req.out_dir.exists() else req.out_dir.parent)
    has_raw = any(f.suffix.lower() not in (".jpg", ".jpeg") for f in files)
    processing_mp = (
        native_mp if (req.resize_mp is None or has_raw) else min(native_mp, req.resize_mp)
    )
    if has_raw and req.resize_mp is not None:
        rep.warn(
            "raw (DNG) photos are sent at full size; JPEG photos give more predictable results"
        )
    if native_mp > 1.5 * processing_mp > 0:
        rep.warn(
            f"the photos are {native_mp:.0f} MP but are processed at {processing_mp:.0f} MP: the "
            f"maps will be about {math.sqrt(native_mp / processing_mp):.1f}x coarser than the "
            "photos allow (choose a larger photo size if this computer has the memory, or fly "
            "12 MP photos next time)"
        )
    job = JobSpec(len(files), max(native_mp, 0.1), input_gb)
    assessment = assess(system, job, processing_mp)
    rep.info(f"needs about {gb(assessment.ram_gb)} GB memory, {gb(assessment.disk_gb)} GB disk")
    for reason in assessment.reasons:
        rep.warn(reason)
    if assessment.verdict == "not-possible" and not req.force and record.task_uuid is None:
        raise ProcessBlockedError(
            "this computer cannot process these photos as they are", assessment
        )

    gsd = qa.stats.get("gsd_cm_median")
    sent_gsd = (
        None
        if gsd is None
        else effective_gsd_cm(gsd, native_mp=native_mp, processing_mp=processing_mp)
    )
    opts = build_options(
        req.preset,
        info.options,
        electronic_shutter=any(r.shutter == "Electronic" for r in records),
        gsd_cm=sent_gsd,
    )
    rep.info(f"preset '{req.preset}': {PRESETS[req.preset].description}")
    for note in opts.notes:
        rep.info(note)
    if opts.dropped:
        rep.warn(f"not supported by this engine, left out: {', '.join(opts.dropped)}")

    upload_dir = req.out_dir / UPLOAD_DIR
    save_work(req.out_dir, record)
    task = None if record.reached("downloaded") else follow_task(node, record, rep.info, rep.warn)
    if task is None and not record.reached("downloaded"):
        to_send = files
        if req.resize_mp is not None:
            rep.step("Preparing photos")
            to_send = prepare_photos(files, req.folder, upload_dir, req.resize_mp, rep.info)
        rep.step("Uploading")
        task = submit(node, to_send, opts.options, name, rep.upload)
        record.task_uuid = getattr(task, "uuid", None)
        save_work(req.out_dir, record, "uploaded")
        shutil.rmtree(upload_dir, ignore_errors=True)  # the engine has them now
    zip_path = req.out_dir / f"{name}_all.zip"
    results_dir: Path | None = req.out_dir / "results"
    zip_or_none: Path | None = zip_path
    outputs: list[Path] = []
    reconstruction: ReconstructionSummary | None = None
    canopy: CanopyStats | None = None
    if task is not None:
        rep.step("Processing")
        outcome = wait(
            task,
            rep.progress,
            interval=req.poll_s or DEFAULT_POLL_S,
            should_cancel=None if req.cancel is None else req.cancel.is_set,
        )
    else:  # an earlier run downloaded the results
        outcome = TaskOutcome(record.task_uuid or "", True, "COMPLETED", "", 0.0, [])
    if not outcome.completed:
        zip_or_none = results_dir = None
    else:
        if not record.reached("processed"):
            save_work(req.out_dir, record, "processed")
        if not (record.reached("downloaded") and zip_path.is_file()):
            rep.step("Downloading results")
            downloaded = download_results(task, req.out_dir)
            downloaded.replace(zip_path)
            save_work(req.out_dir, record, "downloaded")
        assert results_dir is not None
        if record.reached("extracted") and results_dir.is_dir():
            outputs = unpacked(results_dir)
        else:
            outputs = _extract(zip_path, results_dir)
        if req.clip_file is not None:
            cut_step(results_dir, req.clip_file, req.clip_buffer_m, rep.step, rep.info, rep.warn)
            save_work(req.out_dir, record, "extracted")
        stats = read_stats(results_dir)
        if stats is not None:
            rep.step("Result quality")
            reconstruction = summarize_result(
                stats, records, results_dir, sent_gsd, native_mp, processing_mp
            )
            report_quality(reconstruction, rep.info, rep.warn)
        rep.step("Analysis")
        analysis = analysis_step(
            results_dir, req.profile, rep.info, rep.warn, sun_record(light), req.trees
        )
        if analysis is not None:
            canopy = analysis.canopy.stats
            for folder in (CANOPY_DIR, ANALYSIS_DIR):
                outputs = sorted({*outputs, *(results_dir / folder).iterdir()})
        save_work(req.out_dir, record, "done")

    provenance_path = write_provenance(
        out_dir=req.out_dir,
        started=started,
        name=name,
        preset=req.preset,
        resize_mp=req.resize_mp,
        outcome=outcome,
        info=info,
        opts=opts,
        system=system,
        assessment=assessment,
        reconstruction=reconstruction,
        canopy=canopy,
        qa=qa,
        qa_issues=qa_issues,
        files=files,
        outputs=outputs,
        left_out=sorted(leave_out),
        sun=light,
        profile=req.profile,
    )
    return ProcessOutcome(outcome.completed, outcome, zip_or_none, results_dir, provenance_path)
