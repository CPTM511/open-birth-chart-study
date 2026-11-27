from math import asin,cos,degrees,radians,sin,sqrt
import unittest
import qing_apogee as q


class CalendarAndGeometry(unittest.TestCase):
    def test_epoch_and_annual_proportions(self):
        m,e,s=q.source_angles(q.NEXT_MIDNIGHT)
        self.assertAlmostEqual(m,(270+q.APSE_EPOCH_DEG)%360,places=9)
        next_m,e,s=q.source_angles(q.NEXT_MIDNIGHT+1)
        self.assertAlmostEqual(next_m-m,q.APSE_ARCSEC_PER_DAY/3600)
        self.assertAlmostEqual(q.calculate(355,6973/3600,21)["annual_correction_deg"],1196/3600)
        self.assertAlmostEqual(q.calculate(355,-6913/3600,21,6913)["annual_correction_deg"],-1196/3600)

    def test_solar_equation_sign_and_quadrants(self):
        self.assertAlmostEqual(q.solar_equation(0),0)
        self.assertAlmostEqual(q.solar_equation(180),0)
        self.assertGreater(q.solar_equation(45),0)
        self.assertLess(q.solar_equation(270),0)
        self.assertAlmostEqual(q.solar_equation(90), -q.solar_equation(270))

    def test_absolute_triangle_matches_independent_law_of_sines(self):
        for d in range(0,361):
            theta=radians(d)
            other=sqrt(q.DEFERENT_RADIUS**2+q.EPICYCLE_RADIUS**2+
                       2*q.DEFERENT_RADIUS*q.EPICYCLE_RADIUS*cos(theta))
            law=degrees(asin(q.EPICYCLE_RADIUS*sin(theta)/other))
            self.assertAlmostEqual(law,q.apse_offset(d/2),places=11)

    def test_sign_changes_and_wrapping_of_highest_longitude(self):
        for d in (0,90,180,270,360):
            self.assertAlmostEqual(q.apse_offset(d),0,places=10)
        self.assertGreater(q.apse_offset(45),10)
        self.assertLess(q.apse_offset(135),-10)
        self.assertAlmostEqual(q.apse_offset(45),-q.apse_offset(135))
        self.assertGreaterEqual(q.calculate(359,.1,73)["highest_true_deg"],0)
        self.assertLess(q.calculate(359,.1,73)["highest_true_deg"],360)
        with self.assertRaises(ValueError):
            q.calculate(0,0,0,6800)

if __name__=="__main__":
    unittest.main()
