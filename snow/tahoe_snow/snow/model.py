"""The snow model: hourly liquid and an upper-air profile in, hourly snowfall out."""
import numpy as np
import pandas as pd

from tahoe_snow.snow import features, phase

MIN_AMOUNT_MM = 2.5
# The ratio model saw few days above this much water; beyond it the amount is held constant.
MAX_AMOUNT_MM = 100.0
AMOUNT_WINDOW_H = 24


class SnowModel:
    """Snow fraction and snow ratio applied hour by hour."""

    def __init__(self, ratio_model, phase_kind: str, phase_params: dict):
        self.ratio_model = ratio_model
        self.phase_kind = phase_kind
        self.phase_params = phase_params

    def snowfall(self, hourly: pd.DataFrame, liquid_mm: pd.Series, elev_m: float) -> pd.DataFrame:
        """Hourly snowfall at ``elev_m``.

        ``hourly`` is features.hourly_features() for the profile; ``liquid_mm`` is the hourly liquid
        on the same index. Hours with missing profile data give NaN, never zero.
        """
        liquid = liquid_mm.reindex(hourly.index).astype(float)
        fraction = phase.hourly_fraction(hourly, elev_m, self.phase_kind, self.phase_params)
        # The ratio model was trained on storm-day totals, so it sees the surrounding 24 h amount.
        amount = liquid.fillna(0.0).rolling(AMOUNT_WINDOW_H, center=True, min_periods=1).sum()
        amount = amount.clip(lower=MIN_AMOUNT_MM, upper=MAX_AMOUNT_MM)
        rows = features.add_static(hourly, amount, elev_m, hourly.index.day_of_year)
        complete = rows[features.FEATURES].notna().all(axis=1).to_numpy()
        slr = np.full(len(rows), np.nan)
        if complete.any():
            slr[complete] = self.ratio_model.predict(rows.loc[complete])
        out = pd.DataFrame(index=hourly.index)
        out["liquid_mm"] = liquid
        out["snow_fraction"] = fraction
        out["slr"] = slr
        out["snow_cm"] = liquid * fraction * slr / 10.0
        out.loc[liquid == 0, "snow_cm"] = 0.0
        out["snow_level_m"] = hourly["snow_level_m"]
        return out
