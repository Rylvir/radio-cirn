"""Spoken numbers to digits, from real transcripts. No audio."""

import unittest

from radio_numbers import spoken_numbers_to_digits as fix


class RadioNumberTests(unittest.TestCase):
    def test_real_transcripts(self):
        for said, want in (
            ("Engine twenty-three sixty-three", "Engine 2363"),
            ("Engine twenty-three sixty-two seventeen fifteen.", "Engine 2362 1715."),
            ("Blue air attack seventeen twenty-three.", "Blue air attack 1723."),
            ("Medic fifty-three", "Medic 53"),
            ("engine forty-three, Grass Valley", "engine 43, Grass Valley"),
            ("Medic two en route zone one.", "Medic 2 en route zone one."),
            ("Copter five bravo tango", "Copter 5 bravo tango"),
            ("Bridge crew three zero nine zero four", "Bridge crew 30904"),
            ("tanker eight eight, tanker eight nine", "tanker 88, tanker 89"),
            ("thirteen thirty two", "1332"),
            ("nineteen thirty", "1930"),
            ("timeout fifteen hundred", "timeout 1500"),
            ("Copy, ten-four.", "Copy, 10-4."),
            ("Medic one, twenty nineteen.", "Medic 1, 2019."),
            ("Medic five, nineteen zero three.", "Medic 5, 1903."),
            ("Metro fire engine twenty six, twenty four two.", "Metro fire engine 26, 24 2."),
            ("Engine twenty-three sixty-three sixteen nineteen", "Engine 2363 1619"),
            ("Best values in twenty three and two.", "Best values in 23 and two."),
        ):
            with self.subTest(said=said):
                self.assertEqual(fix(said), want)

    def test_lone_words_stay_words(self):
        for text in ("Station 10, one engine to 30.", "no one on scene",
                     "one of them is down", "two vehicles involved",
                     "Oh, okay, copy.", "Engine 2373 arrived"):
            with self.subTest(text=text):
                self.assertEqual(fix(text), text)


if __name__ == "__main__":
    unittest.main()
