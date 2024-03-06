from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.websockets import WebSocketState
import logging
import uvicorn
import asyncio
import enum
import random

app = FastAPI()


class Player:
    def __init__(self) -> None:
        self.can_place = False
        self.bomb = False
        self.armor = False
        self.boost = False
        self.lightning = 0


class BoardUpdateType(enum.Enum):
    PIXEL = 0
    BOMB = 1
    ARMOR = 2


class Game:
    def __init__(self, x, y) -> None:
        self.board = [
            [{"player": None, "armor": False} for x_idx in range(x)]
            for y_idx in range(y)
        ]

    def render(self, for_player) -> list[list[dict]]:
        output = []
        for row in self.board:
            node = []
            for cell in row:
                if cell["player"] == for_player:
                    node.append({"player": 0, "armor": cell["armor"]})
                elif cell["player"] is None:
                    node.append({"player": None, "armor": cell["armor"]})
                else:
                    node.append({"player": 1, "armor": cell["armor"]})
            output.append(node)
        return output

    async def update_board(self, update_type: BoardUpdateType, from_player: WebSocket, x, y):
        if update_type == BoardUpdateType.PIXEL and self.board[y][x]["player"] == None:
            self.board[y][x]["player"] = from_player

        elif update_type == BoardUpdateType.BOMB:
            for y_idx in range(y - 1, y + 2, 1):
                try:
                    for x_idx in range(x - 1, x + 2, 1):
                        try:
                            if (
                                self.board[y_idx][x_idx]["player"] != from_player
                                and not self.board[y_idx][x_idx]["armor"]
                            ):
                                self.board[y_idx][x_idx]["player"] = None
                        except IndexError:
                            continue
                except IndexError as e:
                    continue

        elif update_type == BoardUpdateType.ARMOR:
            for y_idx in range(y - 1, y + 2, 1):
                try:
                    for x_idx in range(x - 1, x + 2, 1):
                        try:
                            if (
                                self.board[y_idx][x_idx]["player"] == from_player
                                and not self.board[y_idx][x_idx]["armor"]
                            ):
                                self.board[y_idx][x_idx]["armor"] = True
                        except IndexError:
                            continue
                except IndexError as e:
                    continue


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[WebSocket, Player] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[websocket] = Player()

    async def broadcast_update(self, game: Game):
            try:
                for websocket in self.active_connections:
                    if websocket.client_state != WebSocketState.DISCONNECTED:
                        await websocket.send_json(
                            {"type": "update", "data": game.render(websocket)}
                        )
            except RuntimeError:
                self.broadcast_update(game)

    def disconnect(self, to_delete: WebSocket):
        for websocket in self.active_connections:
            if to_delete == websocket:
                self.active_connections.pop(websocket)
                return

async def update_can_place(websocket, delay):
    await asyncio.sleep(delay)
    manager.active_connections[websocket].can_place = True

manager = ConnectionManager()
game = Game(10, 10)
print(game.board)


@app.route("/")
async def index(request):
    return HTMLResponse(open("client.html").read())


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    await manager.broadcast_update(game)
    try:
        while True and websocket.client_state != WebSocketState.DISCONNECTED:
            data = await websocket.receive_json()

            if data["type"] == "force":
                manager.active_connections[websocket].can_place = True
                if data["value"] == "boost":
                    manager.active_connections[websocket].boost = True
                elif data["value"] == "lightning":
                    manager.active_connections[websocket].lightning = 5
                elif data["value"] == "bomb":
                    manager.active_connections[websocket].bomb = True
                elif data["value"] == "armor":
                    manager.active_connections[websocket].armor = True

            if data["type"] == "create_test_board":
                for y_idx in range(len(game.board)):
                    for x_idx in range(len(game.board[0])):
                        new_pixel = {}
                        if random.random() > 0.5:
                            if random.random() > 0.5:
                                new_pixel["player"] = "test"
                            else:
                                new_pixel["player"] = websocket
                            if random.random() > 0.7:
                                new_pixel["armor"] = True
                            else:
                                new_pixel["armor"] = False
                        else:
                            new_pixel = {"player": None, "armor": False}
                        game.board[y_idx][x_idx] = new_pixel
                await manager.broadcast_update(game)

            if manager.active_connections[websocket].can_place and data["type"] == "click":
                manager.active_connections[websocket].can_place = False
                if manager.active_connections[websocket].bomb:
                    await game.update_board(
                        BoardUpdateType.BOMB, websocket, data["x"], data["y"]
                    )
                    manager.active_connections[websocket].bomb = False
                elif manager.active_connections[websocket].armor:
                    await game.update_board(
                        BoardUpdateType.ARMOR, websocket, data["x"], data["y"]
                    )
                    manager.active_connections[websocket].armor = False
                else:
                    await game.update_board(
                        BoardUpdateType.PIXEL, websocket, data["x"], data["y"]
                    )
                    if random.random() > 0.7:
                        if random.random() > 0.9:
                            await websocket.send_json({"type": "found", "buff": "armor"})
                            manager.active_connections[websocket].armor = True
                        elif random.random() > 0.9:
                            await websocket.send_json({"type": "found", "buff": "bomb"})
                            manager.active_connections[websocket].bomb = True
                        elif random.random() > 0.7:
                            await websocket.send_json({"type": "found", "buff": "boost"})
                            manager.active_connections[websocket].boost = True
                        elif random.random() > 0.6:
                            await websocket.send_json({"type": "found", "buff": "lightning"})
                            manager.active_connections[websocket].lightning = 5

                
                await manager.broadcast_update(game)

                if manager.active_connections[websocket].boost:
                    asyncio.create_task(update_can_place(websocket, 0))
                elif manager.active_connections[websocket].lightning > 0:
                    manager.active_connections[websocket].lightning -= 1
                    asyncio.create_task(update_can_place(websocket, 2))
                else:
                    asyncio.create_task(update_can_place(websocket, 5))

    except WebSocketDisconnect as e:
        pass

    
        


uvicorn.run(app)
