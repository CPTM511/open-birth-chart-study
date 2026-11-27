from itertools import product
import unittest

from degrees import BRANCHES, DURATIONS, F, GRID, MANSIONS
from degrees import ShoushiScale, age_for_column, column_for, grid_transfer, grid_value, ming_palace, period_trace


class HistoricalDegreesTest(unittest.TestCase):
    def test_all_grid_cells_and_palace_hour_permutations(self):
        result = [(p,*cell) for p in BRANCHES for cell in GRID[p]]
        self.assertEqual(len(result),360)
        self.assertEqual(len(set(result)),360)
        self.assertEqual({m for _,m,_ in result},set(MANSIONS))
        for palace in BRANCHES:
            self.assertEqual(len(GRID[palace]),30)
            self.assertEqual({age_for_column(i) for i in range(1,31)},set(range(11,21)))
            rotated = BRANCHES[BRANCHES.index(palace):]+BRANCHES[:BRANCHES.index(palace)]
            observed = set()
            for hour in BRANCHES:
                reset = BRANCHES[BRANCHES.index(hour):]+BRANCHES[:BRANCHES.index(hour)]
                expected = next(p for p,b in zip(rotated,reset,strict=True) if b=="卯")
                self.assertEqual(ming_palace(palace,hour),expected)
                observed.add(expected)
                for col,(mansion,degree) in enumerate(GRID[palace],start=1):
                    out = grid_transfer(palace,mansion,degree,hour)
                    self.assertEqual(out["solar_column"],col)
                    self.assertEqual(out["ming_palace"],expected)
                    self.assertEqual((out["ming_mansion"],out["ming_whole_degree"]),GRID[expected][col-1])
            self.assertEqual(observed,set(BRANCHES))

    def test_primary_source_disagreements_stay_visible(self):
        self.assertEqual(grid_transfer("子","虚",6,"酉")["ming_whole_degree"],6)
        self.assertEqual(grid_transfer("子","女",3,"酉")["ming_whole_degree"],5)
        self.assertEqual(age_for_column(column_for("午","星",5)),15)
        self.assertEqual(age_for_column(column_for("午","张",11)),19)
        self.assertEqual(age_for_column(column_for("午","张",12)),20)
        self.assertIsNone(grid_transfer("卯","虚",6,"酉"))

    def test_shoushi_both_sources_closed_and_wrapped(self):
        for reading in ("wikisource_san","shidian_er"):
            scale = ShoushiScale(reading)
            self.assertEqual(scale.cycle,F("365.2575"))
            self.assertEqual(sum(scale.palace_width(p) for p in BRANCHES),scale.cycle)
            self.assertEqual(scale.project_bin("申","觜",0,"申","head")["source_arc_units"],"1/20")
            partial = scale.project_bin("子","女",2,"子","head")
            self.assertEqual(partial["target_offset_interval_arc_units"][0],"0")
            self.assertLess(F(partial["source_in_solar_palace_arc_units"]),1)
            self.assertEqual(scale.project_bin("巳","张",16,"丑","tail")["status"],
                             "projected_bin_outside_ming_palace")
        one = ShoushiScale("wikisource_san")
        two = ShoushiScale("shidian_er")
        self.assertEqual(two.palace_width("丑")-one.palace_width("丑"),1)

    def test_major_period_boundaries_and_literal_progress(self):
        for palace,col in product(BRANCHES,(1,15,16,30)):
            previous = period_trace(palace,col,0)
            self.assertEqual(previous["possible_columns"],[col])
            self.assertEqual(previous["period"],"命")
            start = F(previous["end_elapsed_year_exclusive"])
            for i,(name,years) in enumerate(DURATIONS.items(),start=1):
                hit = period_trace(palace,col,start)
                self.assertEqual(hit["period"],name)
                self.assertEqual(hit["column"],1)
                self.assertEqual(hit["palace"],BRANCHES[(BRANCHES.index(palace)+i)%12])
                self.assertEqual(tuple(hit["mansion_degree"]),grid_value(hit["palace"],1))
                late = period_trace(palace,col,start+years-F(1,1000))
                self.assertEqual(late["column"],30)
                self.assertLessEqual(F(late["printed_rate_distance_from_tail"]),
                                     F(late["normalized_distance_from_tail"]))
                start += years
            self.assertEqual(period_trace(palace,col,start)["status"],"outside_this_cycle")

    def test_incomplete_and_invalid_coordinates(self):
        self.assertEqual(period_trace("子",None,40)["status"],"missing_ming_degree")
        with self.assertRaises(ValueError):
            period_trace("子",30,-1)
        with self.assertRaises(ValueError):
            grid_transfer("子","女",True,"卯")
        with self.assertRaises(ValueError):
            age_for_column(31)
        with self.assertRaises(ValueError):
            ShoushiScale("wikisource_san").project_bin("子","女",12,"午","head")


if __name__ == "__main__":
    unittest.main()
