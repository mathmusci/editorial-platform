import time
from pathlib import Path

from editorial.models import ProcessingRunOptions
from editorial.processing import ProcessingRunCoordinator, ProcessingRunService

CONFIG = Path("tests/fixtures/bis/publication.yaml")


def _wait_for_terminal(service, run_id, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = service.runs.get(run_id)
        if run is not None and not run.active:
            return run
        time.sleep(0.01)
    raise AssertionError(f"Processing run {run_id} did not finish")


def test_processing_service_records_ingest_extract_and_evaluate_runs(tmp_path):
    service = ProcessingRunService(tmp_path / "processing.sqlite")

    ingest = service.create_run("ingest", CONFIG)
    service.execute(ingest.id)
    extract = service.create_run("extract", CONFIG)
    service.execute(extract.id)
    evaluate = service.create_run("evaluate", CONFIG)
    service.execute(evaluate.id)

    stored_ingest = service.runs.get(ingest.id)
    stored_extract = service.runs.get(extract.id)
    stored_evaluate = service.runs.get(evaluate.id)
    assert stored_ingest is not None
    assert stored_ingest.status == "completed"
    assert stored_ingest.article_count == 2
    assert stored_ingest.stored_operations == 2
    assert stored_ingest.result["fetched"] == 2
    assert stored_extract is not None
    assert stored_extract.status == "completed"
    assert stored_extract.total_operations == 2
    assert stored_extract.stored_operations == 2
    assert stored_extract.current_processor == "Reading time"
    assert stored_evaluate is not None
    assert stored_evaluate.status == "completed"
    assert stored_evaluate.total_operations == 2
    assert stored_evaluate.stored_operations == 2
    assert stored_evaluate.current_processor == "BIS relevance"
    events = service.events.list(
        artefact_type="processing_run", artefact_id=stored_extract.id
    )
    assert [event.event_type for event in events] == [
        "processing-run-queued",
        "processing-run-started",
        "processing-run-completed",
    ]


def test_processing_service_records_selection_and_resumable_skips(tmp_path):
    service = ProcessingRunService(tmp_path / "processing.sqlite")
    ingest = service.create_run("ingest", CONFIG)
    service.execute(ingest.id)
    initial = service.create_run(
        "extract", CONFIG, ProcessingRunOptions(limit=1, offset=1)
    )
    service.execute(initial.id)
    resumed = service.create_run(
        "extract",
        CONFIG,
        ProcessingRunOptions(limit=1, offset=1, missing_only=True),
    )
    service.execute(resumed.id)

    stored = service.runs.get(resumed.id)
    assert stored is not None
    assert stored.options.limit == 1
    assert stored.options.offset == 1
    assert stored.completed_operations == 1
    assert stored.stored_operations == 0
    assert stored.skipped_operations == 1


def test_processing_service_records_failure_without_exposing_traceback(tmp_path):
    config_path = tmp_path / "invalid-processor.yaml"
    config_path.write_text(
        """
publication:
  name: Broken publication
extractors:
  - type: unsupported
""".strip(),
        encoding="utf-8",
    )
    service = ProcessingRunService(tmp_path / "processing.sqlite")
    run = service.create_run("extract", config_path)

    result = service.execute(run.id, raise_on_failure=False)

    stored = service.runs.get(run.id)
    assert result is None
    assert stored is not None
    assert stored.status == "failed"
    assert "Unsupported extractor type" in stored.error_message
    assert "Traceback" not in stored.error_message
    assert stored.finished_at is not None


def test_processing_service_rejects_configuration_changed_after_queue(tmp_path):
    config_path = tmp_path / "publication.yaml"
    config_path.write_text(CONFIG.read_text(encoding="utf-8"), encoding="utf-8")
    service = ProcessingRunService(tmp_path / "processing.sqlite")
    run = service.create_run("ingest", config_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8") + "\n# changed\n",
        encoding="utf-8",
    )

    service.execute(run.id, raise_on_failure=False)

    stored = service.runs.get(run.id)
    assert stored is not None
    assert stored.status == "failed"
    assert stored.error_message == (
        "Configuration changed after this processing run was queued"
    )


def test_processing_coordinator_runs_in_background_and_persists_status(tmp_path):
    service = ProcessingRunService(tmp_path / "processing.sqlite")
    coordinator = ProcessingRunCoordinator(service)

    run = coordinator.start("ingest", CONFIG)
    completed = _wait_for_terminal(service, run.id)

    assert completed.status == "completed"
    assert completed.stored_operations == 2
    coordinator.shutdown()


def test_processing_coordinator_marks_unfinished_runs_interrupted(tmp_path):
    service = ProcessingRunService(tmp_path / "processing.sqlite")
    queued = service.create_run("extract", CONFIG)

    coordinator = ProcessingRunCoordinator(service)

    interrupted = service.runs.get(queued.id)
    assert interrupted is not None
    assert interrupted.status == "interrupted"
    assert interrupted.finished_at is not None
    coordinator.shutdown()
