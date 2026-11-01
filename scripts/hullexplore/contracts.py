"""Input contracts and explicit physical-unit conversions (no model imports)."""
from __future__ import annotations

import math
import os
from dataclasses import asdict, dataclass
from pathlib import Path, PureWindowsPath

MODEL_LENGTH = 3.0


def positive(value, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a positive finite number.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Provide {name} as a positive finite number.") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be positive and finite.")
    return number


def model_speed(speed, unit: str | None, scale: str | None, full_length: float | None) -> dict:
    value = positive(speed, "speed")
    if unit not in {"m/s", "km/h", "kn"}:
        raise ValueError("Specify speed_unit as m/s, km/h or kn.")
    if scale not in {"model", "full"}:
        raise ValueError("Specify speed_scale as model or full; m/s alone does not identify the scale.")
    factor = {"m/s": 1.0, "km/h": 1.0 / 3.6, "kn": 1852.0 / 3600.0}[unit]
    speed_ms = value * factor
    ratio = None if full_length is None else positive(full_length, "full_length") / MODEL_LENGTH
    if scale == "full" and ratio is None:
        raise ValueError("Full-scale speed requires the full-scale reference length.")
    return {
        "input_speed": value, "input_speed_unit": unit, "input_speed_scale": scale,
        "model_speed_m_s": speed_ms / math.sqrt(ratio) if scale == "full" else speed_ms,
        "model_length_m": MODEL_LENGTH,
        "full_length_m": full_length,
        "length_scale_ratio_full_to_model": ratio,
        "conversion": "Froude similarity" if scale == "full" else "unit conversion only",
    }


@dataclass
class Design:
    length: float
    beam: float
    depth: float
    draft: float
    displacement_volume: float
    density: float
    volume_tolerance: float = 0.05

    @classmethod
    def from_request(cls, values: dict) -> "Design":
        dims = {k: positive(values.get(k), k) for k in ("length", "beam", "depth", "draft")}
        if dims["draft"] > dims["depth"]:
            raise ValueError("Draft must not exceed molded depth.")
        density = positive(values.get("density", 1025.0), "density")
        alternatives = [k for k in ("displacement_tonnes", "displacement_volume", "block_coefficient")
                        if values.get(k) is not None]
        if len(alternatives) != 1:
            raise ValueError("Supply exactly one of displacement_tonnes, displacement_volume or block_coefficient.")
        key = alternatives[0]
        quantity = positive(values[key], key)
        if key == "displacement_tonnes":
            volume = quantity * 1000.0 / density
        elif key == "block_coefficient":
            if quantity >= 1:
                raise ValueError("The conventional block coefficient must be below 1.")
            volume = quantity * dims["length"] * dims["beam"] * dims["draft"]
        else:
            volume = quantity
        if volume >= dims["length"] * dims["beam"] * dims["draft"]:
            raise ValueError("Displacement volume must be smaller than the L x B x T bounding box.")
        tolerance = positive(values.get("volume_tolerance", 0.05), "volume_tolerance")
        if tolerance >= 1:
            raise ValueError("volume_tolerance must be a fraction between 0 and 1, e.g. 0.05.")
        return cls(**dims, displacement_volume=volume, density=density, volume_tolerance=tolerance)

    @property
    def draft_ratio(self) -> float:
        return self.draft / self.depth

    @property
    def physical_volume_ratio(self) -> float:
        return self.displacement_volume / (self.length * self.beam * self.depth)

    @property
    def block_coefficient(self) -> float:
        return self.displacement_volume / (self.length * self.beam * self.draft)

    def to_dict(self) -> dict:
        result = asdict(self)
        result.update({"displacement_tonnes": self.displacement_volume * self.density / 1000,
                       "draft_ratio": self.draft_ratio,
                       "physical_volume_ratio": self.physical_volume_ratio,
                       "block_coefficient": self.block_coefficient,
                       "length_scale_ratio_full_to_model": self.length / MODEL_LENGTH,
                       "units": {"length": "m", "beam": "m", "depth": "m", "draft": "m",
                                 "displacement_volume": "m^3", "density": "kg/m^3"}})
        return result


def domain_warnings(design: Design, speed: float | None, raw_condition: float | None = None) -> list[str]:
    """Report the supplied TD3 configuration's nominal sampling domain."""
    values = [("B/L", design.beam / design.length, 0.15, 0.25),
              ("D/L", design.depth / design.length, 0.07, 0.17),
              ("T/D", design.draft_ratio, 0.35, 0.60)]
    if speed is not None:
        values.append(("model speed (m/s)", speed, 0.6, 1.8))
    if raw_condition is not None:
        values.append(("internal raw-volume condition", raw_condition, 0.1, 0.5))
    return [f"TD3 extrapolation: {name}={value:.6g} is outside the nominal training range [{lo}, {hi}]."
            for name, value, lo, hi in values if not lo <= value <= hi]


def resolved_path(value: str | Path) -> Path:
    if os.name != "nt" and PureWindowsPath(str(value)).drive:
        raise ValueError("A Windows drive or UNC path cannot be used on this operating system. Run on the Windows machine or supply a local path for this device.")
    return Path(value).expanduser().resolve()
