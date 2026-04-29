"""
Machine Learning Confidence Booster — rewritten in PR #4.

Architecture (see app/ml/model.py for details):
  * LightGBM gradient-boosted trees (was: 50-tree shallow RandomForest).
  * TimeSeriesSplit walk-forward validation (was: random k-fold; leaks
    future into past on time-ordered data).
  * Isotonic calibration on out-of-fold predictions so `predict_proba()`
    is closer to a real frequency (was: uncalibrated probabilities).
  * Per-regime sub-models (trending / ranging / volatile / squeeze) with
    fall-back to the global model when a regime has too few samples.
  * 19-feature schema including order-flow features added in PR #2.

The legacy public API (`add_training_sample`, `train_model`,
`predict_confidence`, `MLEngine`, `ml_engine`) is preserved so callers don't
have to change. `MIN_SAMPLES` was raised from 50 → 200 to avoid noise.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np

from app.ml.features import FEATURE_NAMES, NUM_FEATURES, extract_features
from app.ml.model import LightGBMSignalModel, ModelMetrics

logger = logging.getLogger(__name__)

MODEL_PATH = "./data/ml_model_lgbm.pkl"
MIN_SAMPLES = 200
ML_WEIGHT = 0.30  # 30% ML, 70% rule-based

_training_buffer: List[Dict] = []
_model: Optional[LightGBMSignalModel] = None
_last_metrics: Optional[ModelMetrics] = None
_last_trained: Optional[str] = None


# ---------------------------------------------------------------------------
# Sample buffer
# ---------------------------------------------------------------------------

def add_training_sample(signal_data: Dict, outcome: str) -> None:
    """Add a completed signal to the training buffer.

    `outcome` examples: 'TP1' / 'TP2' / 'TP3' / 'WIN' / 'SL' / 'EXPIRED'.
    Anything matching the win set yields label=1, otherwise 0.
    """
    features = extract_features(signal_data)
    if features is None:
        return
    label = 1 if outcome in ("TP1", "TP2", "TP3", "WIN") else 0
    _training_buffer.append({
        "features": features,
        "label": label,
        "outcome": outcome,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    logger.debug("ML training sample added (now %d)", len(_training_buffer))


def reset_training_buffer_for_tests() -> None:
    """Test/utility hook — clears the buffer + cached model."""
    global _model, _last_metrics, _last_trained
    _training_buffer.clear()
    _model = None
    _last_metrics = None
    _last_trained = None


def buffer_size() -> int:
    return len(_training_buffer)


# ---------------------------------------------------------------------------
# Train / load / predict
# ---------------------------------------------------------------------------

def train_model() -> bool:
    """Train (or retrain) the LightGBM bundle on the buffered samples.

    Returns True on success, False if not enough data or LightGBM is missing.
    """
    global _model, _last_metrics, _last_trained

    if len(_training_buffer) < MIN_SAMPLES:
        logger.info(
            "ML: need %d samples, have %d. Skipping training.",
            MIN_SAMPLES, len(_training_buffer),
        )
        return False

    try:
        X = np.array([s["features"] for s in _training_buffer], dtype=float)
        y = np.array([s["label"] for s in _training_buffer], dtype=int)

        new_model = LightGBMSignalModel()
        metrics = new_model.fit(X, y)
        _model = new_model
        _last_metrics = metrics
        _last_trained = datetime.now(timezone.utc).isoformat()

        os.makedirs(os.path.dirname(MODEL_PATH) if os.path.dirname(MODEL_PATH) else ".", exist_ok=True)
        try:
            new_model.save(MODEL_PATH)
        except Exception as e:
            logger.warning("ml model save failed: %s", e)

        logger.info(
            "ML: trained LightGBM model — n=%d auc=%s brier=%s",
            metrics.n_samples, metrics.walk_forward_auc, metrics.walk_forward_brier,
        )
        return True
    except ImportError as e:
        logger.warning("LightGBM/sklearn unavailable: %s", e)
        return False
    except Exception as e:
        logger.error("train_model error: %s", e)
        return False


def load_model() -> bool:
    """Load model from disk on startup; returns True if loaded."""
    global _model, _last_metrics
    if not os.path.exists(MODEL_PATH):
        return False
    try:
        _model = LightGBMSignalModel.load(MODEL_PATH)
        _last_metrics = _model.metrics
        logger.info("ML: loaded persisted LightGBM model from %s", MODEL_PATH)
        return True
    except Exception as e:
        logger.error("load_model error: %s", e)
        _model = None
        return False


def predict_confidence(signal_data: Dict) -> Dict:
    """Blend rule-based confidence with ML probability.

    Output shape preserved from the legacy engine so existing callers and
    serializers keep working. New keys: `top_contributors`, `metrics_summary`.
    """
    rule_score = float(signal_data.get("confidence_score", 0) or 0)

    if _model is None:
        return {
            "ml_active": False,
            "ml_confidence": None,
            "final_confidence": rule_score,
            "rule_confidence": rule_score,
            "reason": (
                f"ML inactive — need {MIN_SAMPLES} signals "
                f"to train (have {len(_training_buffer)})"
            ),
        }

    features = extract_features(signal_data)
    if features is None:
        return {
            "ml_active": False, "ml_confidence": None,
            "final_confidence": rule_score, "rule_confidence": rule_score,
        }

    try:
        x = np.array(features, dtype=float)
        explanation = _model.predict_with_explanation(x)
        proba = float(explanation["probability"]) * 100
        final = rule_score * (1 - ML_WEIGHT) + proba * ML_WEIGHT
        return {
            "ml_active": True,
            "ml_confidence": round(proba, 1),
            "rule_confidence": round(rule_score, 1),
            "final_confidence": round(final, 1),
            "blend_ratio": f"{int((1 - ML_WEIGHT) * 100)}% rule + {int(ML_WEIGHT * 100)}% ML",
            "top_contributors": explanation.get("top_contributors", []),
            "metrics_summary": _summary_metrics(),
        }
    except Exception as e:
        logger.error("predict_confidence error: %s", e)
        return {
            "ml_active": False, "ml_confidence": None,
            "final_confidence": rule_score, "rule_confidence": rule_score,
        }


def _summary_metrics() -> Dict:
    if _last_metrics is None:
        return {}
    return {
        "walk_forward_auc": _last_metrics.walk_forward_auc,
        "walk_forward_brier": _last_metrics.walk_forward_brier,
        "n_samples": _last_metrics.n_samples,
        "n_positive": _last_metrics.n_positive,
    }


# ---------------------------------------------------------------------------
# Engine wrapper (keeps legacy import path working)
# ---------------------------------------------------------------------------

class MLEngine:
    """ML confidence booster engine (legacy facade over LightGBMSignalModel)."""

    def __init__(self) -> None:
        load_model()

    def predict(self, signal_data: Dict) -> Dict:
        return predict_confidence(signal_data)

    def add_sample(self, signal_data: Dict, outcome: str) -> None:
        add_training_sample(signal_data, outcome)

    def retrain(self) -> bool:
        return train_model()

    def get_stats(self) -> Dict:
        active = _model is not None
        if _last_metrics is None:
            return {
                "active": active,
                "buffered_samples": len(_training_buffer),
                "min_samples_needed": MIN_SAMPLES,
                "samples_until_active": max(0, MIN_SAMPLES - len(_training_buffer)),
                "last_trained": _last_trained,
                "model_type": "lightgbm",
                "n_features": NUM_FEATURES,
                "feature_names": FEATURE_NAMES,
            }

        m = _last_metrics
        return {
            "active": active,
            "buffered_samples": len(_training_buffer),
            "min_samples_needed": MIN_SAMPLES,
            "samples_until_active": 0,
            "last_trained": _last_trained,
            "model_type": "lightgbm",
            "n_features": NUM_FEATURES,
            "feature_names": FEATURE_NAMES,
            "n_samples_trained": m.n_samples,
            "n_positive": m.n_positive,
            "walk_forward_auc": m.walk_forward_auc,
            "walk_forward_brier": m.walk_forward_brier,
            "feature_importance": m.feature_importance,
            "per_regime_n": m.per_regime_n,
            "per_regime_auc": m.per_regime_auc,
        }


ml_engine = MLEngine()
