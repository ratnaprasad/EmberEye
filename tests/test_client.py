import websockets
import asyncio
import json

async def test_client():
    uri = "ws://192.168.2.49:8765"
    async with websockets.connect(uri) as websocket:
        data = {
            "loc_id": "500001",
            "temperature": 45.6,
            "fire_alarm": False
        }
        await websocket.send(json.dumps(data))
        response = await websocket.recv()
        print(f"Server response: {response}")

asyncio.run(test_client())