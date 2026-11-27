"""Test archive sampling, transcription review alignment, and historical local time."""

from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from rounds.r27.archive_source import positions
from rounds.r27.study import birth_row, transcription
from rounds.r27.verify import check_toy


class AmsterdamRegisterTests(unittest.TestCase):
    def test_fixed_sampling_excludes_terminal_images(self):
        self.assertEqual(positions("4686", 7), [3, 4, 5])
        self.assertEqual(positions("4686", 204), [3, 91, 186])

    def test_reverse_review_matches_physical_position_when_act_number_differs(self):
        with TemporaryDirectory() as base:
            path = Path(base) / "review.txt"
            path.write_text("4686-003 95:ack 90:0110:0900:M\n4687-003\n")
            first = path.with_name("first.txt")
            first.write_text("4686-003 91:0110:0900:M 95:ack\n4687-003\n")
            pages = {"4686-003", "4687-003"}
            reviewed = transcription(path, pages, reverse=True)
            self.assertEqual(set(transcription(first, pages)), set(reviewed))
            self.assertEqual(reviewed, {
                ("4686-003", 1): ("90", (datetime(1901, 1, 10, 9), "M")),
                ("4686-003", 2): ("95", "ack"),
            })

    def test_civil_year_drives_modeled_ages_even_if_utc_is_previous_year(self):
        row = birth_row("fictional-record", "4686-003", datetime(1901, 1, 1), "F")
        self.assertEqual(row["birth_utc"], "1900-12-31T23:40:28Z")
        self.assertEqual(row["calendar_years"], list(range(1921, 1961)))

    def test_design_keeps_empty_scans_and_the_finite_population_correction(self):
        check_toy()
