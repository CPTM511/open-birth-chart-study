"""Reconstruct the Qing Yuebo (highest longitude) calculation in a separate version."""
from datetime import datetime, timedelta, timezone
from math import atan2, cos, degrees, isfinite, radians, remainder, sin

from open_birth_chart import astronomy

VERSION = "OBS-R19-QING-YUEBO-1.0"
DAYS_PER_YEAR = 365.24233442
DAYS_AFTER_LOCAL_MIDNIGHT = 0.12254
BEIJING_EAST_DEG = 116.4
ROTATION_ORIGIN_DEG = 270.0  # first mansion palace at the winter solstice origin
SOLAR_MEAN_ARCSEC_PER_DAY = 3548.3290897
SOLAR_PERIGEE_ARCSEC_PER_YEAR = 62.9975
SOLAR_PERIGEE_ARCSEC_PER_DAY = .17248
SOLAR_PERIGEE_EPOCH_DEG = 8 + 7/60 + (32 + 22/60)/3600
SOLAR_AXIS = 10_000_000
SOLAR_B = 9_998_571.85
SOLAR_FOCAL_DISTANCE = 169_000
APSE_ARCSEC_PER_DAY = 401.070226
APSE_EPOCH_DEG = 8*30 + 1 + 15/60 + (45 + 38/60)/3600
APSE_AVERAGE_ARCSEC = 1196
SOLAR_MAX_ARCSEC = (6973, 6913)
EPICYCLE_RADIUS = 117_315
DEFERENT_RADIUS = 550_505

LOCAL_ZERO = datetime(1722,12,22,tzinfo=timezone.utc)
SOLSTICE = astronomy.julian_day(
    LOCAL_ZERO + timedelta(days=DAYS_AFTER_LOCAL_MIDNIGHT, hours=-BEIJING_EAST_DEG/15))
NEXT_MIDNIGHT = astronomy.julian_day(
    LOCAL_ZERO + timedelta(days=1,hours=-BEIJING_EAST_DEG/15))


def solar_equation(mean_anomaly_deg):
    """Volume 50's double triangle angle plus signed ellipse/sector correction."""
    if not isfinite(mean_anomaly_deg):
        raise ValueError("Finite mean anomaly required")
    a = radians(remainder(mean_anomaly_deg,360))
    big_angle = 2*atan2(SOLAR_FOCAL_DISTANCE*sin(a),SOLAR_AXIS-SOLAR_FOCAL_DISTANCE*cos(a))
    ellipse = atan2(SOLAR_AXIS*sin(a),SOLAR_B*cos(a))-a
    return degrees(big_angle+ellipse)


def source_angles(jd):
    """Historical mean inputs from the stated Qing epoch and stated rates."""
    if not isfinite(jd) or jd < NEXT_MIDNIGHT:
        raise ValueError("Use a finite nominal UT date after the 1722 epoch")
    elapsed=jd-NEXT_MIDNIGHT
    mean = (ROTATION_ORIGIN_DEG + (jd-SOLSTICE)*SOLAR_MEAN_ARCSEC_PER_DAY/3600) % 360
    # The printed procedure uses integer 節年 and elapsed days after the next local midnight.
    whole_years = int((jd-SOLSTICE)//DAYS_PER_YEAR)
    next_root_day = (SOLSTICE + whole_years*DAYS_PER_YEAR + BEIJING_EAST_DEG/360 + .5)//1
    next_root_day = next_root_day + .5 - BEIJING_EAST_DEG/360
    previous_day_difference = jd-next_root_day
    perigee = (ROTATION_ORIGIN_DEG + SOLAR_PERIGEE_EPOCH_DEG +
              (whole_years*SOLAR_PERIGEE_ARCSEC_PER_YEAR +
               previous_day_difference*SOLAR_PERIGEE_ARCSEC_PER_DAY)/3600) % 360
    equ = solar_equation(mean-perigee)
    return (ROTATION_ORIGIN_DEG + APSE_EPOCH_DEG + elapsed*APSE_ARCSEC_PER_DAY/3600) % 360, equ, (mean+equ)%360


def apse_offset(solar_separation_deg):
    d = radians((2*solar_separation_deg)%360)
    return degrees(atan2(EPICYCLE_RADIUS*sin(d),DEFERENT_RADIUS+EPICYCLE_RADIUS*cos(d)))


def calculate(highest_mean_deg, solar_equation_deg, solar_true_deg, solar_maximum_arcsec=6973):
    """Signed highest mean correction, triangle and final true highest longitude."""
    if not all(isfinite(x) for x in (highest_mean_deg,solar_equation_deg,solar_true_deg)):
        raise ValueError("Three finite source angles required")
    if solar_maximum_arcsec not in SOLAR_MAX_ARCSEC:
        raise ValueError("Only the two source readings are supported")
    annual = solar_equation_deg*APSE_AVERAGE_ARCSEC/solar_maximum_arcsec
    use = (highest_mean_deg+annual)%360
    separation = (solar_true_deg-use)%360
    correction = apse_offset(separation)
    return {"historical_mean_deg":highest_mean_deg%360,"annual_correction_deg":annual,
            "highest_in_use_deg":use,"sun_minus_highest_in_use_deg":separation,
            "highest_true_equation_deg":correction,"highest_true_deg":(use+correction)%360}
