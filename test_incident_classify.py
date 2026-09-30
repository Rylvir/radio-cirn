"""Severity-bar checks for incident classification. No audio, no network."""

import tempfile
import unittest
from pathlib import Path

import incident_classify as ic


class ClassifyTests(unittest.TestCase):
    def test_structure_smoke_showing(self):
        hit = ic.classify("structure fire, smoke showing, 400 elm street")
        self.assertEqual(hit["category"], "structure_fire")

    def test_working_fire_defensive(self):
        hit = ic.classify("working fire, going defensive on the commercial structure")
        self.assertEqual(hit["category"], "structure_fire")

    def test_second_alarm(self):
        hit = ic.classify("make this a second alarm, house fire")
        self.assertEqual(hit["category"], "structure_fire")

    def test_smoke_investigation_is_not_an_alert(self):
        self.assertIsNone(ic.classify("smoke investigation, nothing showing, code 4"))

    def test_negated_smoke_showing(self):
        self.assertIsNone(ic.classify("structure fire reported, no smoke showing"))

    def test_vehicle_fire(self):
        hit = ic.classify("vehicle fire, smoke showing, highway 80")
        self.assertEqual(hit["category"], "other_fire")

    def test_vehicle_fires_from_2026_09_29(self):
        for text in (
            "Reported as a fully involved passenger vehicle and reported "
            "extinguisher used at scene and now no flames but heavy smoke 1335.",
            "Fully involved engine compartment. Actually looks like fire's "
            "knocked down now. Negative extension to the wild end.",
            "I can hear a fire showing 97. Vehicle looks 99% extinguished.",
        ):
            with self.subTest(text=text):
                self.assertEqual(ic.classify(text)["category"], "other_fire")

    def test_fire_with_no_object_is_other_not_structure(self):
        hit = ic.classify("we'll fire with threat to vegetation, report of fully involved.")
        self.assertEqual(hit["category"], "other_fire")

    def test_structure_words(self):
        for text in (
            "Workout fire structure fully involved. Power line still down.",
            "working fire, single story residence",
            "garage fully involved, smoke showing",
            "vehicle fire extending into the garage, fully involved",
        ):
            with self.subTest(text=text):
                self.assertEqual(ic.classify(text)["category"], "structure_fire")

    def test_structure_protection_is_not_a_structure_fire(self):
        hit = ic.classify("vehicle fire fully involved, structure protection on the hill")
        self.assertEqual(hit["category"], "other_fire")

    def test_dumpster_without_severity(self):
        self.assertIsNone(ic.classify("dumpster fire, nothing showing"))

    def test_small_grass_fire(self):
        self.assertIsNone(ic.classify("small grass fire behind the station"))

    def test_major_brush(self):
        hit = ic.classify("major brush fire, multiple acres, newcastle road")
        self.assertEqual(hit["category"], "brush_grass_fire")

    def test_rollover_extrication(self):
        hit = ic.classify("TC with rollover, extrication required")
        self.assertEqual(hit["category"], "motor_vehicle_accident")

    def test_minor_tc(self):
        self.assertIsNone(ic.classify("traffic collision, minor, code 4"))

    def test_multiple_vehicles_needs_a_crash(self):
        self.assertIsNone(ic.classify("multiple vehicles on scene at the house fire"))

    def test_shots_fired(self):
        hit = ic.classify("shots fired, 200 block of main street")
        self.assertEqual(hit["category"], "shooting")

    def test_a_shooting(self):
        hit = ic.classify("we have a shooting at the 200 block of main street")
        self.assertEqual(hit["category"], "shooting")

    def test_shooting_the_compass_is_not_a_shooting(self):
        self.assertIsNone(ic.classify(
            "Start shooting the compasser. The FBI numbers for your subject are different."))

    def test_negated_shots(self):
        self.assertIsNone(ic.classify("no shots fired, just fireworks"))

    def test_shooting_pain_is_medical(self):
        self.assertIsNone(ic.classify("patient has shooting pain in the left arm"))

    def test_firefighter_down_wins(self):
        hit = ic.classify("mayday mayday firefighter down, structure fire")
        self.assertEqual(hit["category"], "firefighter_down")

    def test_mayday_dealership_is_not_a_mayday(self):
        self.assertIsNone(ic.classify(
            "It's supposed to be at a Mayday dealership getting a tire"))

    def test_building_collapse(self):
        hit = ic.classify("building collapse, commercial structure on oak avenue")
        self.assertEqual(hit["category"], "building_collapse")

    def test_mci(self):
        hit = ic.classify("this is an MCI, multiple patients")
        self.assertEqual(hit["category"], "mass_casualty")

    def test_airport(self):
        hit = ic.classify("airport alert, aircraft emergency on the runway")
        self.assertEqual(hit["category"], "airport_alert")

    def test_alert_3_without_airport_is_not_airport(self):
        hit = ic.classify("third alarm structure fire, smoke showing")
        self.assertEqual(hit["category"], "structure_fire")

    def test_technical_rescue(self):
        hit = ic.classify("confined space rescue, worker trapped in the tank")
        self.assertEqual(hit["category"], "technical_rescue")

    def test_routine_dispatch_chatter(self):
        self.assertIsNone(ic.classify("copy, show me 10-8, returning to quarters"))

    def test_foresthill_on_a_routine_call_is_quiet(self):
        for text in (
            "medical aid, 200 Main Street, Foresthill",
            "engine 84 is responding forest hill",
            "MR 142 responding to Jordan Lane from Forest Hill on I-80. Copy staging.",
            "AMR responding from Foresthill and I-80",
            "party separated at the 4th Hill Fire Station",
            "Engine 16 code 3, Foresthill Road",
        ):
            with self.subTest(text=text):
                self.assertIsNone(ic.classify(text))

    def test_foresthill_with_a_real_event_alerts(self):
        for text, evidence in (
            ("AMR responding code 3 for vehicle accident, Foresthill Rd and "
             "Mosquito Ridge", "vehicle accident"),
            ("traffic collision, Foresthill Road at Bowman", "traffic collision"),
            ("small vegetation fire, Foresthill", "vegetation fire"),
            ("Foresthill, male not breathing, CPR in progress", "not breathing"),
            ("male stabbed, Michigan Bluff and Forrest Hill Road", "stabbed"),
            ("landing zone at Foresthill High School for Care Flight", "landing zone"),
        ):
            with self.subTest(text=text):
                hit = ic.classify(text)
                self.assertEqual(hit["category"], "foresthill")
                self.assertEqual(hit["evidence"], f"foresthill + {evidence}")

    def test_foresthill_unit_names_and_training_are_quiet(self):
        for text in (
            "Forest Hill IC, Grass Valley. Rescue 71 is making their way out to the pavement.",
            "Forest Hill IC. Rescue support 71's release will be coming up available shortly.",
            "East Coast 97, Forest Hill, Sunset LZ, training with Forest Hill Fireplace.",
        ):
            with self.subTest(text=text):
                self.assertIsNone(ic.classify(text))
        hit = ic.classify("water rescue, Forest Hill, subject in the river")
        self.assertEqual(hit["evidence"], "foresthill + rescue")

    def test_foresthill_negated_event_is_quiet(self):
        self.assertIsNone(ic.classify("Foresthill Road, no smoke showing, no fire"))
        self.assertIsNone(ic.classify("cancel the vehicle accident, Foresthill"))

    def test_foresthill_tow_company_is_not_the_town(self):
        for text in (
            "10-39 Forest Hill Toll, they're en route, ETA about 20 minutes. vehicle accident",
            "Foresthill Tow is en route for the collision",
            "Forest Hilltow, ETA, 15 minutes. traffic collision",
        ):
            with self.subTest(text=text):
                self.assertIsNone(ic.classify(text))

    def test_foresthill_structure_fire_stays_a_structure_fire(self):
        hit = ic.classify("structure fire, smoke showing, Foresthill Road")
        self.assertEqual(hit["category"], "structure_fire")

    def test_not_foresthill_is_not_an_alert(self):
        self.assertIsNone(ic.classify("not Foresthill, this is Auburn"))

    def test_foresthill_as_transcribed(self):
        # Real renderings from radio_calls.db.
        for text in (
            "Henry, we're here at Michigan Bluffs and Forrest Hill Road.",
            "your subject out of Forest Hills, valid and clear",
            "four people on the catwalk under the bridge on the forest hillside",
            "80 West at 4th Hill, okay.",
            "party separated at the 4th Hill Fire Station",
            "16360 Poster Hills Road, second hand info to the RP",
            "Possible medical. Posterhills and sugar pine.",
            "126 Foster Hills Road, Iron Horse Road.",
            "Foresthill-Road at Bowman",
            "FORESTHILL",
        ):
            with self.subTest(text=text):
                self.assertTrue(ic.foresthill_mentioned(ic.normalize(text)))

    def test_not_foresthill_lookalikes(self):
        for text in (
            "white Subaru Forester, four door",
            "Lake Forest and Meadowbrook",
            "Placer Hills Road in Meadow Vista",
            "Tahoe Forest Hospital",
            "Forest Service unit to Placer",
        ):
            with self.subTest(text=text):
                self.assertIsNone(ic.classify(text))

    def test_foresthill_survives_an_earlier_negation(self):
        hit = ic.classify("negative injuries reported, vehicle accident, Foresthill Road")
        self.assertEqual(hit["category"], "foresthill")

    def test_foresthill_grass_fire_with_smoke_showing(self):
        # Brush + severity without "major" used to return None outright.
        hit = ic.classify("grass fire, smoke showing, Foresthill Road")
        self.assertEqual(hit["category"], "foresthill")

    def test_foresthill_major_incident_is_tagged(self):
        hit = ic.classify("structure fire, smoke showing, Foresthill Road")
        self.assertEqual(hit.get("place"), "foresthill")
        self.assertIsNone(ic.classify("structure fire, smoke showing").get("place"))

    def test_partial_hotword_echo_is_not_foresthill(self):
        text = "Beep. Beep. auburn lincoln roseville placer nevada el dorado miller sacramento foresthill"
        self.assertIsNone(ic.classify(text))
        self.assertEqual(ic.strip_prompt_echo(text), "Beep. Beep.")

    def test_foresthill_is_not_a_decoder_hint(self):
        # A hint word gets echoed onto garbled audio: "Grass up, lincoln
        # forest hill" on Nevada, 2026-09-28. Alerting words stay out.
        import watch_transcribe
        self.assertNotIn("forest", watch_transcribe.HOTWORDS)

    def test_foresthill_at_the_end_of_a_real_call_is_kept(self):
        hit = ic.classify("Engine 16, respond traffic collision, Auburn, Foresthill")
        self.assertEqual(hit["category"], "foresthill")

    def test_major_vehicle_accident(self):
        hit = ic.classify("respond to a major vehicle accident, 49 and Dry Creek")
        self.assertEqual(hit["category"], "motor_vehicle_accident")

    def test_high_level_accident(self):
        for text in ("High level TC, Highway 49 at Dry Creek",
                     "high level response for a vehicle accident on 80 west"):
            with self.subTest(text=text):
                self.assertEqual(ic.classify(text)["category"],
                                 "motor_vehicle_accident")

    def test_high_level_alone_is_not_an_mva(self):
        self.assertIsNone(ic.classify("Pretty high level 10-codes, go ahead."))

    def test_plain_vehicle_accident_is_still_routine(self):
        self.assertIsNone(ic.classify("vehicle accident, Barton Road, non-injury"))

    def test_location_tokens(self):
        self.assertEqual(ic.location_tokens("Highway 49 at Dry Creek Road"),
                         {"hwy 49", "dry creek"})
        self.assertEqual(ic.location_tokens("eastbound 80 at Bell Rd"),
                         {"hwy 80", "bell"})
        self.assertEqual(ic.location_tokens("I 10-4, copy"), set())

    def test_hotword_echo_does_not_create_an_mva(self):
        text = (
            "Standby. Paul 4219. He's detained. His probation on his DL "
            "does not indicate search terms. Lincoln Miller Roseville "
            "smoke showing working fire extrication"
        )
        self.assertIsNone(ic.classify(text))


class MergeTests(unittest.TestCase):
    def _alert(self, **over):
        base = {
            "id": "a",
            "category": "structure_fire",
            "label": "Structure Fire",
            "detail": "x",
            "evidence": "smoke showing",
            "text": "structure fire smoke showing 400 elm street",
            "talkgroup": 2,
            "talkgroup_name": "Placer",
            "system": "fire",
            "started": "2026-09-27T12:00:00",
            "updated": "2026-09-27T12:00:00",
            "rel": "fire/a.wav",
            "calls": 1,
            "location": "400 elm street",
        }
        base.update(over)
        return base

    def test_same_talkgroup_updates_one_alert(self):
        first = self._alert()
        nxt = self._alert(id="b", updated="2026-09-27T12:10:00",
                          text="going defensive 400 elm street", calls=1)
        out = ic.merge_alert([first], nxt)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["calls"], 2)
        self.assertIn("defensive", out[0]["text"])
        self.assertEqual(out[0]["started"], "2026-09-27T12:00:00")

    def test_foresthill_calls_on_the_same_channel_stay_separate(self):
        first = self._alert(category="foresthill", label="Foresthill",
                            text="medical foresthill", location=None)
        nxt = self._alert(id="b", category="foresthill", label="Foresthill",
                          updated="2026-09-27T12:10:00",
                          text="traffic stop foresthill", location=None)
        self.assertEqual(len(ic.merge_alert([first], nxt)), 2)

    def test_different_address_stays_separate(self):
        first = self._alert()
        nxt = self._alert(id="b", updated="2026-09-27T12:10:00",
                          text="smoke showing 900 oak avenue",
                          location="900 oak avenue")
        out = ic.merge_alert([first], nxt)
        self.assertEqual(len(out), 2)

    def test_same_address_across_talkgroups(self):
        first = self._alert()
        nxt = self._alert(id="b", talkgroup=2001, talkgroup_name="PCSO West",
                          system="cirn", updated="2026-09-27T12:20:00")
        out = ic.merge_alert([first], nxt)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["talkgroup_name"], "PCSO West")

    def _mva(self, **over):
        base = self._alert(category="motor_vehicle_accident", label="MVA",
                           location=None, talkgroup=151325,
                           talkgroup_name="NEU West", system="fire",
                           text="High level TC, Highway 49 at Dry Creek")
        base.update(over)
        return base

    def _pcso(self, **over):
        base = dict(id="b", talkgroup=2001, talkgroup_name="PCSO West",
                    system="cirn", updated="2026-09-27T12:06:00",
                    text="major vehicle accident, 49 and Dry Creek")
        base.update(over)
        return self._mva(**base)

    def test_fire_and_law_same_crash_merge(self):
        out = ic.merge_alert([self._mva()], self._pcso())
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["calls"], 2)
        self.assertEqual(out[0]["channels"], ["NEU West", "PCSO West"])
        self.assertEqual(out[0]["talkgroups"], [151325, 2001])

    def test_cross_channel_merge_when_one_side_has_no_place(self):
        out = ic.merge_alert([self._mva()],
                             self._pcso(text="major vehicle accident, units responding"))
        self.assertEqual(len(out), 1)

    def test_cross_channel_different_roads_stay_separate(self):
        out = ic.merge_alert([self._mva()],
                             self._pcso(text="major vehicle accident, 80 west at Bell Road"))
        self.assertEqual(len(out), 2)

    def test_cross_channel_too_late_stays_separate(self):
        out = ic.merge_alert([self._mva()],
                             self._pcso(updated="2026-09-27T12:40:00"))
        self.assertEqual(len(out), 2)

    def test_record_alert_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "incident_alerts.json"
            hit = ic.classify("shots fired at 200 main street")
            ic.record_alert(
                hit, talkgroup=2001, talkgroup_name="PCSO West", system="cirn",
                when_iso="2026-09-27T18:00:00", rel="cirn/x.wav",
                text="shots fired at 200 main street", alerts_path=path,
            )
            ic.record_alert(
                hit, talkgroup=2001, talkgroup_name="PCSO West", system="cirn",
                when_iso="2026-09-27T18:05:00", rel="cirn/y.wav",
                text="still shots fired at 200 main street", alerts_path=path,
            )
            data = __import__("json").loads(path.read_text())
            self.assertEqual(len(data["alerts"]), 1)
            self.assertEqual(data["alerts"][0]["calls"], 2)
            log = data["alerts"][0]["log"]
            self.assertEqual([e["rel"] for e in log], ["cirn/x.wav", "cirn/y.wav"])
            self.assertEqual(log[1]["time"], "2026-09-27T18:05:00")
            self.assertEqual(data["alerts"][0]["talkgroups"], [2001])
            self.assertEqual(len(data["categories"]), 11)


BLUE = [  # NEU West, 2026-09-28, as transcribed
    ("17:03:13", "DRL tanker 8-8 tanker 8-9 copter 5-1-4 copter 5 bravo tango mountain "
     "group engine 23-73 engine 23-83 engine 23-63 engine 23-53 transport dozer 23-40 "
     "transport dozer 23-49 water tender 198 washington ridge crew 3 port of a passenger "
     "vehicle fire possibly fully involved latin long in the cat page be off blue canyon "
     "road near the railroad tracks stand by for check 17-03"),
    ("17:05:54", "A checkback is responding. Passenger vehicle fire reported fully involved "
     "on a dirt road and near the railroad tracks. First seen is seen will be blue IC on "
     "CDF TAC-5. Confirm response. Resources from the mountain group."),
    ("17:12:31", "Station 10, one engine to 30. Station 20, one engine to 33."),
    ("17:16:16", "Engine 2383, grass fight."),
    ("17:19:14", "2373 grass valley, the unnamed road that you're on is the access road "
     "that I'm showing. You're on a good track."),
    ("17:22:55", "Working my way in with the alpha engine. We'll stay in the balance with "
     "the blue canyons next to us."),
    ("17:23:14", "Vehicle fire, threat to vegetation, blue canyon area, stage at eastbound "
     "80 and blue canyon 17, 23. Grassoll air attack 230. Air attack 230, Grassoll. The "
     "blue incident, fire does not appear to be spread into the vegetation, we do have a "
     "box retardant around it, and working with the ground crews to get them in, assuming "
     "blue air attack."),
    ("17:23:58", "Yeah, five bravo tango's been released from the blue incident, we're "
     "returning to Auburn, we've got ETA of 1732."),
    ("17:29:11", "Grass Valley Unit is responding. Now commercial vehicle fire. Engine 2363 "
     "to continue balance to cancel. Engine 2353 cover station 33."),
]


class FollowTests(unittest.TestCase):
    def _run(self, calls):
        d = tempfile.mkdtemp()
        path = Path(d) / "a.json"
        out = []
        for hhmm, text in calls:
            when = f"2026-09-28T{hhmm}"
            hit = ic.classify(text)
            if hit:
                rec = ic.record_alert(hit, talkgroup=151325, talkgroup_name="NEU West",
                                      system="fire", when_iso=when, rel=f"{hhmm}.wav",
                                      text=text, alerts_path=path)
                out.append((hhmm, "alert", rec.get("first_confirmation", False)))
            else:
                a, first = ic.follow_up(talkgroup=151325, talkgroup_name="NEU West",
                                        system="fire", when_iso=when, rel=f"{hhmm}.wav",
                                        text=text, alerts_path=path)
                out.append((hhmm, "follow" if a else "routine", first))
        return __import__("json").loads(path.read_text())["alerts"], out

    def test_blue_incident_is_followed_and_confirmed_by_air_attack(self):
        alerts, out = self._run(BLUE)
        self.assertEqual(len(alerts), 1)
        a = alerts[0]
        self.assertIn("2373", a["units"])
        self.assertIn("2340", a["units"])
        self.assertEqual(a["incident"], ["blue"])
        # Dispatch stays the alert text source; the air attack report confirms.
        self.assertTrue(a["log"][0]["text"].startswith("DRL tanker"))
        self.assertIn("air attack 230", a["confirmation"]["text"].lower())
        kinds = dict((h, k) for h, k, _f in out)
        self.assertEqual(kinds["17:12:31"], "routine")   # station move-ups
        self.assertEqual(kinds["17:22:55"], "routine")   # "blue canyons", not the incident
        for h in ("17:16:16", "17:19:14", "17:23:14", "17:23:58", "17:29:11"):
            self.assertEqual(kinds[h], "follow", h)
        self.assertEqual([h for h, _k, f in out if f], ["17:23:14"])

    def test_confirmation_wording(self):
        for text in ("Engine 2373 arrived", "Battalion 2312, report on conditions: "
                     "one acre, slow rate", "as described, one vehicle fully involved",
                     "Battalion 3412 can handle with units at scene", "Medic 142 is 97"):
            with self.subTest(text=text):
                self.assertTrue(ic.confirmation(text))

    def test_not_confirmations(self):
        for text in ("First unit at scene, Highway IC on XPL, TAC 9.",
                     "Engine 2373 on scene", "notify when arrived",
                     "tanker 8-8 tanker 8-9 copter 5-1-4 respond"):
            with self.subTest(text=text):
                self.assertIsNone(ic.confirmation(text))

    def test_hyphenated_ids(self):
        self.assertEqual(ic.unit_ids("copter 5-1-4, engine 23-73"), {"514", "2373"})

    def test_law_traffic_does_not_follow_a_fire_incident(self):
        d = tempfile.mkdtemp(); path = Path(d) / "a.json"
        t = "Battalion 129, engine 2351, aircraft down, Auburn airport"
        ic.record_alert(ic.classify(t), talkgroup=151325, talkgroup_name="NEU West",
                        system="fire", when_iso="2026-09-29T10:26:00", rel="",
                        text=t, alerts_path=path)
        a, _f = ic.follow_up(talkgroup=2001, talkgroup_name="PCSO West", system="cirn",
                             when_iso="2026-09-29T10:40:00", rel="",
                             text="Placer Alpha 129 in the mail", alerts_path=path)
        self.assertIsNone(a)

    def test_unrelated_traffic_after_an_hour_is_not_followed(self):
        alerts, out = self._run([BLUE[0], ("18:40:00", "Engine 2383 available")])
        self.assertEqual(out[-1][1], "routine")


if __name__ == "__main__":
    unittest.main()
