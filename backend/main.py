from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
import time
from typing import List
import json
from deck_of_cards import DeckOfCards
from phevaluator.evaluator import evaluate_cards

app = FastAPI()

class ConnectionManager:

    def __init__(self):
        return

    async def connect(self, websocket: WebSocket):
        await websocket.accept()

        await manager.send_game_state_to_all()

    async def send_game_state_to_all(self):
        await manager.send_to_all({"type" : "game_state_update" , "game_state": GAME._get_shared_state()})

    def get_username(self, websocket: WebSocket) -> str:
        for player in GAME.players:
            if websocket == player.websocket:
                return player.username 
        return "Not found"

    async def disconnect(self, websocket: WebSocket) -> None:
        global HOST
        
        for i, player in enumerate(GAME.players):
            if player.websocket == websocket:
                GAME.players.pop(i)
                break
        else:
            # Optional: handle the case where the websocket wasn't found
            print("Player with this websocket not found in GAME.players")

    async def send_to_all(self, message: object):
        for player in GAME.players:
            await self.send_to_one(player.websocket, message)

    async def send_to_one(self, websocket: WebSocket, message: object):
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.send_text(json.dumps(message))
            except Exception:
                await self.disconnect(websocket)


class GameState:
    def __init__(self):
        self.deck = DeckOfCards()
        self.deck.shuffle()
        self.pot = 0
        self.players : List[Player] = []
        self.board: List[str]= []
        self.dealer_index = 0
        self.small_blind = 5
        self.big_blind = 10
        self.started = False
        self.current_player_index = 0
        self.people_in_hand : List[Player] = []
        self.last_raise = 0
        self.threshold = 0

    async def restart_round(self):
        self.started = True
        self.pot = 0
        self.board = []

        # shuffle the deck
        self.deck = DeckOfCards()
        self.deck.shuffle()

        active_player_count = 0
        # draw cards
        for player in self.players:
            if player.isActive:
                active_player_count+=1
                player.isInHand = True
                player.hand = [self.deck.draw(), self.deck.draw()]
                await manager.send_to_one(player.websocket, {"type": "get_hand", "hand" : player.hand})
        
        if active_player_count == 0:
            return
        
        # increment the dealer between hands
        self.dealer_index = (self.dealer_index + 1) % active_player_count
        while not self.players[self.dealer_index].isActive:
            self.dealer_index = (self.dealer_index + 1) % active_player_count

        n_players = len(self.players)
        # assign position ordering for each person
        for i in range(n_players):
            self.players[(self.dealer_index + i) % n_players].position = i

        await self.start_round(True)

    async def start_round(self, preflop: bool):

        print("starting new betting rotation")
        self.people_in_hand = [p for p in self.players if p.isInHand]
        self.people_in_hand.sort(key= lambda x: x.position)

        if len(self.board) == 5 or len(self.people_in_hand) <= 1: 
            await self.end_round()
            return

        # reset the player status
        for p in self.people_in_hand:
            p.money_commited_this_round = 0
            p.ready_to_see_next_round = False
            p.your_turn = False
        
        # allow the small and big blind to go last
        if preflop:
            self.current_player_index = 2
            self.threshold = self.big_blind
            self.people_in_hand[(self.current_player_index) % len(self.people_in_hand)].money_commited_this_round  = self.small_blind
            self.people_in_hand[(self.current_player_index+1) % len(self.people_in_hand)].money_commited_this_round  = self.big_blind
            self.pot = self.big_blind + self.small_blind
        else:
           self.current_player_index = 0
           self.board.append(self.deck.draw())
           self.threshold = 0

        self.current_player_index %= len(self.people_in_hand)
        
        await self.allow_to_raise()

    def _get_shared_state(self):
        # Don’t send private server objects like the deck
        return {
            "pot": self.pot,
            "big_blind": self.big_blind,
            "small_blind": self.small_blind,
            "board": self.board,                          
            "players": [p.get_shared_payload() for p in self.players],
            "threshold": self.threshold,
            "last_raise": self.last_raise,
            "started": self.started,
        }
    
    async def allow_to_raise(self):
        self.people_in_hand[self.current_player_index % len(self.people_in_hand)].your_turn = True

    async def set_blind(self, player, amount):
        await manager.send_to_one(player.websocket, {"type": "set_blind", "amount": amount})

    async def end_round(self):
        
        live_players = [p for p in self.players if p.isInHand]

        # didnt' get the river
        if len(live_players) == 1:
            pot_winner = live_players[0]  # compare by the evaluate_cards score )[1]  # get the player
        else:
            # minimum hand ranking takes it
            ranks = [(evaluate_cards(*(self.board+p.hand)), p) for p in live_players]
            pot_winner = min(ranks, key=lambda x: x[0])[1]  # compare by the evaluate_cards score )[1]  # get the player
        
        #TODO: implement chopped pots
        await manager.send_to_all(f"{pot_winner.username} wins the pot")
        pot_winner.stack_size+=GAME.pot

        await self.restart_round()

            
class Player:
    def __init__(self, websocket: WebSocket, username : str):
        self.username = username
        self.isActive = True
        self.isInHand = False
        self.stack_size = 0
        self.hand : List[str] = []
        self.websocket = websocket
        self.position = 0
        self.ready_to_see_next_round = False
        self.money_commited_this_round = 0
        self.your_turn = False

    def get_shared_payload(self):
        return {
            "username": self.username,
            "isActive": self.isActive,
            "isInHand": self.isInHand,
            "stack_size": self.stack_size,
            "money_commited_this_round": self.money_commited_this_round,
            "your_turn": self.your_turn
        }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)

    while True:
        try:
            data_str = await websocket.receive_text()
        except WebSocketDisconnect:
            print("That brother has already left!")
            await manager.disconnect(websocket)
            break
        except RuntimeError as e:
            print('That brother is already disconnecting.. chill...')
            print(e)
            break

        data = json.loads(data_str)

        print('received', data)
        msg_type = data.get("type")

        match msg_type:

            case "join":
                username = data.get("username")
                GAME.players.append(Player(websocket, username))

            case "message":
                username = manager.get_username(websocket)
                text = data.get("text", "")
                await manager.send_to_all(f"{username}: {text}")

            case "start_game":
                await GAME.restart_round()

            case "commit_money":
                raise_amount = data.get("amount")
                username = manager.get_username(websocket)
                await manager.send_to_all(f"{username}: puts in {raise_amount}")

                # new raiser, everyone else needs to check as well
                if raise_amount > GAME.threshold:
                    for p in GAME.people_in_hand:
                        p.ready_to_see_next_round = False
                    GAME.last_raise = raise_amount - GAME.threshold
                    GAME.threshold = raise_amount
                
                GAME.pot+= raise_amount - GAME.people_in_hand[GAME.current_player_index].money_commited_this_round 
                GAME.people_in_hand[GAME.current_player_index].money_commited_this_round = raise_amount
                GAME.people_in_hand[GAME.current_player_index].ready_to_see_next_round = True
                GAME.people_in_hand[GAME.current_player_index].your_turn = False

                if all(p.ready_to_see_next_round for p in GAME.people_in_hand):
                    await GAME.start_round(False)
                else:
                    # let the next person bet
                    GAME.current_player_index = (GAME.current_player_index+ 1) % len(GAME.people_in_hand)
                    GAME.people_in_hand[GAME.current_player_index].your_turn = True


            case "fold":
                GAME.people_in_hand[GAME.current_player_index].ready_to_see_next_round = True
                GAME.people_in_hand[GAME.current_player_index].isInHand = False

                # there's a chance you fold and it automatically ends
                if sum([p.isInHand for p in GAME.players]) == 1:
                    await GAME.end_round()
                else:
                    if all(p.ready_to_see_next_round for p in GAME.people_in_hand):
                        await GAME.start_round(False)
                    else:
                        # let the next person bet
                        GAME.current_player_index = (GAME.current_player_index+ 1) % len(GAME.people_in_hand)
                        GAME.people_in_hand[GAME.current_player_index].your_turn = True

            case _:
                await manager.send_to_one(
                    websocket, f"Unknown message type: {msg_type}"
                )

        await manager.send_game_state_to_all()

manager = ConnectionManager()
GAME = GameState()
    