"""Milestone 8: Data Persistence unit tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from axiomra.backtest.walkforward import run_walk_forward
from axiomra.data.instruments import CorporateAction, Instrument, InstrumentMaster
from axiomra.data.persistence.parquet import ParquetDatasetRepository
from axiomra.data.snapshot import AdjustmentMode, create_snapshot
from axiomra.data.universe import IndexMembership, Universe
from axiomra.domain.market import Bar
from axiomra.quant.trainer import build_training_frame
from axiomra.storage.features import FeatureRepository
from axiomra.storage.local import LocalArtifactStore
from axiomra.storage.manifest import UnsupportedSchemaError


def _sample_dataset(tmp_path):
    bars_aaa = [
        Bar(
            symbol="AAA.NS",
            timestamp=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=i),
            open=100.0 + i,
            high=101.0 + i,
            low=99.0 + i,
            close=100.0 + i,
            volume=10000.0,
        )
        for i in range(60)
    ]

    uni = Universe(name="NIFTY 50", version="v1", as_of=datetime.now(UTC), members=["AAA.NS"])
    m1 = IndexMembership(
        instrument_id="inst-1",
        symbol="AAA.NS",
        index_name="NIFTY 50",
        from_date=datetime(2020, 1, 1, tzinfo=UTC),
    )
    action = CorporateAction(
        instrument_id="inst-1",
        action_type="DIVIDEND",
        ex_date=datetime(2024, 1, 5, tzinfo=UTC),
        amount=5.0,
        currency="INR",
    )
    snap = create_snapshot(
        universe=uni,
        bars={"AAA.NS": bars_aaa},
        data_version="d1",
        actions=[action],
        adjustment_mode=AdjustmentMode.TOTAL_RETURN,
        memberships=[m1],
    )
    master = InstrumentMaster()
    master.upsert(
        Instrument(
            instrument_id="inst-1",
            symbol="AAA.NS",
            active_from=datetime(2020, 1, 1, tzinfo=UTC),
        )
    )
    master.add_action(action)
    store = LocalArtifactStore(root_dir=tmp_path / "artifacts")
    repo = ParquetDatasetRepository(store=store)
    return snap, master, repo


def test_dataset_save_load_preserves_all_bars(tmp_path):
    snap, master, repo = _sample_dataset(tmp_path)
    manifest = repo.save(snap, master)
    restored = repo.load(manifest.dataset_id)

    assert restored.snapshot.bar_count() == snap.bar_count()
    assert "AAA.NS" in restored.snapshot.bars
    assert len(restored.snapshot.bars["AAA.NS"]) == 60

    assert restored.snapshot.bars["AAA.NS"][0].close == snap.bars["AAA.NS"][0].close


def test_instrument_ids_survive_round_trip(tmp_path):
    snap, master, repo = _sample_dataset(tmp_path)
    manifest = repo.save(snap, master)
    restored = repo.load(manifest.dataset_id)

    resolved = restored.instrument_master.resolve_symbol("AAA.NS", datetime(2024, 1, 2, tzinfo=UTC))
    assert resolved is not None
    assert resolved.instrument_id == "inst-1"


def test_historical_symbols_survive_round_trip(tmp_path):
    snap, master, repo = _sample_dataset(tmp_path)
    manifest = repo.save(snap, master)
    restored = repo.load(manifest.dataset_id)

    assert set(restored.snapshot.bars.keys()) == {"AAA.NS"}


def test_membership_intervals_survive_round_trip(tmp_path):
    snap, master, repo = _sample_dataset(tmp_path)
    manifest = repo.save(snap, master)
    restored = repo.load(manifest.dataset_id)

    assert len(restored.snapshot.memberships) == 1
    m = restored.snapshot.memberships[0]
    assert m.instrument_id == "inst-1"
    assert m.index_name == "NIFTY 50"
    assert m.from_date == datetime(2020, 1, 1, tzinfo=UTC)


def test_corporate_actions_survive_round_trip(tmp_path):
    snap, master, repo = _sample_dataset(tmp_path)
    manifest = repo.save(snap, master)
    restored = repo.load(manifest.dataset_id)

    assert len(restored.snapshot.actions) == 1
    a = restored.snapshot.actions[0]
    assert a.instrument_id == "inst-1"
    assert a.amount == 5.0
    assert a.currency == "INR"


def test_adjustment_mode_survives_round_trip(tmp_path):
    snap, master, repo = _sample_dataset(tmp_path)
    manifest = repo.save(snap, master)
    restored = repo.load(manifest.dataset_id)

    assert restored.snapshot.adjustment_mode == AdjustmentMode.TOTAL_RETURN


def test_utc_survives_round_trip(tmp_path):
    snap, master, repo = _sample_dataset(tmp_path)
    manifest = repo.save(snap, master)
    restored = repo.load(manifest.dataset_id)

    bar = restored.snapshot.bars["AAA.NS"][0]
    assert bar.timestamp.tzinfo is not None
    assert bar.timestamp == datetime(2024, 1, 1, tzinfo=UTC)


def test_same_logical_dataset_same_checksum(tmp_path):
    snap, master, repo = _sample_dataset(tmp_path)
    m1 = repo.save(snap, master)
    m2 = repo.save(snap, master)

    assert m1.logical_checksum == m2.logical_checksum
    assert m1.artifact_checksum == m2.artifact_checksum


def test_one_bar_changed_logical_checksum_changes(tmp_path):
    snap, master, repo = _sample_dataset(tmp_path)
    m1 = repo.save(snap, master)

    # Modify one bar price
    snap_mod = snap.model_copy(deep=True)
    snap_mod.bars["AAA.NS"][0].close = 100.5

    snap_mod = create_snapshot(
        universe=snap_mod.universe,
        bars=snap_mod.bars,
        data_version=snap_mod.data_version,
        actions=snap_mod.actions,
        adjustment_mode=snap_mod.adjustment_mode,
        memberships=snap_mod.memberships,
    )
    m2 = repo.save(snap_mod, master)

    assert m1.logical_checksum != m2.logical_checksum
    assert m1.dataset_id != m2.dataset_id


def test_membership_changed_checksum_changes(tmp_path):
    snap, master, repo = _sample_dataset(tmp_path)
    m1 = repo.save(snap, master)

    mod_membership = IndexMembership(
        instrument_id="inst-1",
        symbol="AAA.NS",
        index_name="NIFTY 50",
        from_date=datetime(2023, 1, 1, tzinfo=UTC),  # Changed date
    )
    snap_mod = create_snapshot(
        universe=snap.universe,
        bars=snap.bars,
        data_version=snap.data_version,
        actions=snap.actions,
        adjustment_mode=snap.adjustment_mode,
        memberships=[mod_membership],
    )
    m2 = repo.save(snap_mod, master)

    assert m1.logical_checksum != m2.logical_checksum


def test_adjustment_mode_changed_checksum_changes(tmp_path):
    snap, master, repo = _sample_dataset(tmp_path)
    m1 = repo.save(snap, master)

    snap_mod = create_snapshot(
        universe=snap.universe,
        bars=snap.bars,
        data_version=snap.data_version,
        actions=snap.actions,
        adjustment_mode=AdjustmentMode.RAW,  # Changed mode
        memberships=snap.memberships,
    )
    m2 = repo.save(snap_mod, master)

    assert m1.logical_checksum != m2.logical_checksum


def test_corrupt_bars_parquet_verify_fails(tmp_path):
    snap, master, repo = _sample_dataset(tmp_path)
    manifest = repo.save(snap, master)

    assert repo.verify(manifest.dataset_id) is True

    # Tamper with bars.parquet bytes
    key_bars = f"datasets/{manifest.dataset_id}/bars.parquet"
    original_bytes = repo.store.get_bytes(key_bars)
    tampered_bytes = original_bytes + b"CORRUPTION"
    repo.store.put_bytes(key_bars, tampered_bytes)

    assert repo.verify(manifest.dataset_id) is False


def test_corrupt_memberships_parquet_verify_fails(tmp_path):
    snap, master, repo = _sample_dataset(tmp_path)
    manifest = repo.save(snap, master)

    key_mem = f"datasets/{manifest.dataset_id}/memberships.parquet"
    repo.store.put_bytes(key_mem, b"CORRUPTED")

    assert repo.verify(manifest.dataset_id) is False


def test_missing_file_verify_fails(tmp_path):
    snap, master, repo = _sample_dataset(tmp_path)
    manifest = repo.save(snap, master)

    key_mem = f"datasets/{manifest.dataset_id}/memberships.parquet"
    repo.store.delete(key_mem)

    assert repo.verify(manifest.dataset_id) is False


def test_unsupported_schema_explicit_exception(tmp_path):
    snap, master, repo = _sample_dataset(tmp_path)
    manifest = repo.save(snap, master)

    # Overwrite manifest.json with unsupported schema version
    key_manifest = f"datasets/{manifest.dataset_id}/manifest.json"
    data = json.loads(repo.store.get_bytes(key_manifest).decode("utf-8"))
    data["schema_version"] = "dataset-v99"
    repo.store.put_bytes(key_manifest, json.dumps(data).encode("utf-8"))

    with pytest.raises(UnsupportedSchemaError):
        repo.load(manifest.dataset_id)


def test_rows_persisted_in_deterministic_order(tmp_path):
    snap, master, repo = _sample_dataset(tmp_path)
    manifest = repo.save(snap, master)
    restored = repo.load(manifest.dataset_id)

    timestamps = [b.timestamp for b in restored.snapshot.bars["AAA.NS"]]
    assert timestamps == sorted(timestamps)


def test_save_load_build_training_frame_preserves_pit_membership(tmp_path):
    snap, master, repo = _sample_dataset(tmp_path)
    manifest = repo.save(snap, master)
    restored = repo.load(manifest.dataset_id)

    frame = build_training_frame(restored.snapshot, instruments=restored.instrument_master)
    assert not frame.empty


def test_symbol_rename_membership_continuity_survives_persistence(tmp_path):
    master = InstrumentMaster()
    master.upsert(
        Instrument(
            instrument_id="INST-555",
            symbol="OLD.NS",
            active_from=datetime(2020, 1, 1, tzinfo=UTC),
            active_until=datetime(2022, 12, 31, tzinfo=UTC),
        )
    )
    master.upsert(
        Instrument(
            instrument_id="INST-555",
            symbol="NEW.NS",
            active_from=datetime(2023, 1, 1, tzinfo=UTC),
        )
    )

    membership = IndexMembership(
        instrument_id="INST-555",
        symbol="NEW.NS",
        index_name="NIFTY 50",
        from_date=datetime(2020, 1, 1, tzinfo=UTC),
    )

    start = datetime(2020, 1, 1, tzinfo=UTC)
    bars_old = [
        Bar(
            symbol="OLD.NS",
            timestamp=start + timedelta(days=i),
            open=100.0 + i,
            high=101.0 + i,
            low=99.0 + i,
            close=100.0 + i,
            volume=10000.0,
        )
        for i in range(50)
    ]

    uni = Universe(name="NIFTY 50", version="v1", as_of=datetime.now(UTC), members=["OLD.NS"])
    snap = create_snapshot(universe=uni, bars={"OLD.NS": bars_old}, data_version="d1", memberships=[membership])

    store = LocalArtifactStore(root_dir=tmp_path / "artifacts")
    repo = ParquetDatasetRepository(store=store)

    manifest = repo.save(snap, master)
    restored = repo.load(manifest.dataset_id)

    frame = build_training_frame(restored.snapshot, instruments=restored.instrument_master)
    assert not frame.empty
    assert (frame["symbol"] == "OLD.NS").all()


def test_feature_artifact_points_to_exact_dataset_checksum(tmp_path):
    snap, master, repo = _sample_dataset(tmp_path)
    manifest = repo.save(snap, master)

    feat_store = LocalArtifactStore(root_dir=tmp_path / "artifacts")
    feat_repo = FeatureRepository(store=feat_store)

    frame = build_training_frame(snap, instruments=master)
    feat_manifest = feat_repo.save_features(
        features_df=frame,
        dataset_id=manifest.dataset_id,
        dataset_checksum=manifest.logical_checksum,
        feature_version="v1",
        parameters={"horizon": 5},
    )

    assert feat_manifest.dataset_id == manifest.dataset_id
    assert feat_manifest.dataset_checksum == manifest.logical_checksum
    assert feat_repo.verify_features(feat_manifest.feature_artifact_id) is True


def test_dataset_can_reproduce_walkforward_after_roundtrip(tmp_path):
    """The ultimate acceptance test: walk-forward metrics on restored dataset MUST match original exactly."""
    snap, master, repo = _sample_dataset(tmp_path)

    # 300 days of bars so walk-forward has enough folds
    start = datetime(2020, 1, 1, tzinfo=UTC)
    bars_aaa = [
        Bar(
            symbol="AAA.NS",
            timestamp=start + timedelta(days=i),
            open=100.0 + i * 0.1,
            high=101.0 + i * 0.1,
            low=99.0 + i * 0.1,
            close=100.0 + i * 0.1,
            volume=10000.0,
        )
        for i in range(300)
    ]
    uni = Universe(name="NIFTY 50", version="v1", as_of=datetime.now(UTC), members=["AAA.NS"])
    m1 = IndexMembership(
        instrument_id="inst-1",
        symbol="AAA.NS",
        index_name="NIFTY 50",
        from_date=datetime(2020, 1, 1, tzinfo=UTC),
    )
    snap = create_snapshot(
        universe=uni,
        bars={"AAA.NS": bars_aaa},
        data_version="d1",
        adjustment_mode=AdjustmentMode.TOTAL_RETURN,
        memberships=[m1],
    )

    def dummy_estimator_factory(x_tr, y_tr):
        class DummyEst:
            def predict(self, x):
                return [0.05] * len(x)

        return DummyEst()

    # Save and restore
    manifest = repo.save(snap, master)
    restored = repo.load(manifest.dataset_id)

    # Walk-forward on original snapshot
    before = run_walk_forward(
        snapshot=snap,
        horizon=5,
        n_splits=3,
        min_train_days=30,
        estimator_factory=dummy_estimator_factory,
        instruments=master,
    )

    # Walk-forward on restored snapshot
    after = run_walk_forward(
        snapshot=restored.snapshot,
        horizon=5,
        n_splits=3,
        min_train_days=30,
        estimator_factory=dummy_estimator_factory,
        instruments=restored.instrument_master,
    )

    assert before.n_folds == after.n_folds
    assert before.mean_ic == pytest.approx(after.mean_ic)
    assert before.mean_hit_rate == pytest.approx(after.mean_hit_rate)


def test_logical_checksum_survives_round_trip(tmp_path):
    """The logical checksum of the restored snapshot must equal the manifest value.

    This is the key identity invariant: if universe.as_of or universe.members
    are not persisted and restored exactly, the restored snapshot will produce
    a different checksum — making the dataset_id useless for reproducibility.
    """
    snap, master, repo = _sample_dataset(tmp_path)
    manifest = repo.save(snap, master)
    restored = repo.load(manifest.dataset_id)

    assert restored.snapshot.checksum == manifest.logical_checksum, (
        "Restored snapshot checksum does not match the persisted manifest.logical_checksum. "
        "This means universe.as_of or universe.members were not restored exactly."
    )
    assert restored.snapshot.dataset_id == manifest.dataset_id


def test_universe_as_of_survives_round_trip(tmp_path):
    """universe.as_of must be restored exactly (not replaced with datetime.now())."""
    snap, master, repo = _sample_dataset(tmp_path)
    original_as_of = snap.universe.as_of

    manifest = repo.save(snap, master)
    restored = repo.load(manifest.dataset_id)

    assert restored.snapshot.universe.as_of == original_as_of, (
        f"Expected universe.as_of={original_as_of!r} "
        f"but got {restored.snapshot.universe.as_of!r}"
    )
    assert restored.snapshot.universe.members == snap.universe.members


