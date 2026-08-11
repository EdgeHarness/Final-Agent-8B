"""Tests for the harness backend.

Stdlib unittest, no pytest, no fixtures: `python -m tests.test_harness` from
standalone/. The harness has process-global state (the TOOLS registry, the
fs_tools root, the agent profile), so tests that touch it put it back.

    cd standalone && ../.venv/bin/python -m tests.test_harness
"""
import datetime
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import agent, fs_tools, office, profiles  # noqa: E402
from harness.memory import MemoryStore  # noqa: E402
from harness.tools import TOOLS, execute, validate_call  # noqa: E402
from harness.world import ToolError, World  # noqa: E402


# ------------------------------------------------------------------ parsing ---

class TestParsing(unittest.TestCase):
    def test_strict_takes_clean_json_and_fenced_json(self):
        self.assertEqual(agent.parse_strict('{"tool": "think"}')[0], {"tool": "think"})
        self.assertEqual(agent.parse_strict('```json\n{"tool": "think"}\n```')[0],
                         {"tool": "think"})

    def test_strict_rejects_prose_around_json(self):
        obj, err = agent.parse_strict('Sure! {"tool": "think"}')
        self.assertIsNone(obj)
        self.assertTrue(err)

    def test_lenient_recovers_the_cases_strict_rejects(self):
        for text in ('Sure! {"tool": "think", "args": {}} hope that helps',
                     '{"tool": "think", "args": {},}',
                     'text\n{"tool": "think"}\nmore text'):
            obj, err = agent.parse_lenient(text)
            self.assertIsNotNone(obj, text)
            self.assertEqual(obj.get("tool"), "think", text)

    def test_lenient_reports_rather_than_guesses(self):
        self.assertIsNone(agent.parse_lenient("no json at all")[0])
        self.assertIsNone(agent.parse_lenient('{"a": ')[0])


# ------------------------------------------------------- date/time normalizing --

class TestNormalize(unittest.TestCase):
    MON = datetime.date(2026, 7, 20)  # a Monday

    def test_dates(self):
        n = lambda v: agent.normalize_date(v, self.MON)  # noqa: E731
        self.assertEqual(n("2026-07-22"), "2026-07-22")
        self.assertEqual(n("today"), "2026-07-20")
        self.assertEqual(n("tomorrow"), "2026-07-21")
        self.assertEqual(n("thursday"), "2026-07-23")
        self.assertEqual(n("next monday"), "2026-07-27")  # never "today"
        self.assertEqual(n("July 23"), "2026-07-23")
        self.assertEqual(n("7/23"), "2026-07-23")

    def test_unparseable_dates_pass_through_for_the_world_to_reject(self):
        self.assertEqual(agent.normalize_date("whenever", self.MON), "whenever")
        self.assertEqual(agent.normalize_date(7, self.MON), 7)

    def test_times(self):
        self.assertEqual(agent.normalize_time("2pm"), "14:00")
        self.assertEqual(agent.normalize_time("2:30 pm"), "14:30")
        self.assertEqual(agent.normalize_time("12am"), "00:00")
        self.assertEqual(agent.normalize_time("12pm"), "12:00")
        self.assertEqual(agent.normalize_time("09:15"), "09:15")
        self.assertEqual(agent.normalize_time("25:00"), "25:00")  # invalid, left alone


# ------------------------------------------------------------- weekday check ---

class TestTaskDateCheck(unittest.TestCase):
    """Began as a weekday-only check and was generalized: the failure - the
    model resolves a task's date expression itself and gets it wrong, and every
    tool answers honestly for the wrong day - is identical for "wednesday",
    "tomorrow", "July 23" and "7/23"."""

    MON = datetime.date(2026, 7, 20)

    def check(self, task, args):
        return agent.task_date_mismatch(task, args, self.MON)

    # -- extraction --------------------------------------------------------
    def test_the_expressions_the_normalizer_understands_are_all_found(self):
        # "next tuesday" from a Monday is tomorrow under the normalizer's rule
        # (delta % 7, with "or 7" only when that lands on today). The check MUST
        # agree with the normalizer, whatever the rule is - agreeing is the point.
        self.assertEqual(agent.task_dates("meet next tuesday", self.MON), {"2026-07-21"})
        self.assertEqual(agent.task_dates("do it tomorrow", self.MON), {"2026-07-21"})
        self.assertEqual(agent.task_dates("due July 23", self.MON), {"2026-07-23"})
        self.assertEqual(agent.task_dates("due 7/23", self.MON), {"2026-07-23"})
        self.assertEqual(agent.task_dates("on 2026-07-24 exactly", self.MON), {"2026-07-24"})

    def test_a_bare_month_or_plain_number_is_not_a_date(self):
        self.assertEqual(agent.task_dates("build my July receipts sheet", self.MON), set())
        self.assertEqual(agent.task_dates("the Q3 numbers, all 3 regions", self.MON), set())

    # -- the check ---------------------------------------------------------
    def test_a_wrong_weekday_is_caught_and_corrected(self):
        msg = self.check("Summarize my Wednesday meetings", {"date": "2026-07-27"})
        self.assertIsNotNone(msg)
        self.assertIn("2026-07-22", msg)  # what Wednesday actually is
        self.assertIn("Monday", msg)      # what it sent

    def test_a_wrong_tomorrow_is_caught(self):
        msg = self.check("Book dentist for tomorrow", {"date": "2026-07-20"})
        self.assertIsNotNone(msg)
        self.assertIn("2026-07-21", msg)

    def test_a_wrong_month_day_is_caught(self):
        msg = self.check("Set a reminder for July 23", {"date": "2026-07-24"})
        self.assertIsNotNone(msg)
        self.assertIn("2026-07-23", msg)

    def test_the_right_date_passes_in_every_form(self):
        self.assertIsNone(self.check("Summarize my Wednesday meetings",
                                     {"date": "2026-07-22"}))
        self.assertIsNone(self.check("Book dentist for tomorrow", {"date": "2026-07-21"}))
        self.assertIsNone(self.check("reminder for 7/23", {"date": "2026-07-23"}))

    def test_plurals_count_as_naming_the_day(self):
        self.assertIsNotNone(self.check("never book me on Fridays", {"date": "2026-07-22"}))

    def test_two_dates_in_one_task_are_left_alone(self):
        """"Move my Wednesday meeting to Friday" legitimately carries either."""
        self.assertIsNone(self.check("Move my Wednesday meeting to Friday",
                                     {"date": "2026-07-24"}))
        self.assertIsNone(self.check("move the July 23 review to tomorrow",
                                     {"date": "2026-07-21"}))

    def test_the_same_date_named_two_ways_still_counts_as_one(self):
        """"tomorrow, the 21st..." resolves to one date, so the check stays armed."""
        msg = self.check("book it tomorrow, 7/21", {"date": "2026-07-24"})
        self.assertIsNotNone(msg)

    def test_a_task_naming_no_date_is_left_alone(self):
        self.assertIsNone(self.check("Book an hour for deep work", {"date": "2026-07-27"}))

    def test_a_call_with_no_date_is_left_alone(self):
        self.assertIsNone(self.check("Summarize my Wednesday meetings", {"to": "Jordan"}))
        self.assertIsNone(self.check("Summarize my Wednesday meetings", {}))

    def test_a_date_that_is_not_a_date_is_left_to_the_validator(self):
        self.assertIsNone(self.check("my Wednesday meetings", {"date": "whenever"}))


# ------------------------------------------------------------------- repair ---

class TestRepairAndValidate(unittest.TestCase):
    def test_near_miss_parameter_is_renamed(self):
        args, notes = agent.repair_args("read_email", {"email_id": "e2"})
        self.assertEqual(args, {"id": "e2"})
        self.assertTrue(notes)

    def test_unknown_parameter_is_dropped(self):
        args, notes = agent.repair_args("read_email", {"id": "e2", "colour": "red"})
        self.assertEqual(args, {"id": "e2"})
        self.assertIn("dropped unknown parameter 'colour'", notes)

    def test_validate_names_every_problem_not_just_the_first(self):
        problems = validate_call("add_event", {"title": "x", "nope": 1})
        self.assertTrue(any("date" in p for p in problems))
        self.assertTrue(any("nope" in p for p in problems))

    def test_validate_rejects_an_unknown_tool(self):
        self.assertTrue(validate_call("teleport", {}))


# -------------------------------------------------------------------- world ---

class TestWorld(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.w = World(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_reading_an_unknown_email_says_how_to_find_a_real_one(self):
        with self.assertRaises(ToolError) as cm:
            self.w.read_email("e999")
        self.assertIn("list_emails", str(cm.exception))

    def test_event_must_end_after_it_starts(self):
        with self.assertRaises(ToolError):
            self.w.add_event("x", "2026-07-22", "14:00", "13:00")

    def test_attendees_given_as_a_string_are_split(self):
        ev = self.w.add_event("x", "2026-07-22", "13:00", "14:00", "a@b.com, c@d.com")
        self.assertEqual(ev["attendees"], ["a@b.com", "c@d.com"])

    def test_a_tool_error_is_logged_and_returned_readably(self):
        ok, obs = execute("read_email", {"id": "nope"}, self.w, None)
        self.assertFalse(ok)
        self.assertTrue(obs.startswith("ERROR:"))
        self.assertEqual(self.w.actions[-1]["ok"], False)


class TestCalendarEditing(unittest.TestCase):
    """The calendar was write-only: add an event, never move or cancel one.
    Asked to "move my Design review to Thursday", the agent added a SECOND
    event and reported the meeting moved. The original was still there."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.w = World(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_moving_an_event_changes_it_rather_than_adding_one(self):
        before = len(self.w.events)
        ev = self.w.update_event("c2", date="2026-07-23", start_time="09:00",
                                 end_time="10:00")
        self.assertEqual(len(self.w.events), before)
        self.assertEqual((ev["date"], ev["start"], ev["end"]),
                         ("2026-07-23", "09:00", "10:00"))
        self.assertEqual(ev["title"], "Design review")  # untouched fields survive

    def test_an_update_is_validated_like_a_new_event(self):
        with self.assertRaises(ToolError):
            self.w.update_event("c2", start_time="15:00", end_time="14:00")
        with self.assertRaises(ToolError):
            self.w.update_event("c2", date="next thursday")

    def test_updating_an_event_that_is_not_there_says_how_to_find_one(self):
        with self.assertRaises(ToolError) as cm:
            self.w.update_event("c999", title="x")
        self.assertIn("list_events", str(cm.exception))

    def test_cancelling_removes_it_and_reports_what_went(self):
        out = self.w.cancel_event("c2")
        self.assertEqual(out["cancelled"]["title"], "Design review")
        self.assertNotIn("c2", [e["id"] for e in self.w.events])

    def test_an_id_is_never_handed_out_twice(self):
        """Ids were len(events)+1. Cancelling an event from the middle of the
        list then adding one handed out an id that was still in use: seven
        events, cancel c2, len+1 is 7, and c7 already exists."""
        self.w.cancel_event("c2")
        new = self.w.add_event("Deep work", "2026-07-23", "14:00", "15:00")
        ids = [e["id"] for e in self.w.events]
        self.assertEqual(len(ids), len(set(ids)), ids)
        self.assertEqual(new["id"], "c8")

    def test_both_editors_count_as_writes_for_the_loop(self):
        from harness import agent as a
        src = open(a.__file__).read()
        self.assertIn('"update_event"', src)
        self.assertIn('"cancel_event"', src)


# ------------------------------------------------------------------- memory ---

class TestMemory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "memory.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_facts_survive_a_reload(self):
        MemoryStore(self.path).save("User's manager is Sam.")
        self.assertEqual(MemoryStore(self.path).facts, ["User's manager is Sam."])

    def test_search_ranks_by_overlap_and_returns_nothing_for_a_miss(self):
        m = MemoryStore(self.path)
        m.save("User prefers meetings after 14:00")
        m.save("The office wifi password is hunter2")
        self.assertEqual(m.search("meeting preferences"),
                         ["User prefers meetings after 14:00"])
        self.assertEqual(m.search("quarterly revenue"), [])

    def test_a_torn_line_does_not_brick_the_agent_folder(self):
        """The agent appends to this file itself, so a crash mid-write leaves a
        partial line. Losing that line is fine; refusing to start is not."""
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"fact": "good one"}) + "\n")
            f.write('{"fact": "torn half')  # no newline, no closing brace
        self.assertEqual(MemoryStore(self.path).facts, ["good one"])

    def test_the_same_fact_twice_is_stored_once(self):
        """memory_k is 3 or 4 slots in the system prompt. A model that saves the
        same fact on every run would otherwise spend all of them on one fact."""
        m = MemoryStore(self.path)
        m.save("User's manager is Sam.")
        m.save("  User's manager is Sam.  ")
        self.assertEqual(m.facts, ["User's manager is Sam."])
        self.assertEqual(len(MemoryStore(self.path).facts), 1)


# ----------------------------------------------------------------- profiles ---

class TestProfiles(unittest.TestCase):
    def test_an_exact_tag_wins(self):
        self.assertEqual(profiles.for_model("llama3.2:1b").label, "format-survival")
        self.assertEqual(profiles.for_model("llama3.1:8b").label, "balanced")

    def test_a_quantized_variant_resolves_to_its_own_size(self):
        self.assertEqual(profiles.for_model("llama3.2:1b-instruct-q4_K_M").label,
                         "format-survival")
        self.assertEqual(profiles.for_model("llama3.2:3b-instruct-q8_0").label,
                         "guided-guarded")

    def test_an_unlisted_size_does_not_inherit_a_smaller_sibling(self):
        """llama3.2 happens to list 1b first. Matching on family alone handed an
        11B the 1B's profile: no planning, no verifier, 350-token replies."""
        prof = profiles.for_model("llama3.2:11b")
        self.assertNotEqual(prof.label, "format-survival")
        self.assertTrue(prof.plan)

    def test_an_unknown_model_is_sized_rather_than_given_the_flat_default(self):
        """gemma3:4b and phi4-mini:3.8b are offered in the picker but have no
        profile of their own. Size is the knob that actually predicts the
        failure mode, and the tag states it."""
        self.assertFalse(profiles.for_model("gemma3:1b").plan)
        self.assertEqual(profiles.for_model("phi4-mini:3.8b").verify_rounds, 1)
        self.assertTrue(profiles.for_model("qwen3:8b").plan)

    def test_a_model_with_no_size_in_its_tag_falls_back_to_default(self):
        self.assertEqual(profiles.for_model("some-new-model").label, "default")
        self.assertEqual(profiles.for_model(None).label, "default")

    def test_a_config_block_patches_individual_fields(self):
        prof = profiles.for_model("llama3.1:8b", {"max_calls": 33, "bogus": 1})
        self.assertEqual(prof.max_calls, 33)
        self.assertEqual(prof.label, "balanced")
        self.assertFalse(hasattr(prof, "bogus"))


# ----------------------------------------------------------------- fs_tools ---

class TestFsTools(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self.tmp.name)
        self.saved = dict(TOOLS)
        # execute() logs every call to the world, so the tools need one even
        # though the file tools themselves never read it.
        self.world = World(os.path.join(self.root, ".world"))
        fs_tools.enable(self.root, allow_shell=True, confirm=None)

    def tearDown(self):
        TOOLS.clear()
        TOOLS.update(self.saved)
        self.tmp.cleanup()

    def run_tool(self, name, **args):
        return execute(name, args, self.world, None)

    def test_a_relative_path_lands_inside_the_root(self):
        ok, obs = self.run_tool("write_file", path="notes/todo.txt", content="hi")
        self.assertTrue(ok, obs)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "notes", "todo.txt")))

    def test_escaping_the_root_is_refused(self):
        for bad in ("../outside.txt", "/etc/hosts", "notes/../../outside.txt"):
            ok, obs = self.run_tool("write_file", path=bad, content="x")
            self.assertFalse(ok, f"{bad} was allowed: {obs}")
            self.assertIn("outside the allowed root", obs)

    def test_a_declined_confirmation_tells_the_model_not_to_retry(self):
        open(os.path.join(self.root, "a.txt"), "w").close()
        fs_tools.enable(self.root, allow_shell=True, confirm=lambda *a: False)
        ok, obs = self.run_tool("delete_path", path="a.txt")
        self.assertFalse(ok)
        self.assertIn("Do not retry", obs)
        self.assertTrue(os.path.exists(os.path.join(self.root, "a.txt")))

    def test_shell_stays_off_unless_it_was_asked_for(self):
        fs_tools.enable(self.root, allow_shell=False, confirm=None)
        self.assertNotIn("run_command", TOOLS)

    def test_the_shell_runs_on_this_platform(self):
        """It shelled out to powershell.exe unconditionally, so shell mode could
        not work anywhere but Windows."""
        ok, obs = self.run_tool("run_command", command="echo hello-from-the-shell")
        self.assertTrue(ok, obs)
        self.assertIn("hello-from-the-shell", obs)
        self.assertIn("exit code 0", obs)

    def test_the_examples_use_this_platform_s_separator(self):
        """A model copies the example verbatim. A Windows example on POSIX
        creates one file literally named 'notes\\todo.txt'."""
        for name, spec in TOOLS.items():
            for value in spec["example"]["args"].values():
                if isinstance(value, str) and os.sep == "/":
                    self.assertNotIn("\\", value, f"{name} example is Windows-only")

    def test_the_protected_locations_exist_on_this_platform(self):
        """The deny-list was Windows absolute paths, so on macOS and Linux it
        matched nothing and protected nothing."""
        real = [d for d in fs_tools._DENY_WRITE if os.path.isdir(d)]
        self.assertTrue(real, f"no entry in the deny-list exists here: {fs_tools._DENY_WRITE}")

    def test_a_denied_location_cannot_be_written_even_inside_the_root(self):
        protected = os.path.join(self.root, "protected")
        os.makedirs(protected)
        fs_tools.enable(self.root, allow_shell=False, confirm=None,
                        deny=[protected])
        ok, obs = self.run_tool("write_file", path="protected/x.txt", content="x")
        self.assertFalse(ok, obs)
        self.assertIn("protected", obs)


# ------------------------------------------------------------------- office ---

class TestOffice(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_spreadsheet_round_trips_through_the_reader(self):
        office.create_spreadsheet(self.tmp.name, "costs.xlsx",
                                  [["Item", "Cost"], ["Chairs", 400]])
        out = office.read_spreadsheet(self.tmp.name, "costs.xlsx")
        self.assertEqual(out[0]["rows"][0], ["Item", "Cost"])
        self.assertEqual(out[0]["rows"][1], ["Chairs", 400])

    def test_a_missing_extension_is_added_rather_than_rejected(self):
        office.create_spreadsheet(self.tmp.name, "costs", [["a"]])
        self.assertTrue(os.path.isfile(os.path.join(self.tmp.name, "costs.xlsx")))

    def test_a_filename_cannot_escape_the_files_folder(self):
        office.create_spreadsheet(self.tmp.name, "../escaped.xlsx", [["a"]])
        self.assertFalse(os.path.exists(
            os.path.join(os.path.dirname(self.tmp.name), "escaped.xlsx")))

    def test_a_deck_needs_slides_and_says_so(self):
        with self.assertRaises(ToolError) as cm:
            office.create_presentation(self.tmp.name, "d.pptx", [])
        self.assertIn("slides", str(cm.exception))

    def test_reading_a_spreadsheet_that_was_never_made(self):
        with self.assertRaises(ToolError):
            office.read_spreadsheet(self.tmp.name, "ghost.xlsx")


# ----------------------------------------------------------------- verifier ---

class _StubLLM:
    """Captures the prompt it was handed and answers with a fixed reply."""

    def __init__(self, reply='{"complete": true, "missing": ""}'):
        self.reply = reply
        self.seen = []
        self.calls = 0

    def chat(self, messages, **kw):
        self.seen.append(messages)
        self.calls += 1
        return self.reply


class TestVerifier(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.world = World(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_verifier_is_shown_what_the_actions_returned(self):
        """Given only "create_spreadsheet(...) -> ok" it cannot see that the file
        it is about to ask for already exists. Observed live: it answered
        complete:false against a finished task, the 8B redid the work, and the
        rerun wrote a SECOND spreadsheet - one task, two files for the user."""
        office.create_spreadsheet(self.world.files_dir, "q3.xlsx", [["Region", "Total"]])
        execute("create_spreadsheet",
                {"filename": "q3.xlsx", "rows": [["Region", "Total"]]}, self.world, None)
        llm = _StubLLM()
        agent._verify(llm, self.world, "build a spreadsheet")
        prompt = llm.seen[0][-1]["content"]
        self.assertIn("created q3.xlsx", prompt)

    def test_think_calls_are_left_out_of_the_evidence(self):
        execute("think", {"thought": "pondering"}, self.world, None)
        llm = _StubLLM()
        agent._verify(llm, self.world, "do something")
        self.assertNotIn("pondering", llm.seen[0][-1]["content"])

    def test_an_unusable_verdict_fails_open_but_says_it_did(self):
        """A broken verifier must not trap the agent in a loop it cannot exit.
        But an unmarked complete:true is indistinguishable from a real pass, so
        a systematically broken verifier would read as a clean run forever."""
        verdict = agent._verify(_StubLLM("I think it looks fine!"), self.world, "t")
        self.assertTrue(verdict["complete"])
        self.assertIn("unverified", verdict)

    def test_a_verifier_that_raises_does_not_kill_the_run(self):
        class Boom:
            calls = 0

            def chat(self, *a, **k):
                raise ConnectionError("ollama went away")

        verdict = agent._verify(Boom(), self.world, "t")
        self.assertTrue(verdict["complete"])
        self.assertIn("ConnectionError", verdict["unverified"])


# --------------------------------------------------------------- the loop ---

class _ScriptedLLM:
    """Replies from a fixed list, then repeats the last one forever."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0
        self.output_tokens = self.prompt_tokens = 0
        self.wall = 0.0
        self.seen_feedback = []

    def chat(self, messages, **kw):
        if messages and messages[-1]["role"] == "user":
            self.seen_feedback.append(messages[-1]["content"])
        reply = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        return reply


class TestLoop(unittest.TestCase):
    """run_harness itself, driven by a scripted model. No network."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.world = World(self.tmp.name)
        self.mem = MemoryStore(os.path.join(self.tmp.name, "m.jsonl"))
        self.saved_profile, self.saved_calls = agent.PROFILE, agent.MAX_CALLS
        agent.MAX_CALLS = 12

    def tearDown(self):
        agent.set_profile(self.saved_profile)
        agent.MAX_CALLS = self.saved_calls
        self.tmp.cleanup()

    def call(self, tool, **args):
        return json.dumps({"thought": "x", "tool": tool, "args": args})

    def executed(self, name):
        return [a for a in self.world.actions if a["tool"] == name]

    def test_a_call_that_failed_is_not_run_again_against_the_same_world(self):
        """The repeat budget is there so a model can look at something twice. A
        call that ERRORED cannot return anything new, so a budget of three used
        to buy three copies of one failure - observed live, an 8B spent three of
        its twenty calls on one bad email id."""
        agent.set_profile(profiles.replace(profiles.DEFAULT, plan=False, verify_rounds=0,
                                           repeat_limit=3))
        ep = agent.run_harness(_ScriptedLLM([self.call("read_email", id="c3")]),
                               self.world, self.mem, "read something")
        self.assertEqual(len(self.executed("read_email")), 1)
        self.assertFalse(ep.finished)

    def test_a_call_that_worked_may_still_repeat_up_to_its_budget(self):
        agent.set_profile(profiles.replace(profiles.DEFAULT, plan=False, verify_rounds=0,
                                           repeat_limit=3))
        agent.run_harness(_ScriptedLLM([self.call("list_emails")]),
                          self.world, self.mem, "look at the inbox")
        self.assertEqual(len(self.executed("list_emails")), 3)

    def test_an_identical_write_is_never_repeated(self):
        """A successful write bumps the world and hands out a fresh budget, so
        the guard against a duplicate invite has to be its own rule."""
        agent.set_profile(profiles.replace(profiles.DEFAULT, plan=False, verify_rounds=0,
                                           repeat_limit=3))
        agent.run_harness(
            _ScriptedLLM([self.call("send_message", to="sam", text="hi")]),
            self.world, self.mem, "message sam")
        self.assertEqual(len(self.world.messages), 1)

    def test_writing_before_reading_is_questioned_once(self):
        """The worst failure this app can produce: asked for a spreadsheet of
        July receipts, an 8B skipped the inbox and invented the numbers. The
        plan had named the read step. One nudge, then it gets its way."""
        agent.set_profile(profiles.replace(profiles.DEFAULT, plan=True, verify_rounds=0))
        plan = '{"steps": [{"tool": "list_emails", "what": "find the receipts"}, '
        plan += '{"tool": "create_spreadsheet", "what": "totals"}]}'
        llm = _ScriptedLLM([plan, self.call("create_spreadsheet", filename="r.xlsx",
                                            rows=[["Item", "Cost"], ["made up", 100]])])
        agent.run_harness(llm, self.world, self.mem, "spreadsheet of my July receipts")
        written = self.executed("create_spreadsheet")
        self.assertEqual(len(written), 1, "the nudge should delay the write, not block it")
        nudges = [n for n in llm.seen_feedback if "writing from memory" in n]
        self.assertEqual(len(nudges), 1, "exactly one nudge, or the agent is stuck")

    def test_a_run_that_reads_first_is_never_nudged(self):
        agent.set_profile(profiles.replace(profiles.DEFAULT, plan=True, verify_rounds=0))
        plan = '{"steps": [{"tool": "list_emails", "what": "find them"}, '
        plan += '{"tool": "create_spreadsheet", "what": "totals"}]}'
        llm = _ScriptedLLM([plan, self.call("list_emails"),
                            self.call("create_spreadsheet", filename="r.xlsx",
                                      rows=[["a", 1]]),
                            self.call("done", summary="done")])
        agent.run_harness(llm, self.world, self.mem, "spreadsheet of my July receipts")
        self.assertFalse([n for n in llm.seen_feedback if "writing from memory" in n])

    def test_a_read_planned_after_the_write_is_not_a_source_read(self):
        """A plan of think -> create_spreadsheet -> read_spreadsheet reads back
        the file it is about to make. Nudging toward it sent the agent to open a
        spreadsheet that did not exist yet."""
        agent.set_profile(profiles.replace(profiles.DEFAULT, plan=True, verify_rounds=0))
        plan = ('{"steps": [{"tool": "think", "what": "plan it"}, '
                '{"tool": "create_spreadsheet", "what": "make it"}, '
                '{"tool": "read_spreadsheet", "what": "check it"}]}')
        llm = _ScriptedLLM([plan, self.call("create_spreadsheet", filename="r.xlsx",
                                            rows=[["a", 1]]),
                            self.call("done", summary="done")])
        agent.run_harness(llm, self.world, self.mem, "spreadsheet of my July receipts")
        self.assertFalse([n for n in llm.seen_feedback if "writing from memory" in n])

    def test_done_ends_the_run_and_keeps_the_summary(self):
        agent.set_profile(profiles.replace(profiles.DEFAULT, plan=False, verify_rounds=0))
        ep = agent.run_harness(_ScriptedLLM([self.call("done", summary="all finished")]),
                               self.world, self.mem, "do it")
        self.assertTrue(ep.finished)
        self.assertEqual(ep.done_summary, "all finished")

    def test_the_budget_is_a_hard_stop(self):
        agent.set_profile(profiles.replace(profiles.DEFAULT, plan=False, verify_rounds=0))
        llm = _ScriptedLLM(["not json at all"])
        ep = agent.run_harness(llm, self.world, self.mem, "do it")
        self.assertEqual(llm.calls, agent.MAX_CALLS)
        self.assertFalse(ep.finished)
        self.assertEqual(ep.parse_failures, agent.MAX_CALLS)


# ------------------------------------------------------------------- server ---

class TestWorkspacePanel(unittest.TestCase):
    def test_the_inbox_panel_shows_the_newest_email_first(self):
        """It rendered state.json's insertion order, so a mail that had just
        arrived appeared at the bottom of the inbox under nine older ones."""
        from webui import server
        with tempfile.TemporaryDirectory() as d:
            folder = os.path.join(d, "agents", "demo")
            os.makedirs(os.path.join(folder, "workspace"))
            with open(os.path.join(folder, "config.json"), "w") as f:
                json.dump({"name": "demo", "model": "llama3.1:8b"}, f)
            with open(os.path.join(folder, "workspace", "state.json"), "w") as f:
                json.dump({"emails": [
                    {"id": "a", "date": "2026-07-13 08:00", "subject": "old"},
                    {"id": "b", "date": "2026-07-20 08:40", "subject": "newest"},
                    {"id": "c", "date": "2026-07-15 09:10", "subject": "middle"}]}, f)
            saved = server.AGENTS_DIR
            server.AGENTS_DIR = os.path.join(d, "agents")
            try:
                got = [e["subject"] for e in server.workspace("demo")["emails"]]
            finally:
                server.AGENTS_DIR = saved
        self.assertEqual(got, ["newest", "middle", "old"])


class TestSpreadsheetPreview(unittest.TestCase):
    def test_a_grouped_number_previews_the_way_excel_shows_it(self):
        """office.py writes a #,##0 format, so Excel shows 1,240,000. The
        preview printed str(value) and showed 1240000, which on a demo built
        from an email quoting "$1,240,000" reads as a mangled number."""
        from webui.server import _cell_text

        class Cell:
            number_format = "#,##0"

        class Money:
            number_format = '#,##0.00'

        self.assertEqual(_cell_text(1240000, True, Cell()), "1,240,000")
        self.assertEqual(_cell_text(1240000.5, True, Money()), "1,240,000.50")
        self.assertEqual(_cell_text("West", False, Cell()), "West")
        self.assertEqual(_cell_text(None, False, Cell()), "")

    def test_a_number_with_no_format_is_left_alone(self):
        class Plain:
            number_format = "General"

        from webui.server import _cell_text
        self.assertEqual(_cell_text(2026, True, Plain()), "2026")


# ------------------------------------------------------------------- runner ---

class TestRunner(unittest.TestCase):
    def test_run_numbering_never_reuses_an_index(self):
        from webui.runner import next_run_index
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(next_run_index(d), 1)
            for name in ("run_001.json", "run_003.json", "model_calls.jsonl", "notes.txt"):
                open(os.path.join(d, name), "w").close()
            self.assertEqual(next_run_index(d), 4)  # not 3, and not 5
            os.remove(os.path.join(d, "run_001.json"))
            self.assertEqual(next_run_index(d), 4)  # a deleted run frees nothing


if __name__ == "__main__":
    unittest.main(verbosity=2)
