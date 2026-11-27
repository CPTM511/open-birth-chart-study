"""Propagate catalogue directions and find the intersections of RA meridians and the ecliptic."""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, degrees, radians, sin

import erfa
import numpy as np
import swisseph as swe


J2000 = 2451545.0
JULIAN_YEAR_DAYS = 365.25
HIPPARCOS_EPOCH = J2000 + (1991.25 - 2000.0) * JULIAN_YEAR_DAYS
MAS_PER_DEGREE = 3600000.0


def signed_degrees(angle):
    return (angle + 180.0) % 360.0 - 180.0


@dataclass(frozen=True)
class Star:
    ra_deg: float
    dec_deg: float
    pm_ra: float
    pm_dec: float

    def direction(self, years):
        ra, dec = radians(self.ra_deg), radians(self.dec_deg)
        east = np.array([-sin(ra), cos(ra), 0.0])
        north = np.array([-cos(ra) * sin(dec), -sin(ra) * sin(dec), cos(dec)])
        start = np.array([cos(ra) * cos(dec), sin(ra) * cos(dec), sin(dec)])
        velocity = radians(self.pm_ra / MAS_PER_DEGREE) * east + radians(self.pm_dec / MAS_PER_DEGREE) * north
        return start + years * velocity


@dataclass(frozen=True)
class Epoch:
    jd_tt: float
    years_since_hipparcos: float
    precession_matrix: np.ndarray
    obliquity: float

    @classmethod
    def from_ut(cls, jd_ut):
        jd_tt = jd_ut + swe.deltat(jd_ut)
        return cls(jd_tt, (jd_tt - HIPPARCOS_EPOCH) / JULIAN_YEAR_DAYS,
                   erfa.pmat06(J2000, jd_tt - J2000), float(erfa.obl06(J2000, jd_tt - J2000)))

    def right_ascension(self, star, *, proper_motion=True):
        x, y, _ = self.precession_matrix @ star.direction(self.years_since_hipparcos if proper_motion else 0.0)
        return degrees(atan2(y, x)) % 360.0

    def meridian_longitude(self, right_ascension):
        ra = radians(right_ascension)
        return degrees(atan2(sin(ra), cos(ra) * cos(self.obliquity))) % 360.0

    def ecliptic_right_ascension(self, longitude):
        angle = radians(longitude)
        return degrees(atan2(sin(angle) * cos(self.obliquity), cos(angle))) % 360.0


def independent_longitude(star, epoch):
    """Catalogue space motion and IAU 1976 precession, with a plane-intersection projection."""
    ra, dec = radians(star.ra_deg), radians(star.dec_deg)
    pv = erfa.s2pv(ra, dec, 1.0, radians(star.pm_ra / MAS_PER_DEGREE) / cos(dec),
                  radians(star.pm_dec / MAS_PER_DEGREE), 0.0)
    ra, dec = erfa.c2s(erfa.pvu(epoch.years_since_hipparcos, pv)["p"])

    # IAU 1976 precession from J2000, where the frame bias relative to ICRS is below 0.03 arcsec.
    t = (epoch.jd_tt - J2000) / 36525.0
    zeta = radians((2306.2181 * t + 0.30188 * t**2 + 0.017998 * t**3) / 3600)
    z = radians((2306.2181 * t + 1.09468 * t**2 + 0.018203 * t**3) / 3600)
    theta = radians((2004.3109 * t - 0.42665 * t**2 - 0.041833 * t**3) / 3600)
    numerator = cos(dec) * sin(ra + zeta)
    denominator = cos(theta) * cos(dec) * cos(ra + zeta) - sin(theta) * sin(dec)
    precessed = atan2(numerator, denominator) + z

    eps = radians((84381.448 - 46.8150 * t - 0.00059 * t**2 + 0.001813 * t**3) / 3600)
    meridian_normal = [-sin(precessed), cos(precessed), 0]
    ecliptic_normal = [0, -sin(eps), cos(eps)]
    line = np.cross(meridian_normal, ecliptic_normal)
    return degrees(atan2(np.dot(line, [0, cos(eps), sin(eps)]), line[0])) % 360.0
