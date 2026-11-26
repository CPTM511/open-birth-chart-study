# SPDX-License-Identifier: AGPL-3.0-or-later
"""Checks at astronomical, historical-definition and date-boundary risk points."""
import math
import unittest
import astronomy as independent
import swisseph as swe
from open_birth_chart import astronomy as a
from open_birth_chart import qizheng_engine as q
from open_birth_chart import western_engine as w


SYNTHETIC = {"study_id":"synthetic-2000-greenwich", "birth_local":"2000-01-01T12:00:00",
             "birth_utc":"2000-01-01T12:00:00Z", "source_offset_seconds":0,
             "latitude":51.5, "longitude":0, "calendar":"gregorian"}


class AstronomicalChecks(unittest.TestCase):
    def test_time_offset_and_missing_clock(self):
        self.assertEqual(a.normalize_birth(SYNTHETIC)["jd_ut"],2451545.0)
        with self.assertRaises(a.InputError):
            a.normalize_birth(SYNTHETIC | {"birth_local":"2000-01-01"})
        with self.assertRaises(a.InputError):
            a.normalize_birth(SYNTHETIC | {"source_offset_seconds":3600})
        self.assertAlmostEqual(a.normalize_birth(SYNTHETIC,30)["jd_ut"],2451545+30/1440)

    def test_ten_bodies_against_independent_engine(self):
        # Astronomy Engine advertises arcminute-class accuracy. Future delta-T
        # models differ, so this limit uses nominal-UT rather than fitted TT.
        for year in (1880,1950,2000,2026,2070):
            jd=swe.julday(year,6,15,12)
            t=independent.Time(jd-2451545)
            for name in a.TEN:
                other=independent.Ecliptic(independent.GeoVector(getattr(independent.Body,name),t,True))
                self.assertLess(a.circular_distance(a.position(jd,name)["longitude"],other.elon)*3600,60,
                                (year,name))

    def test_house_angles_analytic_geometry_and_poles(self):
        jd=2451545.0
        for lat,lon in ((0,0),(51.5,0),(-33.9,151.2),(40,-75)):
            h=a.houses(jd,lat,lon)
            theta=math.radians(h["ARMC"]); eps=math.radians(a.obliquity(jd))
            asc=math.degrees(math.atan2(math.cos(theta),-math.sin(theta)*math.cos(eps)-math.tan(math.radians(lat))*math.sin(eps)))%360
            self.assertLess(a.circular_distance(asc,h["Ascendant"]),1e-8)
            self.assertEqual(len(h["cusps"]),12)
        self.assertEqual(len(a.houses(jd,80,20)["cusps"]),12)
        with self.assertRaises(a.InputError): a.houses(jd,90,0)


class HistoricalDefinitionChecks(unittest.TestCase):
    def test_absolute_ziqi_not_arbitrary_phase(self):
        self.assertAlmostEqual(q.ziqi_epoch()["jd_ut"],2358033.176666667,8)
        self.assertAlmostEqual(q.ziqi_longitude(q.ziqi_epoch()["jd_ut"]),137.8374675925926,10)
        # Directly verified primary scan: Daoguang13 p40, first lunar month day1.
        p=q.qizheng_sky(2390599.5-116.4/360)["Ziqi"]
        self.assertEqual(p["mansion"]["name"],"角")
        self.assertLess(abs(p["mansion"]["degree_in_mansion"]-(2+38/60))*60,1)

    def test_all28_unequal_mansions_cover_circle(self):
        for jd in (q.MANSION_EPOCH_JD,2451545.0,swe.julday(2070,7,1,0)):
            starts=q.mansion_boundaries(jd)
            widths=[(starts[(i+1)%28]-starts[i])%360 for i in range(28)]
            self.assertAlmostEqual(sum(widths),360,8)
            self.assertGreater(max(widths)/min(widths),10)
            for i,start in enumerate(starts):
                self.assertEqual(q.mansion((start+widths[i]/2)%360,jd)["index"],i)

    def test_four_points_exist_and_nodes_have_qing_names(self):
        p=q.qizheng_sky(2451545.0)
        self.assertEqual(len(p),11)
        self.assertAlmostEqual(a.circular_distance(p["Luohou"]["longitude"],p["Jidu"]["longitude"]),180)
        self.assertEqual(p["Jidu"]["longitude"],a.position(2451545.0,"TrueNode")["longitude"])
        self.assertEqual(p["Yuebo"]["longitude"],a.position(2451545.0,"MeanApogee")["longitude"])
        alt=q.qizheng_sky(2451545.0,"osculating")
        self.assertGreater(a.circular_distance(p["Yuebo"]["longitude"],alt["Yuebo"]["longitude"]),1)
        self.assertEqual(p["Ziqi"]["longitude"],alt["Ziqi"]["longitude"])

    def test_no_invented_extension_after_major_period_end(self):
        n=q.build_natal(SYNTHETIC)
        jd=n["birth"]["jd_ut"]
        self.assertEqual(q.major_period(n,jd)["name"],"命")
        self.assertEqual(q.major_period(n,jd+15*a.TROPICAL_YEAR_DAYS+.001)["name"],"相貌")
        self.assertIsNone(q.major_period(n,jd+101*a.TROPICAL_YEAR_DAYS))
        old=q.build_natal(SYNTHETIC|{"birth_local":"1880-01-01T12:00:00",
                                     "birth_utc":"1880-01-01T12:00:00Z"})
        self.assertIsNone(q.annual_signals(old,1985)["primary_score"])

    def test_birthdays_not_january_reset(self):
        n=q.build_natal(SYNTHETIC | {"birth_local":"2000-08-01T12:00:00",
                                    "birth_utc":"2000-08-01T12:00:00Z"})
        self.assertEqual(q.minor_period(n,swe.julday(2026,7,31,12))["completed_birthdays"],25)
        self.assertEqual(q.minor_period(n,swe.julday(2026,8,1,12))["completed_birthdays"],26)


class WorkflowChecks(unittest.TestCase):
    def test_secondary_zero_identity_and_day_year_mapping(self):
        n=w.build_natal(SYNTHETIC); jd=n["birth"]["jd_ut"]
        z=w.progressed_chart(n,jd)
        self.assertLess(a.circular_distance(z["angles"]["Ascendant"],n["angles"]["Ascendant"]),1e-8)
        for body in a.TEN:
            self.assertEqual(z["planets"][body]["longitude"],n["planets"][body]["longitude"])
        p=w.progressed_chart(n,jd+30*a.TROPICAL_YEAR_DAYS)
        self.assertAlmostEqual(p["progressed_jd_ut"],jd+30,8)
        self.assertAlmostEqual((p["houses"]["ARMC"]-n["houses"]["ARMC"])%360,30*.98564733,8)

    def test_compact_full_equal_and_twelve_samples(self):
        for engine in (w,q):
            for birth in (SYNTHETIC,SYNTHETIC|{"latitude":-33.9,"longitude":151.2}):
                n=engine.build_natal(birth)
                for year in (2026,2040,2059):
                    compact=engine.annual_signals(n,year)
                    full=engine.annual_signals(n,year,include_details=True)
                    self.assertEqual(compact["primary_score"],full["primary_score"])
                    self.assertEqual(compact["components"],full["components"])
                    self.assertEqual(len(full["details"]),12)
                    self.assertTrue(0<=full["primary_score"]<=1)

    def test_model_completeness_is_not_predictive_validation(self):
        for engine in (w,q):
            n=engine.build_natal(SYNTHETIC)
            self.assertFalse(n["module_completeness"]["empirically_validated_prediction"])
            self.assertIsNone(engine.annual_signals(n,1999)["primary_score"])


if __name__ == "__main__": unittest.main()
