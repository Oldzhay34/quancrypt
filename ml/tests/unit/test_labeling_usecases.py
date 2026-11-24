"""Export, import and resolution of a label batch, against fakes of the outbound ports."""

from __future__ import annotations

from pathlib import Path

import pytest

from quancrypt_ml.domain.labels import (
    CONTEXT_NO_LOCATION,
    CONTEXT_OK,
    CONTEXT_UNAVAILABLE,
    FIRST,
    SECOND,
    SourceLocation,
)
from quancrypt_ml.port.inbound.labeling import ExportCommand, ImportCommand, LabelingError, ResolveCommand
from quancrypt_ml.usecase.export_label_batch_service import ExportLabelBatchService
from quancrypt_ml.usecase.import_labels_service import ImportLabelsService
from quancrypt_ml.usecase.labeling_report_writer import LabelingReporter
from quancrypt_ml.usecase.resolve_disagreements_service import ResolveDisagreementsService
from tests.support.fakes import (
    FakeCandidates,
    FakeFiles,
    FakeLabelStore,
    FakeLocator,
    FakeReports,
    FakeSnippets,
    FixedClock,
    SequentialIds,
    candidate,
)

OUT = Path("labeling/batch_001.csv")
REPORT = Path("reports/labeling.md")
DIS = Path("labeling/batch_001_disagreements.csv")


class World:
    def __init__(self, pool: int = 20, snippets: FakeSnippets | None = None) -> None:
        self.candidates = FakeCandidates([candidate(n) for n in range(pool)])
        ids = [c.finding_id for c in self.candidates.rows]
        self.locator = FakeLocator(
            {f: SourceLocation("/corpus/acme__shop", f"src/F{i}.java", 10 + i) for i, f in enumerate(ids[:-2])}
            | {ids[-2]: SourceLocation("/corpus/acme__shop", "certs/server.crt.pem", None)}
        )
        self.snippets = snippets or FakeSnippets()
        self.store = FakeLabelStore()
        self.files = FakeFiles()
        self.reports = FakeReports()
        self.clock = FixedClock()
        reporter = LabelingReporter(self.store, self.candidates, self.files, self.reports)
        self.export = ExportLabelBatchService(
            self.candidates, self.locator, self.snippets, self.store, self.files, self.clock, SequentialIds()
        )
        self.importer = ImportLabelsService(self.store, self.files, reporter, self.clock)
        self.resolver = ResolveDisagreementsService(self.store, self.files, reporter, self.clock)

    def exported(self, size: int = 10, double: int = 4) -> None:
        self.export.execute(ExportCommand("batch_001", OUT, size, double, 42))

    def fill(self, path: Path, labeler: str, label_of: dict[str, str] | None = None, only_double: bool = False) -> None:
        stored = self.store.batch("batch_001")
        assert stored is not None
        self.files.inputs[path] = [
            {"finding_id": f, "label": (label_of or {}).get(f, "HIGH"), "labeler": labeler, "notes": ""}
            for f, double in sorted(stored.items.items())
            if double or not only_double
        ]


def test_the_export_stores_the_batch_and_writes_every_row_with_its_context() -> None:
    world = World(pool=20)
    result = world.export.execute(ExportCommand("batch_001", OUT, 20, 6, 42))
    rows = world.files.batches[OUT]
    assert (result.sampled, result.double, len(rows)) == (20, 6, 20)
    statuses = [r.context_status for r in rows]
    # 18 locations with a line, one whole-file location, one finding without a location.
    assert statuses.count(CONTEXT_OK) == 18 and statuses.count(CONTEXT_NO_LOCATION) == 2
    stored = world.store.batch("batch_001")
    assert stored is not None and stored.size == 20 and stored.double_size == 6
    with_context = next(r for r in rows if r.context_status == CONTEXT_OK)
    assert len(with_context.context) == 11  # ±5 lines


def test_a_location_the_analyzer_cannot_read_is_marked_and_the_export_goes_on() -> None:
    world = World(pool=5, snippets=FakeSnippets(missing={"src/F0.java"}))
    result = world.export.execute(ExportCommand("batch_001", OUT, 5, 1, 42))
    assert result.context_unavailable == 1
    assert [r.context_status for r in world.files.batches[OUT]].count(CONTEXT_UNAVAILABLE) == 1


def test_an_unreachable_analyzer_stops_the_export_before_anything_is_stored() -> None:
    world = World(pool=5, snippets=FakeSnippets(down=True))
    with pytest.raises(LabelingError, match="analyzer cannot be reached"):
        world.export.execute(ExportCommand("batch_001", OUT, 5, 1, 42))
    assert world.store.batches == {} and world.files.batches == {}


def test_a_batch_is_exported_once() -> None:
    world = World()
    world.exported()
    with pytest.raises(LabelingError, match="already exists"):
        world.exported()


def test_an_empty_warehouse_and_too_many_doubles_are_refused() -> None:
    world = World(pool=2)
    world.candidates.rows = []
    with pytest.raises(LabelingError, match="no finding to label"):
        world.exported()
    with pytest.raises(LabelingError, match="cannot exceed"):
        world.export.execute(ExportCommand("batch_002", OUT, 5, 6, 42))


def test_a_file_with_one_bad_row_stores_nothing() -> None:
    world = World()
    world.exported()
    world.fill(Path("first.csv"), "olcay")
    world.files.inputs[Path("first.csv")][3]["label"] = "SEVERE"
    result = world.importer.execute(ImportCommand("batch_001", FIRST, Path("first.csv"), REPORT, DIS))
    assert result.stored == 0 and [i.row for i in result.issues] == [
        5,
        0,
    ]  # the bad row and the record it left unlabelled
    stored = world.store.batch("batch_001")
    assert stored is not None and world.store.labels(stored.id, FIRST) == {}


def test_both_labellers_give_kappa_a_report_and_a_disagreement_file() -> None:
    world = World()
    world.exported(size=10, double=4)
    stored = world.store.batch("batch_001")
    assert stored is not None
    doubles = sorted(f for f, d in stored.items.items() if d)
    world.fill(Path("first.csv"), "olcay")
    first = world.importer.execute(ImportCommand("batch_001", FIRST, Path("first.csv"), REPORT, DIS))
    assert (first.stored, first.kappa) == (10, None)
    world.fill(Path("second.csv"), "arkadaş", {doubles[0]: "LOW", doubles[1]: "LOW"}, only_double=True)
    second = world.importer.execute(ImportCommand("batch_001", SECOND, Path("second.csv"), REPORT, DIS))
    assert (second.stored, second.pairs, second.disagreements) == (4, 4, 2)
    assert second.kappa is not None
    assert [r["finding_id"] for r in world.files.written[DIS]] == doubles[:2]
    assert "Cohen kappa" in world.reports.texts[REPORT]


def test_a_reimport_replaces_the_labels_of_that_labeller() -> None:
    world = World()
    world.exported()
    world.fill(Path("first.csv"), "olcay")
    world.importer.execute(ImportCommand("batch_001", FIRST, Path("first.csv"), REPORT, DIS))
    stored = world.store.batch("batch_001")
    assert stored is not None
    world.fill(Path("first.csv"), "olcay", dict.fromkeys(stored.items, "LOW"))
    world.importer.execute(ImportCommand("batch_001", FIRST, Path("first.csv"), REPORT, DIS))
    assert set(world.store.labels(stored.id, FIRST).values()) == {"LOW"}


def test_resolutions_are_stored_and_the_open_count_drops() -> None:
    world = World()
    world.exported(size=10, double=4)
    stored = world.store.batch("batch_001")
    assert stored is not None
    doubles = sorted(f for f, d in stored.items.items() if d)
    world.fill(Path("first.csv"), "olcay")
    world.importer.execute(ImportCommand("batch_001", FIRST, Path("first.csv"), REPORT, DIS))
    world.fill(Path("second.csv"), "arkadaş", {doubles[0]: "LOW", doubles[1]: "LOW"}, only_double=True)
    world.importer.execute(ImportCommand("batch_001", SECOND, Path("second.csv"), REPORT, DIS))
    world.files.inputs[DIS] = [
        {"finding_id": doubles[0], "label": "MEDIUM", "resolved_by": "olcay", "notes": "TLS ama ağ yolu yok"},
        {"finding_id": doubles[1], "label": "", "resolved_by": "", "notes": ""},
    ]
    result = world.resolver.execute(ResolveCommand("batch_001", DIS, REPORT))
    assert (result.stored, result.open_disagreements) == (1, 1)
    assert world.store.resolutions(stored.id) == {doubles[0]: "MEDIUM"}
    assert "| MEDIUM |" in world.reports.texts[REPORT]


def test_resolving_needs_both_labellers_and_a_known_batch() -> None:
    world = World()
    with pytest.raises(LabelingError, match="not stored"):
        world.resolver.execute(ResolveCommand("batch_001", DIS, REPORT))
    world.exported()
    with pytest.raises(LabelingError, match="no double-labelled record"):
        world.resolver.execute(ResolveCommand("batch_001", DIS, REPORT))
    with pytest.raises(LabelingError, match="FIRST or SECOND"):
        world.importer.execute(ImportCommand("batch_001", "THIRD", Path("x.csv"), REPORT, DIS))


def test_the_report_counts_labels_the_warehouse_no_longer_has() -> None:
    world = World()
    world.exported()
    world.fill(Path("first.csv"), "olcay")
    world.candidates.gone = {world.candidates.rows[0].finding_id, world.candidates.rows[1].finding_id}
    world.importer.execute(ImportCommand("batch_001", FIRST, Path("first.csv"), REPORT, DIS))
    stored = world.store.batch("batch_001")
    assert stored is not None
    gone_in_batch = len(world.candidates.gone & set(stored.items))
    assert f"artık bulunmayan etiketli bulgu: {gone_in_batch}." in world.reports.texts[REPORT]
