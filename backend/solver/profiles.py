"""
Time-Series Profiles
====================
Built-in 24-hour load and irradiance profiles for Phase 2 time-series simulation.

Reference location: Bucharest, Romania (44.4°N, 26.1°E)
Time resolution: 30-minute intervals (48 points per 24 hours)
Time zone: EET (UTC+2 winter, UTC+3 summer — Romania)

Profile sources and methodology:
  - Residential load: based on ENTSO-E Romanian demand patterns and
    typical household consumption studies for Eastern Europe.
    Characterised by two daily peaks: morning (07:00-09:00) and
    evening (18:00-22:00), with a midday trough.
  - Industrial load: flatter profile with shift-work pattern.
    Higher daytime consumption, reduced nights and weekends.
  - Solar irradiance: clear-sky model based on solar geometry at 44.4°N.
    Summer uses June 21 (solstice) parameters.
    Winter uses December 21 (solstice) parameters.
    Values in kW/m² at horizontal surface (GHI — Global Horizontal Irradiance).
    Peak clear-sky GHI for Bucharest: ~0.85 kW/m² summer, ~0.35 kW/m² winter.

All profiles are normalised to a peak value of 1.0.
Actual values are obtained by multiplying by the peak_load_multiplier parameter.

Index mapping:
  Index 0  = 00:00 – 00:30
  Index 1  = 00:30 – 01:00
  ...
  Index 23 = 11:30 – 12:00
  Index 24 = 12:00 – 12:30
  ...
  Index 47 = 23:30 – 24:00
"""

from __future__ import annotations
from dataclasses import dataclass
import math


# ─────────────────────────────────────────────────────────────────────────────
# RAW PROFILES (48 points, normalised 0.0 – 1.0)
# ─────────────────────────────────────────────────────────────────────────────

# Residential load profile — Romania
# Two peaks: morning commute (07:00–09:00) and evening (19:00–22:00)
# Night trough (01:00–05:00) at ~25% of peak
RESIDENTIAL_LOAD_PROFILE = [
    0.30, 0.27, 0.25, 0.24,  # 00:00 – 02:00  night trough
    0.23, 0.23, 0.24, 0.26,  # 02:00 – 04:00  deep night
    0.28, 0.32, 0.45, 0.65,  # 04:00 – 06:00  early morning rise
    0.82, 0.95, 1.00, 0.92,  # 06:00 – 08:00  morning peak
    0.80, 0.68, 0.58, 0.52,  # 08:00 – 10:00  post-morning drop
    0.50, 0.49, 0.50, 0.52,  # 10:00 – 12:00  midday trough
    0.54, 0.56, 0.58, 0.60,  # 12:00 – 14:00  early afternoon
    0.58, 0.56, 0.55, 0.57,  # 14:00 – 16:00  afternoon
    0.62, 0.70, 0.80, 0.90,  # 16:00 – 18:00  evening ramp-up
    0.97, 1.00, 0.98, 0.95,  # 18:00 – 20:00  evening peak
    0.90, 0.82, 0.72, 0.60,  # 20:00 – 22:00  post-evening decline
    0.48, 0.40, 0.35, 0.32,  # 22:00 – 24:00  night wind-down
]

# Industrial load profile — Romania
# Flatter than residential; three-shift pattern with reduced nights
# and a slight midday dip (lunch break / process changeover)
INDUSTRIAL_LOAD_PROFILE = [
    0.55, 0.53, 0.52, 0.51,  # 00:00 – 02:00  night shift (reduced)
    0.50, 0.50, 0.51, 0.52,  # 02:00 – 04:00  night shift
    0.54, 0.58, 0.70, 0.85,  # 04:00 – 06:00  morning shift ramp
    0.92, 0.97, 1.00, 1.00,  # 06:00 – 08:00  day shift peak
    0.99, 0.98, 0.97, 0.95,  # 08:00 – 10:00  full production
    0.94, 0.93, 0.90, 0.88,  # 10:00 – 12:00  slight pre-lunch dip
    0.82, 0.85, 0.92, 0.95,  # 12:00 – 14:00  lunch break + recovery
    0.97, 0.98, 0.98, 0.97,  # 14:00 – 16:00  afternoon production
    0.95, 0.93, 0.88, 0.80,  # 16:00 – 18:00  afternoon shift end
    0.72, 0.68, 0.65, 0.63,  # 18:00 – 20:00  evening shift (reduced)
    0.61, 0.60, 0.59, 0.58,  # 20:00 – 22:00  night shift transition
    0.57, 0.56, 0.56, 0.55,  # 22:00 – 24:00  night shift settled
]

# Solar irradiance profile — Summer (June 21, Bucharest 44.4°N)
# Sunrise ~05:30, Sunset ~21:00 (local solar time, EET+3 summer)
# Peak GHI ~0.85 kW/m² at solar noon (~13:00 local time)
# Normalised to 1.0 at peak
IRRADIANCE_SUMMER = [
    0.000, 0.000, 0.000, 0.000,  # 00:00 – 02:00  night
    0.000, 0.000, 0.000, 0.000,  # 02:00 – 04:00  night
    0.000, 0.000, 0.020, 0.080,  # 04:00 – 06:00  civil twilight / sunrise ~05:30
    0.180, 0.310, 0.440, 0.560,  # 06:00 – 08:00  morning climb
    0.660, 0.750, 0.820, 0.875,  # 08:00 – 10:00  mid-morning
    0.920, 0.960, 0.985, 1.000,  # 10:00 – 12:00  approaching solar noon
    0.995, 0.975, 0.940, 0.890,  # 12:00 – 14:00  solar noon ~13:00, afternoon
    0.825, 0.750, 0.660, 0.560,  # 14:00 – 16:00  afternoon decline
    0.450, 0.340, 0.230, 0.130,  # 16:00 – 18:00  late afternoon
    0.055, 0.010, 0.000, 0.000,  # 18:00 – 20:00  sunset ~20:45
    0.000, 0.000, 0.000, 0.000,  # 20:00 – 22:00  night
    0.000, 0.000, 0.000, 0.000,  # 22:00 – 24:00  night
]

# Solar irradiance profile — Winter (December 21, Bucharest 44.4°N)
# Sunrise ~07:50, Sunset ~16:10 (local solar time, EET+2 winter)
# Peak GHI ~0.35 kW/m² at solar noon (~12:10 local time)
# Normalised to 1.0 at peak (absolute values much lower than summer)
IRRADIANCE_WINTER = [
    0.000, 0.000, 0.000, 0.000,  # 00:00 – 02:00  night
    0.000, 0.000, 0.000, 0.000,  # 02:00 – 04:00  night
    0.000, 0.000, 0.000, 0.000,  # 04:00 – 06:00  night
    0.000, 0.000, 0.000, 0.050,  # 06:00 – 08:00  twilight / sunrise ~07:50
    0.220, 0.450, 0.650, 0.820,  # 08:00 – 10:00  rapid morning climb
    0.930, 0.990, 1.000, 0.985,  # 10:00 – 12:00  approaching solar noon
    0.950, 0.880, 0.770, 0.620,  # 12:00 – 14:00  solar noon ~12:10, rapid decline
    0.440, 0.240, 0.070, 0.000,  # 14:00 – 16:00  sunset ~16:10
    0.000, 0.000, 0.000, 0.000,  # 16:00 – 18:00  night
    0.000, 0.000, 0.000, 0.000,  # 18:00 – 20:00  night
    0.000, 0.000, 0.000, 0.000,  # 20:00 – 22:00  night
    0.000, 0.000, 0.000, 0.000,  # 22:00 – 24:00  night
]

# Peak absolute irradiance values for Bucharest (kW/m²)
# Used to scale normalised profiles back to physical units
PEAK_IRRADIANCE_SUMMER_KW_M2 = 0.85
PEAK_IRRADIANCE_WINTER_KW_M2 = 0.35


# ─────────────────────────────────────────────────────────────────────────────
# VALIDATION
# Ensure all profiles have exactly 48 points
# ─────────────────────────────────────────────────────────────────────────────

assert len(RESIDENTIAL_LOAD_PROFILE) == 48, "Residential profile must have 48 points"
assert len(INDUSTRIAL_LOAD_PROFILE)  == 48, "Industrial profile must have 48 points"
assert len(IRRADIANCE_SUMMER)        == 48, "Summer irradiance profile must have 48 points"
assert len(IRRADIANCE_WINTER)        == 48, "Winter irradiance profile must have 48 points"


# ─────────────────────────────────────────────────────────────────────────────
# PROFILE RESULT DATACLASS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ScaledProfiles:
    """
    Profiles scaled to actual physical values, ready for OpenDSS injection.

    residential_kw   : 48-point residential load curve in kW
                       (peak_kw × normalised_profile × peak_load_multiplier)
    industrial_kw    : 48-point industrial load curve in kW
    irradiance_kw_m2 : 48-point irradiance curve in kW/m²
    time_labels      : human-readable time labels for each interval
    season           : 'summer' or 'winter'
    peak_load_multiplier : the multiplier applied
    """
    residential_kw:       list[float]
    industrial_kw:        list[float]
    irradiance_kw_m2:     list[float]
    time_labels:          list[str]
    season:               str
    peak_load_multiplier: float


# ─────────────────────────────────────────────────────────────────────────────
# TIME LABEL GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

def _generate_time_labels() -> list[str]:
    """Generate 48 time labels for 30-minute intervals across 24 hours."""
    labels = []
    for i in range(48):
        hour   = i // 2
        minute = "30" if i % 2 else "00"
        labels.append(f"{hour:02d}:{minute}")
    return labels


TIME_LABELS = _generate_time_labels()


# ─────────────────────────────────────────────────────────────────────────────
# MAIN PROFILE GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

def get_scaled_profiles(
    peak_residential_kw:  float = 5.0,
    peak_industrial_kw:   float = 250.0,
    peak_load_multiplier: float = 1.0,
    season:               str   = "summer",
) -> ScaledProfiles:
    """
    Generate scaled 48-point profiles ready for OpenDSS injection.

    Parameters
    ----------
    peak_residential_kw : float
        The peak active power demand of the residential load in kW.
        Matches the kw field of a ResidentialLoad component.

    peak_industrial_kw : float
        The peak active power demand of the industrial load in kW.
        Matches the kw field of an IndustrialLoad component.

    peak_load_multiplier : float
        Scales all load profiles uniformly.
        1.0 = normal day, 1.3 = heavy load day, 0.7 = light load day.
        Valid range: 0.1 – 2.0

    season : str
        'summer' or 'winter'. Selects the appropriate irradiance profile
        and peak GHI value for Bucharest, Romania.

    Returns
    -------
    ScaledProfiles
        Object containing all scaled profiles and metadata.
    """

    # Clamp multiplier to valid range
    peak_load_multiplier = max(0.1, min(2.0, peak_load_multiplier))

    # Select irradiance profile and peak value
    if season.lower() == "winter":
        irradiance_normalised = IRRADIANCE_WINTER
        peak_ghi              = PEAK_IRRADIANCE_WINTER_KW_M2
    else:
        irradiance_normalised = IRRADIANCE_SUMMER
        peak_ghi              = PEAK_IRRADIANCE_SUMMER_KW_M2

    # Scale residential load
    residential_kw = [
        v * peak_residential_kw * peak_load_multiplier
        for v in RESIDENTIAL_LOAD_PROFILE
    ]

    # Scale industrial load
    industrial_kw = [
        v * peak_industrial_kw * peak_load_multiplier
        for v in INDUSTRIAL_LOAD_PROFILE
    ]

    # Scale irradiance to physical kW/m²
    # Note: irradiance is NOT affected by peak_load_multiplier —
    # the sun doesn't get brighter because there's more load
    irradiance_kw_m2 = [
        v * peak_ghi
        for v in irradiance_normalised
    ]

    return ScaledProfiles(
        residential_kw       = residential_kw,
        industrial_kw        = industrial_kw,
        irradiance_kw_m2     = irradiance_kw_m2,
        time_labels          = TIME_LABELS,
        season               = season,
        peak_load_multiplier = peak_load_multiplier,
    )


def get_profile_summary(profiles: ScaledProfiles) -> dict:
    """
    Return summary statistics for a set of scaled profiles.
    Useful for debugging and for the frontend to display context.
    """
    res = profiles.residential_kw
    ind = profiles.industrial_kw
    irr = profiles.irradiance_kw_m2

    peak_irr_idx = irr.index(max(irr)) if max(irr) > 0 else 0

    return {
        "season":               profiles.season,
        "peak_load_multiplier": profiles.peak_load_multiplier,
        "residential": {
            "peak_kw":    round(max(res), 2),
            "min_kw":     round(min(res), 2),
            "peak_time":  TIME_LABELS[res.index(max(res))],
        },
        "industrial": {
            "peak_kw":    round(max(ind), 2),
            "min_kw":     round(min(ind), 2),
            "peak_time":  TIME_LABELS[ind.index(max(ind))],
        },
        "irradiance": {
            "peak_kw_m2": round(max(irr), 3),
            "solar_noon": TIME_LABELS[peak_irr_idx],
            "daylight_hours": round(sum(1 for v in irr if v > 0.01) * 0.5, 1),
        },
    }
