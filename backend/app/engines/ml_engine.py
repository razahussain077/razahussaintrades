"""
Machine Learning Confidence Booster — Feature 5
Uses scikit-learn Random Forest to predict signal outcome probability.
Requires minimum 50 past signals to activate.
"""
import logging
import os
import pickle
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

MODEL_PATH = "./data/ml_model.pkl"
MIN_SAMPLES = 50
ML_WEIGHT = 0.30  # 30% ML, 70% rule-based

# In-memory signal outcome buffer for training
_training_buffer: List[Dict] = []
_model = None
_model_stats: Dict = {
    "accuracy": 0.0,
    "last_trained": None,
    "total_samples": 0,
    "feature_importance": {},
    "active": False,
}


def _extract_features(signal_data: Dict) -> Optional[List[float]]:
    """
    Extract ML features from signal data.
    Features:
      0: engine_confluence_count (1-6)
      1: funding_rate_boost (confidence modifier from funding)
      2: oi_change_pct (open interest change %)
      3: volume_relative (volume vs 20-period avg)
      4: market_regime (0=ranging, 1=trending, 2=volatile, 3=squeeze)
      5: kill_zone_active (0/1)
      6: htf_bias_aligned (0/1)
      7: hour_of_day_pkt (0-23)
      8: day_of_week (0-6, Monday=0)
    """
    try:
        # Engine confluence from reasoning list
        reasoning = signal_data.get("reasoning", [])
        engine_count = min(len(reasoning), 6)

        # Funding rate boost (default 0 if not available)
        funding_boost = float(signal_data.get("funding_boost", 0))

        # OI change (default 0)
        oi_change = float(signal_data.get("oi_change_pct", 0))

        # Volume relative to average
        volume_relative = float(signal_data.get("volume_relative", 1.0))

        # Market regime
        regime_map = {"ranging": 0, "trending": 1, "volatile": 2, "squeeze": 3}
        regime = regime_map.get(signal_data.get("regime", "ranging"), 0)

        # Kill zone active
        kill_zone = signal_data.get("kill_zone", "Off Hours")
        kill_zone_active = 0 if kill_zone in ("Off Hours", None, "") else 1

        # HTF bias aligned (confidence > 75 as proxy)
        htf_aligned = 1 if signal_data.get("confidence_score", 0) >= 75 else 0

        # Time features from created_at
        created_at = signal_data.get("created_at", "")
        hour = 0
        dow = 0
        if created_at:
            try:
                dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                # Convert to PKT (UTC+5)
                from datetime import timedelta
                pkt_dt = dt + timedelta(hours=5)
                hour = pkt_dt.hour
                dow = pkt_dt.weekday()
            except Exception:
                pass

        return [
            float(engine_count),
            float(funding_boost),
            float(oi_change),
            float(volume_relative),
            float(regime),
            float(kill_zone_active),
            float(htf_aligned),
            float(hour),
            float(dow),
        ]
    except Exception as e:
        logger.error(f"_extract_features error: {e}")
        return None


def add_training_sample(signal_data: Dict, outcome: str) -> None:
    """
    Add a completed signal to the training buffer.
    outcome: 'TP1', 'TP2', 'TP3', 'SL', 'EXPIRED'
    """
    features = _extract_features(signal_data)
    if features is None:
        return

    # Binary label: hit TP1 or better = 1, SL/expired = 0
    label = 1 if outcome in ("TP1", "TP2", "TP3", "WIN") else 0

    _training_buffer.append({
        "features": features,
        "label": label,
        "outcome": outcome,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    logger.debug(f"Training sample added. Total: {len(_training_buffer)}")


def train_model() -> bool:
    """Train (or retrain) the Random Forest model on buffered data."""
    global _model, _model_stats

    if len(_training_buffer) < MIN_SAMPLES:
        logger.info(f"ML: Need {MIN_SAMPLES} samples, have {len(_training_buffer)}. Skipping training.")
        return False

    try:
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.model_selection import cross_val_score
        from sklearn.preprocessing import StandardScaler

        X = np.array([s["features"] for s in _training_buffer])
        y = np.array([s["label"] for s in _training_buffer])

        # Train model
        clf = RandomForestClassifier(
            n_estimators=50,
            max_depth=6,
            random_state=42,
            class_weight="balanced",
        )
        clf.fit(X, y)

        # Cross-validation accuracy
        try:
            scores = cross_val_score(clf, X, y, cv=min(5, len(y) // 10 + 2))
            accuracy = float(np.mean(scores))
        except Exception:
            accuracy = float(clf.score(X, y))

        # Feature importance
        feature_names = [
            "engine_confluence", "funding_boost", "oi_change",
            "volume_relative", "regime", "kill_zone", "htf_aligned",
            "hour_pkt", "day_of_week",
        ]
        importance = dict(zip(feature_names, clf.feature_importances_.tolist()))

        _model = clf
        _model_stats = {
            "accuracy": round(accuracy * 100, 1),
            "last_trained": datetime.now(timezone.utc).isoformat(),
            "total_samples": len(_training_buffer),
            "feature_importance": {k: round(float(v) * 100, 1) for k, v in importance.items()},
            "active": True,
        }

        # Save model to disk
        os.makedirs(os.path.dirname(MODEL_PATH) if os.path.dirname(MODEL_PATH) else ".", exist_ok=True)
        with open(MODEL_PATH, "wb") as f:
            pickle.dump(_model, f)

        logger.info(f"ML model trained. Accuracy: {accuracy:.1%}, Samples: {len(_training_buffer)}")
        return True

    except ImportError:
        logger.warning("scikit-learn not installed — ML features disabled")
        return False
    except Exception as e:
        logger.error(f"train_model error: {e}")
        return False


def load_model() -> bool:
    """Load model from disk on startup."""
    global _model
    if os.path.exists(MODEL_PATH):
        try:
            with open(MODEL_PATH, "rb") as f:
                _model = pickle.load(f)
            _model_stats["active"] = True
            logger.info("ML model loaded from disk")
            return True
        except Exception as e:
            logger.error(f"load_model error: {e}")
    return False


def predict_confidence(signal_data: Dict) -> Dict:
    """
    Predict probability of hitting TP1 using ML model.
    Returns ML confidence score (0-100) and blend with rule-based score.
    """
    if _model is None or not _model_stats.get("active"):
        return {
            "ml_active": False,
            "ml_confidence": None,
            "final_confidence": signal_data.get("confidence_score", 0),
            "reason": f"ML inactive — need {MIN_SAMPLES} signals to train (have {len(_training_buffer)})",
        }

    features = _extract_features(signal_data)
    if features is None:
        return {
            "ml_active": False,
            "ml_confidence": None,
            "final_confidence": signal_data.get("confidence_score", 0),
        }

    try:
        X = np.array([features])
        proba = _model.predict_proba(X)[0]
        # proba[1] = probability of success (hitting TP1)
        ml_score = proba[1] * 100

        rule_score = signal_data.get("confidence_score", 0)
        # Blend: 70% rule-based + 30% ML
        final_score = rule_score * (1 - ML_WEIGHT) + ml_score * ML_WEIGHT

        return {
            "ml_active": True,
            "ml_confidence": round(ml_score, 1),
            "rule_confidence": round(rule_score, 1),
            "final_confidence": round(final_score, 1),
            "blend_ratio": f"{int((1-ML_WEIGHT)*100)}% rule + {int(ML_WEIGHT*100)}% ML",
        }
    except Exception as e:
        logger.error(f"predict_confidence error: {e}")
        return {
            "ml_active": False,
            "ml_confidence": None,
            "final_confidence": signal_data.get("confidence_score", 0),
        }


class MLEngine:
    """ML confidence booster engine."""

    def __init__(self):
        load_model()

    def predict(self, signal_data: Dict) -> Dict:
        return predict_confidence(signal_data)

    def add_sample(self, signal_data: Dict, outcome: str) -> None:
        add_training_sample(signal_data, outcome)

    def retrain(self) -> bool:
        return train_model()

    def get_stats(self) -> Dict:
        return {
            **_model_stats,
            "buffered_samples": len(_training_buffer),
            "min_samples_needed": MIN_SAMPLES,
            "samples_until_active": max(0, MIN_SAMPLES - len(_training_buffer)),
        }


ml_engine = MLEngine()
