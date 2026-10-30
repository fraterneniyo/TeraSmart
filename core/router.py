# router.py - routes each crop to the right frozen model (EXPERIMENTAL)
import json
import math
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

from .predictor import IhingaPredictorV1, _code

SCOPE = {"1", "2"}


class ExtensionPredictor:
    def __init__(self, path):
        with open(path, "rb") as f:
            fz = pickle.load(f)
        if fz.get("version") != "IhingaAI_Extension_v1":
            raise ValueError("Unexpected extension model version.")
        self.pipes = fz["pipelines"]
        self.features = list(fz["features"])
        self.schema = fz["input_schema"]
        self.conformal = fz["conformal"]
        self.group_of = self.schema["crop_model_group"]
        cats = self.schema["categorical"]
        self.maps = {c: {(_code(v) if c != "season" else str(v).upper()): v for v in cats[c]} for c in cats}
        self.area_ranges = self.schema["plot_area_ha_training_range_by_crop"]

    def predict(self, crop, season, dist, ft, area):
        if dist not in self.maps["district_code"]:
            return {"status": "unsupported_district"}
        if area > self.area_ranges[crop]["max"]:
            return {"status": "outside_area_range"}
        row = pd.DataFrame([{"crop_code": self.maps["crop_code"][crop],
                             "season": self.maps["season"][season],
                             "district_code": self.maps["district_code"][dist],
                             "farmer_type_code": self.maps["farmer_type_code"][ft],
                             "plot_area_ha": area}])[self.features]
        per_ha = max(float(self.pipes[self.group_of[crop]].predict(row)[0]), 0.0)
        q = self.conformal[crop]
        base = np.log1p(per_ha)
        lower = max(float(np.expm1(base + q["lower_log_offset"])), 0.0) * area
        upper = max(float(np.expm1(base + q["upper_log_offset"])), 0.0) * area
        return {"status": "ok", "estimate_kg": per_ha * area, "lower_kg": lower, "upper_kg": upper}


class IhingaRouter:
    def __init__(self, data_dir):
        data_dir = Path(data_dir)
        with open(data_dir / "crop_catalog.json", encoding="utf-8") as f:
            self.catalog = json.load(f)
        with open(data_dir / "district_labels.json", encoding="utf-8") as f:
            self.districts = set(json.load(f)["districts"])
        self.v1 = IhingaPredictorV1(data_dir / "IhingaAI_Frozen_Model_v1.pkl")
        self.ext = ExtensionPredictor(data_dir / "IhingaAI_Frozen_Extension_v1.pkl")

    def crops(self):
        return list(self.catalog)

    def seasons(self, crop):
        return sorted(self.catalog[crop]["seasons"])

    def predict(self, crop_code, season, district_code, farmer_type_code,
                plot_area_ha=None, plot_area_sqm=None, harvest_this_season=None):
        crop, ft, dist = _code(crop_code), _code(farmer_type_code), _code(district_code)
        season = str(season).strip().upper()
        out = {"status": None, "crop_code": crop, "season": season, "estimate_kg": None,
               "lower_kg": None, "upper_kg": None, "warnings": [], "evidence": None,
               "coverage_in_10": None, "model": None}
        area = None
        try:
            if plot_area_ha is not None:
                area = float(plot_area_ha)
            elif plot_area_sqm is not None:
                area = float(plot_area_sqm) / 10000
        except (ValueError, TypeError):
            area = None
        if (crop not in self.catalog or season not in {"A", "B", "C"} or ft not in {"1", "2", "3", "4"}
                or dist not in self.districts or area is None or not math.isfinite(area) or area <= 0):
            out["status"] = "invalid_input"
            return out
        entry = self.catalog[crop]
        combo = entry["seasons"].get(season)
        if combo is None:
            out["status"] = "unsupported_crop_season"
            return out
        if ft not in SCOPE:
            out["status"] = "outside_scope"
            return out
        if entry["harvest_question"] and harvest_this_season is False:
            out["status"] = "no_harvest_this_season"
            return out
        out.update(evidence=combo["evidence"], coverage_in_10=combo["coverage_in_10"], model=entry["model"])
        if entry["model"] == "v1":
            r = self.v1.predict(crop, season, dist, ft, plot_area_ha=area)
            ranges = self.v1.area_ranges
        else:
            r = self.ext.predict(crop, season, dist, ft, area)
            ranges = self.ext.area_ranges
        if r["status"] != "ok":
            out["status"] = r["status"]
            return out
        out.update(status="ok", estimate_kg=r["estimate_kg"], lower_kg=r["lower_kg"], upper_kg=r["upper_kg"])
        rg, w = ranges[crop], out["warnings"]
        if not (rg["p01"] <= area <= rg["p99"]):
            w.append("w_size")
        if season == "C":
            w.append("w_season_c")
        if ft == "2":
            w.append("w_group")
        if (crop, season) == ("101", "B"):
            w.append("w_maize_b")
        if combo["evidence"] == "limited":
            w.append("w_limited_evidence")
        if entry["perennial"]:
            w.append("w_perennial")
        if entry["harvest_question"]:
            w.append("w_harvest_conditional")
        return out
