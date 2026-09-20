import asyncio
import json
import unittest

from game import Table, InvalidAction
from main import GameServer
from storage import snapshot, restore


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.table = Table()
        self.a = self.table.join("Alice")
        self.b = self.table.join("Bob")

    def test_any_player_can_update_shared_settings_and_blinds(self):
        self.table.set_settings(self.b.id, 25, 50, True, True)
        for player in (self.a, self.b):
            state = self.table.state(player.id)
            self.assertEqual((state["small_blind"], state["big_blind"]), (25, 50))
            self.assertTrue(state["cents"])
            self.assertTrue(state["auto_deal"])
        self.table.start(self.a.id)
        self.assertEqual(self.table.pot, 75)
        self.assertEqual(self.table.min_raise, 50)

    def test_invalid_settings_are_atomic(self):
        for sb, bb, auto, cents in [(0, 10, False, False), (20, 10, False, False),
                                    (1.5, 10, False, False), (True, 10, False, False),
                                    (5, 1000001, False, False), (5, 10, 1, False),
                                    (5, 10, False, "yes")]:
            with self.subTest(values=(sb, bb, auto, cents)):
                with self.assertRaises(InvalidAction):
                    self.table.set_settings(self.b.id, sb, bb, auto, cents)
                self.assertEqual((self.table.small_blind, self.table.big_blind,
                                  self.table.auto_deal, self.table.cents), (5, 10, True, False))

    def test_live_hand_rejects_denomination_changes(self):
        self.table.start(self.a.id)
        for values in [(25, 50, True, False), (5, 10, True, True)]:
            with self.assertRaises(InvalidAction):
                self.table.set_settings(self.b.id, *values)
        self.table.set_settings(self.b.id, 5, 10, True, False)
        self.assertTrue(self.table.auto_deal)

    def test_checkpoint_roundtrip_and_legacy_defaults(self):
        self.table.set_settings(self.b.id, 25, 50, True, True)
        saved = snapshot(self.table)
        recovered = restore(saved)
        self.assertEqual((recovered.small_blind, recovered.big_blind,
                          recovered.auto_deal, recovered.cents), (25, 50, True, True))
        old = json.loads(saved)
        old["auto_deal"] = False
        self.assertTrue(restore(json.dumps(old)).auto_deal)
        del old["auto_deal"]
        del old["cents"]
        recovered = restore(json.dumps(old))
        self.assertTrue(recovered.auto_deal)
        self.assertFalse(recovered.cents)


class AutoDealTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = GameServer(auto_deal_delay=.02)
        self.a = self.server.table.join("Alice")
        self.server.table.join("Bob")

    async def asyncTearDown(self):
        if self.server.deal_task:
            self.server.deal_task.cancel()
            await asyncio.gather(self.server.deal_task, return_exceptions=True)

    async def finish_hand(self):
        self.server.table.start(self.a.id)
        self.server.table.act(self.server.table.actor, "fold")
        await self.server.broadcast()

    async def test_first_and_subsequent_hands_deal_automatically(self):
        await self.server.broadcast()
        self.assertIsNotNone(self.server.deal_task)
        await asyncio.sleep(.05)
        self.assertEqual(self.server.table.hand_number, 1)
        self.assertTrue(self.server.table.running)
        self.server.table.act(self.server.table.actor, "fold")
        await self.server.broadcast()
        self.assertEqual(self.server.table.street, "complete")
        task = self.server.deal_task
        await self.server.broadcast()
        self.assertIs(self.server.deal_task, task)
        await asyncio.sleep(.05)
        self.assertEqual(self.server.table.hand_number, 2)
        self.assertTrue(self.server.table.running)

    async def test_legacy_setting_cannot_disable_automatic_dealing(self):
        await self.finish_hand()
        self.server.table.set_settings(self.a.id, 5, 10, False, False)
        await self.server.broadcast()
        await asyncio.sleep(.05)
        self.assertEqual(self.server.table.hand_number, 2)
        self.assertTrue(self.server.table.auto_deal)

    async def test_manual_deal_cancels_timer(self):
        await self.finish_hand()
        self.server.table.start(self.a.id)
        await self.server.broadcast()
        await asyncio.sleep(.05)
        self.assertEqual(self.server.table.hand_number, 2)
        self.assertIsNone(self.server.deal_task)

    async def test_disconnect_pauses_until_enough_players(self):
        await self.finish_hand()
        self.server.table.disconnect(self.a.id)
        await self.server.broadcast()
        await asyncio.sleep(.05)
        self.assertEqual(self.server.table.hand_number, 1)
        self.server.table.join("Alice", self.a.token)
        await self.server.broadcast()
        await asyncio.sleep(.05)
        self.assertEqual(self.server.table.hand_number, 2)

    async def test_insufficient_funded_players_pause_first_deal(self):
        self.server.table.set_stack(self.a.id, 0)
        await self.server.broadcast()
        self.assertIsNone(self.server.deal_task)
        self.server.table.set_stack(self.a.id, 1000)
        await self.server.broadcast()
        await asyncio.sleep(.05)
        self.assertEqual(self.server.table.hand_number, 1)

    async def test_failure_prevents_dealing(self):
        await self.server.broadcast()
        self.server.failed = True
        await asyncio.sleep(.05)
        self.assertEqual(self.server.table.hand_number, 0)
