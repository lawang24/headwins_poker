"""Runout consent, card integrity, payouts, recovery and server deadlines."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
import main
from archive import archive_items, decode
from game import InvalidAction, Table
from main import GameServer
from storage import snapshot, restore, StorageError


def table(stacks=(100, 100)):
    t = Table()
    for i, stack in enumerate(stacks):
        t.join(f"Player {i}").stack = stack
    t.start(t.players[0].id)
    return t


def all_in(t):
    while t.actor:
        state = t.state(t.actor)
        if state["can_raise"]:
            t.act(t.actor, "raise", state["max_raise_to"])
        else:
            t.act(t.actor, "check_call")


def twice(t):
    for pid in list(t.runout_vote["eligible"]):
        t.choose_runouts(pid, 2, t.hand_id)


class RunoutTests(unittest.TestCase):
    def test_no_vote_before_final_call_and_unanimity(self):
        t = table()
        t.act(t.actor, "raise", 100)
        self.assertIsNone(t.runout_vote)
        t.act(t.actor, "check_call")
        a, b = t.players
        self.assertIsNone(t.actor)
        self.assertEqual(t.board, [])
        self.assertTrue(t.running)
        t.choose_runouts(a.id, 2, t.hand_id)
        self.assertIsNone(t.result)
        self.assertEqual(t.board, [])
        view = t.state(b.id)
        self.assertEqual(view["runout_vote"]["votes"], {a.id: 2})
        self.assertNotIn(a.token, json.dumps(view))
        self.assertNotIn("deck_order", json.dumps(view))
        self.assertFalse(any("hand" in p for p in view["players"]))
        t.choose_runouts(b.id, 2, t.hand_id)
        self.assertFalse(t.running)
        self.assertEqual(len(t.result["runouts"]), 2)
        cards = sum((r["board"] for r in t.result["runouts"]), []) + a.hand + b.hand
        self.assertEqual(len(cards), len(set(cards)))
        self.assertEqual(sum(p.stack for p in t.players), 200)

    def test_once_veto_and_duplicate_or_stale_votes(self):
        t = table()
        all_in(t)
        a, b = t.players
        t.choose_runouts(a.id, 2, t.hand_id)
        for pid, count, hand in [(a.id, 2, t.hand_id), (b.id, True, t.hand_id),
                                 (b.id, 3, t.hand_id), (b.id, '2', t.hand_id),
                                 (b.id, 2, 'old-hand')]:
            before = deepcopy(t.runout_vote)
            with self.assertRaises(InvalidAction):
                t.choose_runouts(pid, count, hand)
            self.assertEqual(t.runout_vote, before)
        t.choose_runouts(b.id, 1, t.hand_id)
        self.assertEqual(len(t.result["runouts"]), 1)
        before = [p.stack for p in t.players]
        with self.assertRaises(InvalidAction):
            t.choose_runouts(a.id, 2, t.hand_id)
        t.resolve_runouts(1)
        self.assertEqual(before, [p.stack for p in t.players])

    def test_folded_and_new_players_cannot_vote(self):
        t = table((100, 100, 100))
        folded = t.actor
        t.act(folded, "fold")
        all_in(t)
        guest = t.join("Observer")
        for pid in (folded, guest.id):
            self.assertNotIn(pid, t.runout_vote["eligible"])
            with self.assertRaises(InvalidAction):
                t.choose_runouts(pid, 2, t.hand_id)
        t.disconnect(guest.id)
        self.assertIsNotNone(t.runout_vote)
        twice(t)

    def test_flop_and_turn_prefix_burns_and_archive(self):
        for street in ('flop', 'turn'):
            with self.subTest(street=street):
                t = table()
                while t.street != street:
                    t.act(t.actor, 'check_call')
                prefix = list(t.board)
                remaining = list(reversed(t.deck.cards))
                all_in(t)
                twice(t)
                boards = [r['board'] for r in t.result['runouts']]
                suffixes = [b[len(prefix):] for b in boards]
                expected = [[remaining[1], remaining[3]], [remaining[5], remaining[7]]] if street == 'flop' else [[remaining[1]], [remaining[3]]]
                self.assertEqual(suffixes, expected)
                self.assertTrue(all(b[:len(prefix)] == prefix for b in boards))
                summaries = [decode(item['payload']) for item in archive_items(t.events) if item['sk'] == 'SUMMARY']
                self.assertEqual(summaries[0]['result']['runouts'], t.result['runouts'])
                self.assertEqual(sum(summaries[0]['net'].values()), 0)
                recovered = restore(snapshot(t))
                self.assertEqual(recovered.result, t.result)
                self.assertEqual(sum(p.stack for p in recovered.players), 200)

    def test_river_and_uncontested_hand_do_not_offer(self):
        t = table()
        while t.street != 'river':
            t.act(t.actor, 'check_call')
        all_in(t)
        self.assertIsNone(t.runout_vote)
        self.assertEqual(t.street, 'complete')
        t = table()
        t.act(t.actor, 'fold')
        self.assertIsNone(t.runout_vote)
        self.assertEqual(t.street, 'complete')

    def test_covering_player_disconnect_keeps_eligibility(self):
        t = table((100, 200))
        all_in(t)
        cover = t.players[1]
        self.assertEqual(cover.stack, 100)
        t.disconnect(cover.id)
        self.assertFalse(cover.folded)
        self.assertIn(cover.id, t.result['hands'])
        self.assertEqual(len(t.result['runouts']), 1)
        self.assertEqual(sum(p.stack for p in t.players), 300)

    def test_disconnected_all_in_before_offer_defaults_once(self):
        t = table()
        a = t.player(t.actor)
        t.act(a.id, 'raise', 100)
        t.disconnect(a.id)
        t.act(t.actor, 'check_call')
        self.assertFalse(a.folded)
        self.assertEqual(len(t.result['runouts']), 1)

    def test_restart_during_vote_refunds_and_late_vote_defaults_once(self):
        t = table()
        all_in(t)
        t.choose_runouts(t.players[0].id, 2, t.hand_id)
        recovered = restore(snapshot(t))
        self.assertFalse(recovered.running)
        self.assertIsNone(recovered.runout_vote)
        self.assertEqual([p.stack for p in recovered.players], [100, 100])
        t.runout_vote['deadline'] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        t.choose_runouts(t.players[1].id, 2, t.hand_id)
        self.assertEqual(len(t.result['runouts']), 1)

    def test_two_runouts_split_side_pots_and_return_uncalled_chips(self):
        t = table((50, 100, 200))
        for p, hand, amount in zip(t.players, ('Ah Ad', 'Kh Kd', 'Qh Qd'), (50, 100, 200)):
            p.stack, p.contribution, p.hand = 0, amount, hand.split()
        t.pot = 350
        boards = ['2c 3d 7h 8s 9c'.split(), 'Qs 4d 5h 8c Jc'.split()]
        t.board = boards[0]
        t.finish(boards)
        self.assertEqual([p.stack for p in t.players], [75, 50, 225])
        self.assertEqual([sum(r['payouts'].values()) for r in t.result['runouts']], [125, 125])
        self.assertEqual(sum(p.stack for p in t.players), 350)

    def test_odd_pot_and_ties_conserve_every_chip(self):
        t = table((5, 5, 5))
        for p, hand in zip(t.players, ('Ah Kd', 'As Kc', 'Qh Jd')):
            p.stack, p.contribution, p.hand = 0, 5, hand.split()
        t.players[2].folded = True
        t.pot = 15
        t.runout_vote = None
        t.finish(['2c 3d 7h 8s 9c'.split(), '2d 3c 7c 8h 9d'.split()])
        self.assertEqual([p.stack for p in t.players], [7, 8, 0])
        self.assertEqual([r['pots'][0]['amount'] for r in t.result['runouts']], [8, 7])

    def test_nine_player_preflop_twice_has_enough_unique_cards(self):
        t = table((100,) * 9)
        all_in(t)
        twice(t)
        cards = sum((p.hand for p in t.players), []) + sum((r['board'] for r in t.result['runouts']), [])
        self.assertEqual(len(set(cards)), 28)
        self.assertEqual(len(t.deck.cards), 18)  # Six burn cards as well.
        self.assertEqual(sum(p.stack for p in t.players), 900)


class RunoutTimerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = GameServer(table=table(), auto_deal_delay=3600)
        all_in(self.server.table)

    async def asyncTearDown(self):
        tasks = [t for t in (self.server.deal_task, self.server.runout_task) if t]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def test_deadline_resolves_once_and_broadcast_does_not_reset(self):
        t = self.server.table
        t.runout_vote['deadline'] = (datetime.now(timezone.utc) + timedelta(seconds=.03)).isoformat()
        await self.server.broadcast()
        task = self.server.runout_task
        await self.server.broadcast()
        self.assertIs(task, self.server.runout_task)
        await asyncio.sleep(.08)
        self.assertEqual(len(t.result['runouts']), 1)
        self.assertIsNone(self.server.runout_task)

    async def test_consent_cancels_deadline(self):
        await self.server.broadcast()
        task = self.server.runout_task
        twice(self.server.table)
        await self.server.broadcast()
        await asyncio.sleep(0)
        self.assertTrue(task.cancelled())
        self.assertIsNone(self.server.runout_task)

    async def test_storage_failure_stops_deadline(self):
        await self.server.broadcast()
        self.server.store = Mock(save=Mock(side_effect=OSError('offline')))
        with self.assertRaises(StorageError):
            await self.server.broadcast()
        self.assertTrue(self.server.failed)
        self.assertIsNone(self.server.runout_task)
        self.assertIsNone(self.server.table.result)


class RunoutWebSocketTests(unittest.TestCase):
    def test_choices_shared_reconnect_and_stale_request_rejected(self):
        with patch.dict('os.environ', {'DYNAMODB_TABLE': ''}):
            main.server = GameServer(auto_deal_delay=3600)
            with TestClient(main.app) as client, client.websocket_connect('/ws') as a, client.websocket_connect('/ws') as b:
                a.send_json({'type': 'join', 'name': 'Alice'})
                sa = a.receive_json()
                a.receive_json()
                b.send_json({'type': 'join', 'name': 'Bob'})
                b.receive_json(); b.receive_json(); a.receive_json()
                for socket, action in [(a, {'type': 'start'}), (a, {'type': 'raise', 'amount': 1000}), (b, {'type': 'check_call'})]:
                    socket.send_json(action)
                    aa, bb = a.receive_json()['state'], b.receive_json()['state']
                self.assertEqual(aa['runout_vote'], bb['runout_vote'])
                hand = aa['runout_vote']['hand_id']
                a.send_json({'type': 'runout', 'count': 2, 'hand_id': hand})
                a.receive_json(); b.receive_json()
                with client.websocket_connect('/ws') as replacement:
                    replacement.send_json({'type': 'join', 'name': 'Alice', 'token': sa['token']})
                    replacement.receive_json()
                    state = replacement.receive_json()['state']
                    self.assertEqual(state['runout_vote']['votes'][sa['id']], 2)
                    self.assertEqual(a.receive()['code'], 4001)
                    b.receive_json()
                    b.send_json({'type': 'runout', 'count': 2, 'hand_id': hand})
                    result = b.receive_json()['state']['result']
                    self.assertEqual(len(result['runouts']), 2)
                    self.assertEqual(result, replacement.receive_json()['state']['result'])
                    b.send_json({'type': 'runout', 'count': 1, 'hand_id': hand})
                    self.assertEqual(b.receive_json()['type'], 'error')
                    b.receive_json(); replacement.receive_json()
