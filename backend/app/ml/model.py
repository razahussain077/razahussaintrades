"""
LightGBM signal-confidence model with TimeSeriesSplit walk-forward validation
and isotonic calibration on the held-out fold.

Why this architecture:
  * LightGBM handles non-linear feature interactions out of the box and is
    robust to feature-scale heterogeneity (CVD in $ vs hour-of-day in 0-23).
  * `TimeSeriesSplit` enforces strict past→future ordering — random k-fold
    leaks future labels into training on time-ordered data and produces
    optimistic CV numbers.
  * Isotonic calibration on the last fold's out-of-fold probabilities
    converts raw model scores into something closer to actual win rates,
    so `predict_proba()=0.85` corresponds to ~85% empirical hit rate.
  * Per-regime sub-models are trained from the same buffer but filtered
    to the rows where `regime == r`. The wrapper picks the right sub-model
    at inference time and falls back to the global model if a regime has
    too few samples.

The class is library-light at import time — heavy deps (LightGBM, sklearn)
are imported lazily so unit tests that only touch `extract_features` don't
need the C++ runtime.
"""
from __future__ import annotations

import logging
import math
import pickle
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from app.ml.features import FEATURE_NAMES, NUM_FEATURES

logger = logging.getLogger(__name__)


_REGIME_NAMES = ["ranging", "trending", "volatile", "squeeze"]


@dataclass
class ModelMetrics:
    """Walk-forward metrics for a fitted model."""
    n_samples: int
    n_positive: int
    n_features: int
    walk_forward_auc: Optional[float]   # mean AUC across folds (None if folds<2)
    walk_forward_brier: Optional[float] # mean Brier loss across folds
    feature_importance: Dict[str, float] = field(default_factory=dict)
    per_regime_n: Dict[str, int] = field(default_factory=dict)
    per_regime_auc: Dict[str, Optional[float]] = field(default_factory=dict)


def _is_constant(y: np.ndarray) -> bool:
    return bool(len(np.unique(y)) < 2)


def _safe_auc(y_true: np.ndarray, y_pred: np.ndarray) -> Optional[float]:
    if _is_constant(y_true):
        return None
    try:
        from sklearn.metrics import roc_auc_score
        return float(roc_auc_score(y_true, y_pred))
    except Exception as e:
        logger.warning("auc compute failed: %s", e)
        return None


def _safe_brier(y_true: np.ndarray, y_pred: np.ndarray) -> Optional[float]:
    try:
        from sklearn.metrics import brier_score_loss
        return float(brier_score_loss(y_true, y_pred))
    except Exception as e:
        logger.warning("brier compute failed: %s", e)
        return None


class LightGBMSignalModel:
    """LightGBM + walk-forward + per-regime + isotonic calibration."""

    MIN_SAMPLES = 200          # global minimum to fit anything
    MIN_REGIME_SAMPLES = 80    # below this, fall back to global model
    REGIME_FEATURE_INDEX = 4   # FEATURE_NAMES[4] == "regime"

    def __init__(self) -> None:
        self.global_booster = None
        self.regime_boosters: Dict[int, object] = {}
        self.calibrators: Dict[Optional[int], object] = {}  # key: regime int or None for global
        self.metrics: Optional[ModelMetrics] = None
        self.feature_names: List[str] = list(FEATURE_NAMES)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fit(self, X: np.ndarray, y: np.ndarray) -> ModelMetrics:
        """Train global + per-regime models with walk-forward validation."""
        if X.ndim != 2 or X.shape[1] != NUM_FEATURES:
            raise ValueError(f"X must be (n, {NUM_FEATURES}); got {X.shape}")
        if X.shape[0] < self.MIN_SAMPLES:
            raise ValueError(f"need >= {self.MIN_SAMPLES} samples to fit, got {X.shape[0]}")
        if y.shape[0] != X.shape[0]:
            raise ValueError("X / y row count mismatch")

        wf_auc, wf_brier, oof_pred, oof_true = self._walk_forward(X, y)

        self.global_booster = self._fit_lgbm(X, y)
        self._fit_calibrator(None, oof_pred, oof_true)

        per_regime_n: Dict[str, int] = {}
        per_regime_auc: Dict[str, Optional[float]] = {}
        for regime_int, regime_name in enumerate(_REGIME_NAMES):
            mask = X[:, self.REGIME_FEATURE_INDEX] == regime_int
            n = int(mask.sum())
            per_regime_n[regime_name] = n
            if n < self.MIN_REGIME_SAMPLES:
                per_regime_auc[regime_name] = None
                continue
            X_r, y_r = X[mask], y[mask]
            r_auc, _, oof_p, oof_t = self._walk_forward(X_r, y_r)
            self.regime_boosters[regime_int] = self._fit_lgbm(X_r, y_r)
            self._fit_calibrator(regime_int, oof_p, oof_t)
            per_regime_auc[regime_name] = r_auc

        importance = self._feature_importance(self.global_booster)
        self.metrics = ModelMetrics(
            n_samples=int(X.shape[0]),
            n_positive=int(y.sum()),
            n_features=int(X.shape[1]),
            walk_forward_auc=wf_auc,
            walk_forward_brier=wf_brier,
            feature_importance=importance,
            per_regime_n=per_regime_n,
            per_regime_auc=per_regime_auc,
        )
        return self.metrics

    def predict_proba(self, x: np.ndarray) -> float:
        """Return calibrated probability of class=1 (signal hits TP1+) for one row."""
        if x.ndim == 1:
            x = x.reshape(1, -1)
        if x.shape[1] != NUM_FEATURES:
            raise ValueError(f"feature dim mismatch: {x.shape[1]} != {NUM_FEATURES}")

        regime_int = int(x[0, self.REGIME_FEATURE_INDEX])
        booster = self.regime_boosters.get(regime_int) or self.global_booster
        if booster is None:
            raise RuntimeError("model not fitted")

        raw = float(booster.predict(x)[0])  # type: ignore[union-attr]
        cal_key = regime_int if regime_int in self.regime_boosters else None
        cal = self.calibrators.get(cal_key) or self.calibrators.get(None)
        if cal is not None:
            try:
                return float(cal.predict([raw])[0])  # type: ignore[union-attr]
            except Exception:
                pass
        return raw

    def predict_with_explanation(self, x: np.ndarray) -> Dict:
        """Probability + top-3 contributing features (LightGBM split contributions)."""
        if x.ndim == 1:
            x = x.reshape(1, -1)
        proba = self.predict_proba(x)
        top: List[Tuple[str, float]] = []
        if self.global_booster is not None:
            try:
                # pred_contrib returns SHAP-style decomposition (last col = bias)
                contribs = self.global_booster.predict(x, pred_contrib=True)[0]  # type: ignore[union-attr]
                pairs = [(self.feature_names[i], float(contribs[i]))
                         for i in range(min(NUM_FEATURES, len(contribs) - 1))]
                pairs.sort(key=lambda p: abs(p[1]), reverse=True)
                top = pairs[:3]
            except Exception as e:
                logger.warning("pred_contrib failed: %s", e)
        return {
            "probability": proba,
            "top_contributors": [{"feature": k, "shap": v} for k, v in top],
        }

    def save(self, path: str) -> None:
        with open(path, "wb") as f:
            pickle.dump({
                "global_booster": self.global_booster,
                "regime_boosters": self.regime_boosters,
                "calibrators": self.calibrators,
                "metrics": self.metrics,
                "feature_names": self.feature_names,
            }, f)

    @classmethod
    def load(cls, path: str) -> "LightGBMSignalModel":
        with open(path, "rb") as f:
            blob = pickle.load(f)
        m = cls()
        m.global_booster = blob.get("global_booster")
        m.regime_boosters = blob.get("regime_boosters") or {}
        m.calibrators = blob.get("calibrators") or {}
        m.metrics = blob.get("metrics")
        m.feature_names = blob.get("feature_names") or list(FEATURE_NAMES)
        return m

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _fit_lgbm(X: np.ndarray, y: np.ndarray):
        import lightgbm as lgb
        params = {
            "objective": "binary",
            "metric": "binary_logloss",
            "learning_rate": 0.05,
            "num_leaves": 31,
            "feature_fraction": 0.8,
            "bagging_fraction": 0.8,
            "bagging_freq": 5,
            "min_data_in_leaf": 10,
            "verbose": -1,
        }
        train_set = lgb.Dataset(X, label=y, feature_name=list(FEATURE_NAMES))
        booster = lgb.train(params, train_set, num_boost_round=200)
        return booster

    def _walk_forward(
        self, X: np.ndarray, y: np.ndarray,
    ) -> Tuple[Optional[float], Optional[float], np.ndarray, np.ndarray]:
        """TimeSeriesSplit-based walk-forward eval. Returns (mean_auc, mean_brier,
        oof_predictions, oof_truth) for the rows that appeared as test rows."""
        n_samples = X.shape[0]
        if _is_constant(y):
            return None, None, np.array([]), np.array([])
        n_splits = max(2, min(5, n_samples // 60))

        from sklearn.model_selection import TimeSeriesSplit
        tscv = TimeSeriesSplit(n_splits=n_splits)

        oof_p: List[float] = []
        oof_t: List[int] = []
        aucs: List[float] = []
        briers: List[float] = []

        for tr_idx, te_idx in tscv.split(X):
            X_tr, X_te = X[tr_idx], X[te_idx]
            y_tr, y_te = y[tr_idx], y[te_idx]
            if _is_constant(y_tr):
                continue
            booster = self._fit_lgbm(X_tr, y_tr)
            p = booster.predict(X_te)
            oof_p.extend(p.tolist())
            oof_t.extend(y_te.tolist())
            auc = _safe_auc(y_te, p)
            if auc is not None and not math.isnan(auc):
                aucs.append(auc)
            brier = _safe_brier(y_te, p)
            if brier is not None:
                briers.append(brier)

        mean_auc = float(np.mean(aucs)) if aucs else None
        mean_brier = float(np.mean(briers)) if briers else None
        return mean_auc, mean_brier, np.array(oof_p), np.array(oof_t)

    def _fit_calibrator(self, regime: Optional[int], oof_p: np.ndarray, oof_t: np.ndarray) -> None:
        if oof_p.size < 30 or _is_constant(oof_t):
            return
        try:
            from sklearn.isotonic import IsotonicRegression
            iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
            iso.fit(oof_p, oof_t)
            self.calibrators[regime] = iso
        except Exception as e:
            logger.warning("calibrator fit failed (regime=%s): %s", regime, e)

    @staticmethod
    def _feature_importance(booster) -> Dict[str, float]:
        if booster is None:
            return {}
        try:
            imp = booster.feature_importance(importance_type="gain")
            total = float(np.sum(imp)) or 1.0
            return {
                FEATURE_NAMES[i]: round(float(imp[i]) / total * 100, 1)
                for i in range(min(len(imp), NUM_FEATURES))
            }
        except Exception as e:
            logger.warning("feature importance failed: %s", e)
            return {}
