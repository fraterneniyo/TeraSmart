# ihingaai_predict.py - IhingaAI v1 prototype predictor (EXPERIMENTAL)
# Small-scale farmers only; maize (A, B), bush bean (A, B, C), Irish potato (A, B, C).
# Estimates are a rough guide from 2025 survey patterns, not a validated forecast.

import math
import pickle
import numpy as np
import pandas as pd

CROP_NAMES = {"101": "Maize", "106": "Bush bean", "110": "Irish potato"}
FARMER_TYPES = {"1": "Small-scale individual", "2": "Small-scale organization",
                "3": "Large-scale individual", "4": "Large-scale organization"}


def _code(x):
    try:
        return str(int(float(str(x).strip())))
    except (ValueError, TypeError):
        return None


class IhingaPredictorV1:
    def __init__(self, frozen_path):
        with open(frozen_path, "rb") as f:
            fz = pickle.load(f)
        if fz.get("version") != "IhingaAI_v1":
            raise ValueError("Unexpected model version.")
        self.pipe = fz["pipeline"]
        self.features = list(fz["features"])
        self.schema = fz["input_schema"]
        self.conformal = fz["conformal"]
        self.level = 1 - fz["alpha"]
        cats = self.schema["categorical"]
        self.maps = {c: {(_code(v) if c != "season" else str(v).upper()): v for v in cats[c]} for c in cats}
        self.supported = {tuple(x) for x in self.schema["supported_crop_seasons"]}
        self.scope = set(self.schema["scope_farmer_types"])
        self.area_ranges = self.schema["plot_area_ha_training_range_by_crop"]

    def predict(self, crop_code, season, district_code, farmer_type_code,
                plot_area_ha=None, plot_area_sqm=None):
        crop, ft, dist = _code(crop_code), _code(farmer_type_code), _code(district_code)
        season = str(season).strip().upper()
        out = {"model_version": "IhingaAI_v1 (experimental prototype)", "status": None,
               "crop": CROP_NAMES.get(crop), "season": season,
               "estimate_kg": None, "lower_kg": None, "upper_kg": None,
               "interval_level": self.level, "warnings": [], "message": None}

        errors = []
        if crop not in CROP_NAMES:
            errors.append("Crop not supported (supported: maize, bush bean, Irish potato).")
        if season not in {"A", "B", "C"}:
            errors.append("Season must be A, B or C.")
        if ft not in FARMER_TYPES:
            errors.append("Farmer type must be 1-4.")
        if dist not in self.maps["district_code"]:
            errors.append("District code not recognised.")
        area = None
        try:
            if plot_area_ha is not None:
                area = float(plot_area_ha)
            elif plot_area_sqm is not None:
                area = float(plot_area_sqm) / 10000
        except (ValueError, TypeError):
            area = None
        if area is None or not math.isfinite(area) or area <= 0:
            errors.append("Whole-plot area must be a positive number.")
        if errors:
            out["status"] = "invalid_input"
            out["message"] = " ".join(errors)
            return out

        if (crop, season) not in self.supported:
            out["status"] = "unsupported_crop_season"
            out["message"] = "No estimate: " + CROP_NAMES[crop] + " in Season " + season + " is not supported by this model."
            return out
        if ft not in self.scope:
            out["status"] = "outside_scope"
            out["message"] = ("No estimate: this prototype is validated only for small-scale farmers. "
                              "Large-scale farm production could not be predicted reliably from these inputs.")
            return out
        rng = self.area_ranges[crop]
        if area > rng["max"]:
            out["status"] = "outside_area_range"
            out["message"] = "No estimate: plot is larger than any comparable plot in the 2025 survey data."
            return out

        if not (rng["p01"] <= area <= rng["p99"]):
            out["warnings"].append("Plot size is unusual compared with survey plots; estimate is less reliable "
                                   "(tested: large plots tended to be underestimated).")
        if season == "C":
            out["warnings"].append("Season C estimates are based on few survey records.")
        if ft == "2":
            out["warnings"].append("Very few small-scale organisations in the data; estimate is less certain.")
        if (crop, season) == ("101", "B"):
            out["warnings"].append("Maize Season B estimates were less stable in testing.")

        row = pd.DataFrame([{"crop_code": self.maps["crop_code"][crop],
                             "season": self.maps["season"][season],
                             "district_code": self.maps["district_code"][dist],
                             "farmer_type_code": self.maps["farmer_type_code"][ft],
                             "plot_area_ha": area}])[self.features]
        per_ha = max(float(self.pipe.predict(row)[0]), 0.0)
        q = self.conformal[crop]
        base = np.log1p(per_ha)
        lower = max(float(np.expm1(base + q["lower_log_offset"])), 0.0) * area
        upper = max(float(np.expm1(base + q["upper_log_offset"])), 0.0) * area
        est = per_ha * area

        out.update(status="ok", estimate_kg=est, lower_kg=lower, upper_kg=upper)
        out["message"] = ("Likely range: about {:,.0f} to {:,.0f} kg of {} this season "
                          "(typical estimate about {:,.0f} kg). In testing on 2025 survey plots, "
                          "ranges like this contained the actual harvest about 8 times out of 10. "
                          "This is a rough guide based on past survey patterns, not a guarantee, "
                          "and it does not show what any farming practice would change."
                          ).format(lower, upper, CROP_NAMES[crop].lower(), est)
        return out
