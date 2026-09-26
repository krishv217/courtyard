import unittest

from courtyard.safety import card_for, custom_card, infer_activity, infer_clock, inspect, line_is_safe, redact_for_model
from courtyard.service import (
    accept_friend,
    ask_agent,
    invite,
    join,
    leave,
    load_story,
    public_state,
    request_friend,
    reset,
    seed_community,
    submit_text,
)


class SafetyTests(unittest.TestCase):
    def test_helen_note_keeps_the_walk_and_drops_the_address(self):
        text = (
            "I'm in 12C and I'll be alone all afternoon. The gate code is 4491. "
            "I'd like company walking to lunch."
        )
        found = inspect(text)
        self.assertIsNone(found.emergency)
        self.assertIn("unit number", found.withheld)
        self.assertIn("being alone", found.withheld)
        self.assertIn("door code", found.withheld)
        redacted = redact_for_model(text)
        self.assertNotIn("12C", redacted)
        self.assertNotIn("4491", redacted)
        self.assertNotIn("alone", redacted.lower())
        self.assertEqual(infer_activity(text), "Walk to lunch")
        card = card_for("Walk to lunch")
        self.assertEqual(card.place, "Lobby")
        self.assertEqual(card.time, "11:30")

    def test_a_fall_never_becomes_a_visit(self):
        found = inspect("I fell and I can't get up.")
        self.assertEqual(found.emergency, "fall")
        self.assertIsNone(infer_activity("I fell and I can't get up."))

    def test_spoken_line_rejects_a_unit_number(self):
        self.assertFalse(line_is_safe("Meet Helen at 12C."))
        self.assertTrue(line_is_safe("Helen and Frank will meet in the Lobby at 11:30."))

    def test_a_grocery_trip_stays_a_grocery_trip(self):
        reset()
        text = "I'm in 12C. Let's carpool to the grocery store at 1pm."
        card = custom_card(text, None)
        self.assertIsNotNone(card)
        self.assertEqual(card.place, "Grocery store")
        self.assertNotIn("12C", card.activity)
        self.assertEqual(card.time, "1:00")
        submit_text("helen", text)
        posted = [
            plan for plan in public_state("helen")["plans"]
            if plan["resident_ids"] == ["helen"]
        ]
        self.assertEqual(posted[0]["place"], "Grocery store")
        self.assertNotIn("12C", json_dump(public_state("frank")))
        self.assertIn("12C", public_state("helen")["notes"][0]["text"])

    def test_a_suggestion_stays_unsent_until_they_choose(self):
        reset()
        payload = ask_agent("helen", "frank", "Where should we go for lunch?")
        self.assertIn("lunch", payload["suggestion"].lower())
        self.assertEqual(public_state("helen")["threads"], [])
        self.assertEqual(public_state("frank")["threads"], [])

    def test_a_clock_time_is_not_a_unit_number(self):
        self.assertIsNone(infer_clock("I'm in 12C and the gate code is 4491"))
        self.assertEqual(infer_clock("I'd like a walk at 1pm"), "1:00")

    def test_story_posts_separate_plans_and_someone_can_join(self):
        reset()
        load_story()
        staff = public_state("staff")
        helen = public_state("helen")
        frank = public_state("frank")
        self.assertEqual(len(staff["alerts"]), 1)
        self.assertIn("Ruth", staff["alerts"][0]["summary"])
        self.assertNotIn("12C", json_dump(staff))
        self.assertNotIn("4491", json_dump(staff))
        helen_walks = [
            plan for plan in helen["plans"]
            if plan["resident_ids"] == ["helen"] and plan["activity"] == "Walk to lunch"
        ]
        frank_plans = [plan for plan in frank["plans"] if plan["resident_ids"][0] == "frank"]
        self.assertEqual(len(helen_walks), 1)
        self.assertEqual(helen_walks[0]["place"], "Lobby")
        self.assertGreaterEqual(len(frank_plans), 2)
        self.assertIn(helen_walks[0]["id"], [plan["id"] for plan in frank["plans"]])
        self.assertNotIn("12C", json_dump(frank))
        self.assertIn("12C", helen["notes"][0]["text"])
        self.assertTrue(all("text" not in note for note in staff["notes"]))
        joined = join(helen_walks[0]["id"], "frank")
        self.assertEqual(set(joined["resident_ids"]), {"helen", "frank"})
        submit_text("helen", "I'd like to play cards at 3pm.")
        helen_hosted = [
            plan for plan in public_state("helen")["plans"]
            if plan["resident_ids"][0] == "helen"
        ]
        self.assertGreaterEqual(len(helen_hosted), 2)
        reset()

    def test_friends_only_is_hidden_until_they_are_friends(self):
        reset()
        submit_text("helen", "I'd like company walking to lunch.", audience="friends")
        helen_plan = public_state("helen")["plans"][0]
        self.assertEqual(public_state("ruth")["plans"], [])
        self.assertEqual(public_state("frank")["plans"], [])
        self.assertEqual(len(public_state("staff")["plans"]), 1)
        with self.assertRaises(ValueError):
            join(helen_plan["id"], "frank")
        request_friend("helen", "frank")
        self.assertEqual(public_state("frank")["incoming"][0]["id"], "helen")
        accept_friend("frank", "helen")
        self.assertEqual(public_state("frank")["friends"][0]["id"], "helen")
        self.assertEqual(len(public_state("frank")["plans"]), 1)
        self.assertEqual(public_state("ruth")["plans"], [])
        joined = join(helen_plan["id"], "frank")
        self.assertEqual(set(joined["resident_ids"]), {"helen", "frank"})
        reset()

    def test_shared_events_become_friend_suggestions(self):
        reset()
        submit_text("helen", "I'd like company walking to lunch.")
        walk = public_state("helen")["plans"][0]
        join(walk["id"], "frank")
        submit_text("helen", "I'd like to play cards at 3pm.")
        cards = next(
            plan for plan in public_state("helen")["plans"]
            if plan["activity"] == "Cards" and plan["resident_ids"][0] == "helen"
        )
        join(cards["id"], "frank")
        submit_text("helen", "I'd like company in the garden.", audience="everyone")
        frank = public_state("frank")
        self.assertEqual(frank["suggestions"], [{"id": "helen", "shared": 2}])
        self.assertEqual(public_state("ruth")["suggestions"], [])
        request_friend("frank", "helen")
        self.assertEqual(public_state("frank")["suggestions"], [])
        reset()

    def test_seeded_board_is_full_and_suggests_from_shared_events(self):
        reset()
        seed_community()
        helen = public_state("helen")
        self.assertGreaterEqual(len(helen["plans"]), 10)
        shared = {item["id"]: item["shared"] for item in helen["suggestions"]}
        self.assertEqual(shared["ruth"], 3)
        self.assertEqual(shared["samir"], 2)
        self.assertEqual({item["id"] for item in helen["friends"]}, {"frank", "mae", "walter"})
        self.assertEqual(helen["incoming"][0]["id"], "doris")
        self.assertEqual(helen["outgoing"][0]["id"], "leo")
        self.assertTrue(all(plan["resident_ids"][0] != "leo" or plan["audience"] != "friends" for plan in helen["plans"]))
        self.assertNotIn("12C", json_dump(public_state("frank")))
        self.assertEqual(len(public_state("staff")["alerts"]), 1)
        self.assertEqual(helen["notifications"][0]["kind"], "cancel")
        self.assertTrue(any(item["kind"] == "invite" for item in helen["notifications"]))
        reset()

    def test_invite_and_cancel_show_up_for_the_other_person(self):
        reset()
        submit_text("helen", "I'd like company walking to lunch.", audience="friends")
        plan = public_state("helen")["plans"][0]
        request_friend("helen", "frank")
        accept_friend("frank", "helen")
        request_friend("frank", "walter")
        accept_friend("walter", "frank")
        self.assertEqual(public_state("walter")["plans"], [])
        join(plan["id"], "frank")
        invite(plan["id"], "frank", "walter")
        walter = public_state("walter")
        self.assertEqual(walter["plans"][0]["id"], plan["id"])
        self.assertEqual(walter["notifications"][0]["kind"], "invite")
        self.assertIn("Frank invited you", walter["notifications"][0]["text"])
        helen = public_state("helen")
        self.assertEqual(helen["notifications"][0]["kind"], "join")
        leave(plan["id"], "frank")
        helen = public_state("helen")
        self.assertEqual(helen["plans"][0]["resident_ids"], ["helen"])
        self.assertEqual(helen["notifications"][0]["kind"], "leave")
        self.assertIn(plan["id"], [item["id"] for item in public_state("walter")["plans"]])
        leave(plan["id"], "helen")
        self.assertEqual(public_state("walter")["plans"], [])
        self.assertEqual(public_state("walter")["notifications"][0]["kind"], "cancel")
        self.assertNotIn("12C", public_state("walter")["notifications"][0]["text"])
        reset()


def json_dump(payload: dict) -> str:
    import json
    return json.dumps(payload)


if __name__ == "__main__":
    unittest.main()
