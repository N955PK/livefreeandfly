"""Snow-to-liquid ratio models: candidates, cross-validation, and selection."""
import json

import joblib
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin, clone
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from tahoe_snow import physics
from tahoe_snow.config import MM_PER_IN, MODELS
from tahoe_snow.snow.features import FEATURES, REDUCED_FEATURES

SLR_CLIP = (3.0, 30.0)
MODEL_FILE = "snow_ratio.joblib"


class FixedRatio(BaseEstimator, RegressorMixin):
    def __init__(self, ratio: float = 10.0):
        self.ratio = ratio

    def fit(self, X, y):
        return self

    def predict(self, X):
        return np.full(len(X), self.ratio)


class MeanRatio(BaseEstimator, RegressorMixin):
    """Liquid-weighted mean ratio of the training events."""

    def fit(self, X, y):
        liquid = X["liquid_mm"].to_numpy()
        self.ratio_ = float((y * liquid).sum() / liquid.sum())
        return self

    def predict(self, X):
        return np.full(len(X), self.ratio_)


class Kuchera(BaseEstimator, RegressorMixin):
    def fit(self, X, y):
        return self

    def predict(self, X):
        return physics.kuchera_slr(X["tmax_col"].to_numpy() + 273.15)


class ColumnModel(BaseEstimator, RegressorMixin):
    """A regressor on a named subset of columns, with predictions clipped to a physical range."""

    def __init__(self, estimator=None, columns=None):
        self.estimator = estimator
        self.columns = columns

    def fit(self, X, y, sample_weight=None):
        self.estimator_ = clone(self.estimator)
        if sample_weight is None:
            self.estimator_.fit(X[list(self.columns)], y)
        else:
            step = self.estimator_.steps[-1][0] + "__sample_weight" if hasattr(self.estimator_, "steps") else None
            kwargs = {step: sample_weight} if step else {"sample_weight": sample_weight}
            self.estimator_.fit(X[list(self.columns)], y, **kwargs)
        return self

    def predict(self, X):
        return np.clip(self.estimator_.predict(X[list(self.columns)]), *SLR_CLIP)


def candidates() -> dict:
    ridge = make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-2, 3, 12)))
    forest = RandomForestRegressor(n_estimators=400, min_samples_leaf=5, max_features=0.5, n_jobs=-1, random_state=0)
    boost = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=20,
                                          l2_regularization=1.0, random_state=0)
    return {
        "fixed 10:1": FixedRatio(10.0),
        "training mean": MeanRatio(),
        "Kuchera": Kuchera(),
        "ridge (temp + wind)": ColumnModel(ridge, REDUCED_FEATURES),
        "ridge (all)": ColumnModel(ridge, FEATURES),
        "random forest (temp + wind)": ColumnModel(forest, REDUCED_FEATURES),
        "random forest (all)": ColumnModel(forest, FEATURES),
        "gradient boosting (temp + wind)": ColumnModel(boost, REDUCED_FEATURES),
        "gradient boosting (all)": ColumnModel(boost, FEATURES),
    }


def folds(events: pd.DataFrame, by: str) -> list:
    """Leave-one-group-out folds as (group, train_mask, test_mask); no group is on both sides."""
    groups = events[by].to_numpy()
    return [(g, groups != g, groups == g) for g in pd.unique(groups)]


def out_of_fold(events: pd.DataFrame, model, by: str = "season", weighted: bool = True) -> np.ndarray:
    """Predictions for every event from a model that never saw that event's group."""
    predictions = np.full(len(events), np.nan)
    y = events["slr"].to_numpy()
    weights = np.sqrt(events["liquid_mm"].to_numpy()) if weighted else None
    for _, train, test in folds(events, by):
        fitted = clone(model)
        if isinstance(fitted, ColumnModel) and weights is not None:
            fitted.fit(events[train], y[train], sample_weight=weights[train])
        else:
            fitted.fit(events[train], y[train])
        predictions[test] = fitted.predict(events[test])
    return predictions


def score(events: pd.DataFrame, predicted_slr: np.ndarray) -> dict:
    """Error of a ratio prediction, as ratio and as inches of snow given the observed liquid."""
    slr = events["slr"].to_numpy()
    liquid = events["liquid_mm"].to_numpy()
    snow_error_in = (predicted_slr - slr) * liquid / MM_PER_IN
    residual = slr - predicted_slr
    return {
        "n": int(len(events)),
        "slr_mae": float(np.abs(residual).mean()),
        "slr_bias": float(-residual.mean()),
        "r2": float(1 - (residual ** 2).sum() / ((slr - slr.mean()) ** 2).sum()),
        "snow_mae_in": float(np.abs(snow_error_in).mean()),
        "snow_bias_in": float(snow_error_in.mean()),
        "snow_rmse_in": float(np.sqrt((snow_error_in ** 2).mean())),
    }


def cross_validate(events: pd.DataFrame, models: dict | None = None, by: str = "season") -> tuple:
    """Score every candidate out of fold. Returns (score table, {name: predictions})."""
    models = models or candidates()
    rows, predictions = [], {}
    for name, model in models.items():
        predictions[name] = out_of_fold(events, model, by)
        rows.append({"model": name, **score(events, predictions[name])})
    return pd.DataFrame(rows).set_index("model"), predictions


def train_on_apply_to(train: pd.DataFrame, test: pd.DataFrame, models: dict | None = None) -> pd.DataFrame:
    """Fit on one table and score on another (for transfer tests such as manual stations to SNOTEL)."""
    rows = []
    for name, model in (models or candidates()).items():
        fitted = clone(model)
        if isinstance(fitted, ColumnModel):
            fitted.fit(train, train["slr"].to_numpy(), sample_weight=np.sqrt(train["liquid_mm"].to_numpy()))
        else:
            fitted.fit(train, train["slr"].to_numpy())
        rows.append({"model": name, **score(test, fitted.predict(test))})
    return pd.DataFrame(rows).set_index("model")


def learning_curve(events: pd.DataFrame, model, seasons_per_step: list) -> pd.DataFrame:
    """Held-out-season error as a function of how many other seasons were used for training."""
    seasons = sorted(events["season"].unique())
    rows = []
    for count in seasons_per_step:
        errors = []
        for held in seasons:
            others = [s for s in seasons if s != held]
            if count > len(others):
                continue
            # Every contiguous run of `count` training seasons, to average out which seasons are picked.
            for start in range(len(others) - count + 1):
                train = events[events["season"].isin(others[start:start + count])]
                test = events[events["season"] == held]
                fitted = clone(model).fit(train, train["slr"].to_numpy())
                errors.append(score(test, fitted.predict(test))["snow_mae_in"])
        if errors:
            rows.append({"train_seasons": count, "snow_mae_in": float(np.mean(errors)), "runs": len(errors)})
    return pd.DataFrame(rows)


def fit_final(events: pd.DataFrame, name: str, model) -> ColumnModel:
    fitted = clone(model)
    if isinstance(fitted, ColumnModel):
        fitted.fit(events, events["slr"].to_numpy(), sample_weight=np.sqrt(events["liquid_mm"].to_numpy()))
    else:
        fitted.fit(events, events["slr"].to_numpy())
    MODELS.mkdir(parents=True, exist_ok=True)
    joblib.dump(fitted, MODELS / MODEL_FILE)
    sidecar = {"model": name, "features": list(getattr(fitted, "columns", None) or []), "events": int(len(events)),
               "stations": int(events["station"].nunique()), "seasons": sorted(int(s) for s in events["season"].unique()),
               "first_date": str(events["date"].min().date()), "last_date": str(events["date"].max().date())}
    (MODELS / "snow_ratio.json").write_text(json.dumps(sidecar, indent=2))
    return fitted


def load():
    return joblib.load(MODELS / MODEL_FILE)
