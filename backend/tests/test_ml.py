"""Tests for the rewritten ML engine + LightGBMSignalModel."""
import os
import tempfile

import numpy as np
import pytest

from app.engines import ml_engine
from app.ml.features import FEATURE_NAMES, NUM_FEATURES, extract_features
from app.ml.model import LightGBMSignalModel


@pytest.fixture(autouse=True)
def _reset_buffer():
    ml_engine.reset_training_buffer_for_tests()
    yield
    ml_engine.reset_training_buffer_for_tests()


# ---------------------------------------------------------------------------
# extract_features
# ---------------------------------------------------------------------------

class TestExtractFeatures:
    def test_minimal_signal_yields_full_vector(self):
        feats = extract_features({})
        assert feats is not None
        assert len(feats) == NUM_FEATURES

    def test_orderflow_block_threaded_through(self):
        sig = {
            "orderflow_result": {
                "have_data": True,
                "delta_1m_normalized": 0.55,
                "cvd_5m": 12345.0,
                "large_buy_count": 7,
                "large_sell_count": 0,
                "bullish_divergence": True,
                "bearish_divergence": False,
            },
        }
        feats = extract_features(sig)
        assert feats is not None
        # Indexes must match FEATURE_NAMES.
        idx = {name: i for i, name in enumerate(FEATURE_NAMES)}
        assert feats[idx["of_have_data"]] == 1.0
        assert feats[idx["of_delta_1m_norm"]] == pytest.approx(0.55)
        assert feats[idx["of_cvd_5m"]] == pytest.approx(12345.0)
        assert feats[idx["of_large_buy_count"]] == 7
        assert feats[idx["of_bullish_divergence"]] == 1.0
        assert feats[idx["of_bearish_divergence"]] == 0.0

    def test_regime_mapped_to_int(self):
        idx = FEATURE_NAMES.index("regime")
        assert extract_features({"regime": "trending"})[idx] == 1
        assert extract_features({"regime": "volatile"})[idx] == 2
        assert extract_features({"regime": "squeeze"})[idx] == 3
        assert extract_features({"regime": "unknown_str"})[idx] == 0

    def test_pkt_hour_from_iso_timestamp(self):
        idx = FEATURE_NAMES.index("hour_pkt")
        feats = extract_features({"created_at": "2024-12-20T08:30:00+00:00"})
        # 08:30 UTC + 5h = 13:30 PKT
        assert feats[idx] == 13.0

    def test_bad_timestamp_falls_back_to_zero(self):
        idx = FEATURE_NAMES.index("hour_pkt")
        feats = extract_features({"created_at": "not-a-time"})
        assert feats[idx] == 0


# ---------------------------------------------------------------------------
# LightGBMSignalModel
# ---------------------------------------------------------------------------

def _synthetic_dataset(n: int = 400, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Build a learnable synthetic dataset spanning all 4 regimes."""
    rng = np.random.default_rng(seed)
    X = np.zeros((n, NUM_FEATURES))
    # Engine confluence (0..6).
    X[:, 0] = rng.integers(0, 7, size=n)
    # Random funding boost.
    X[:, 1] = rng.normal(0, 5, size=n)
    # Volume relative ~ 1.
    X[:, 3] = rng.normal(1, 0.3, size=n)
    # Regime (0..3).
    X[:, 4] = rng.integers(0, 4, size=n)
    # Order flow features.
    X[:, 9] = rng.integers(0, 2, size=n)              # of_have_data
    X[:, 10] = rng.uniform(-1, 1, size=n)             # of_delta_1m_norm

    # Label: noisy linear function of confluence + delta + regime.
    score = 0.4 * X[:, 0] + 1.5 * X[:, 10] + 0.3 * X[:, 4] + rng.normal(0, 0.5, size=n)
    y = (score > score.mean()).astype(int)
    return X, y


class TestLightGBMSignalModel:
    def test_fit_and_predict(self):
        X, y = _synthetic_dataset(n=400)
        model = LightGBMSignalModel()
        metrics = model.fit(X, y)
        assert metrics.n_samples == 400
        assert 0 < metrics.n_positive < 400
        # Walk-forward AUC should be informative on this contrived dataset.
        if metrics.walk_forward_auc is not None:
            assert metrics.walk_forward_auc > 0.55
        # Model returns a probability in [0, 1] for a single row.
        proba = model.predict_proba(X[0])
        assert 0.0 <= proba <= 1.0

    def test_min_samples_enforced(self):
        X, y = _synthetic_dataset(n=50)
        model = LightGBMSignalModel()
        with pytest.raises(ValueError):
            model.fit(X, y)

    def test_per_regime_metrics_present(self):
        X, y = _synthetic_dataset(n=600)
        model = LightGBMSignalModel()
        metrics = model.fit(X, y)
        assert set(metrics.per_regime_n.keys()) == {"ranging", "trending", "volatile", "squeeze"}
        # We expect at least 1 regime to have hit MIN_REGIME_SAMPLES.
        assert any(n >= LightGBMSignalModel.MIN_REGIME_SAMPLES for n in metrics.per_regime_n.values())

    def test_save_and_load_roundtrip(self):
        X, y = _synthetic_dataset(n=400)
        model = LightGBMSignalModel()
        model.fit(X, y)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "m.pkl")
            model.save(path)
            loaded = LightGBMSignalModel.load(path)
        assert loaded.global_booster is not None
        # Predictions match (modulo floating point) after roundtrip.
        a = model.predict_proba(X[0])
        b = loaded.predict_proba(X[0])
        assert abs(a - b) < 1e-6

    def test_explanation_top_contributors(self):
        X, y = _synthetic_dataset(n=400)
        model = LightGBMSignalModel()
        model.fit(X, y)
        out = model.predict_with_explanation(X[0])
        assert "probability" in out
        assert isinstance(out["top_contributors"], list)
        assert len(out["top_contributors"]) <= 3
        for entry in out["top_contributors"]:
            assert entry["feature"] in FEATURE_NAMES


# ---------------------------------------------------------------------------
# ml_engine integration
# ---------------------------------------------------------------------------

class TestMLEngineIntegration:
    def test_inactive_until_min_samples(self):
        for _ in range(10):
            ml_engine.add_training_sample({"confidence_score": 60}, "TP1")
        assert ml_engine.train_model() is False
        result = ml_engine.predict_confidence({"confidence_score": 70})
        assert result["ml_active"] is False
        assert result["final_confidence"] == 70

    def test_full_train_predict_cycle(self):
        rng = np.random.default_rng(1)
        for i in range(ml_engine.MIN_SAMPLES + 20):
            cs = float(rng.uniform(40, 95))
            outcome = "TP1" if cs > 70 else "SL"
            ml_engine.add_training_sample(
                {
                    "confidence_score": cs,
                    "regime": ["ranging", "trending", "volatile", "squeeze"][i % 4],
                    "reasoning": ["x"] * (i % 6),
                    "orderflow_result": {
                        "have_data": True,
                        "delta_1m_normalized": float(rng.uniform(-1, 1)),
                        "cvd_5m": float(rng.uniform(-50_000, 50_000)),
                        "large_buy_count": int(rng.integers(0, 6)),
                        "large_sell_count": int(rng.integers(0, 6)),
                        "bullish_divergence": bool(rng.random() < 0.3),
                        "bearish_divergence": bool(rng.random() < 0.3),
                    },
                    "rr_gross": float(rng.uniform(1.5, 4.0)),
                    "rr_net": float(rng.uniform(1.0, 3.5)),
                    "atr_pct": float(rng.uniform(0.5, 3.0)),
                },
                outcome,
            )
        assert ml_engine.train_model() is True
        result = ml_engine.predict_confidence({
            "confidence_score": 75,
            "regime": "trending",
            "orderflow_result": {"have_data": True, "delta_1m_normalized": 0.4},
        })
        assert result["ml_active"] is True
        assert 0 <= result["ml_confidence"] <= 100
        assert "blend_ratio" in result
        # Stats endpoint reflects the trained model.
        stats = ml_engine.ml_engine.get_stats()
        assert stats["active"] is True
        assert stats["n_samples_trained"] >= ml_engine.MIN_SAMPLES
        assert stats["model_type"] == "lightgbm"
        assert stats["n_features"] == NUM_FEATURES
