from fastapi import FastAPI, WebSocket, WebSocketDisconnect

def getPlayerFromWebsocket(websocket: WebSocket, game):
    for player in game.players:
        if websocket == player.websocket:
            return player

    raise RuntimeError("raising from disconnected")
