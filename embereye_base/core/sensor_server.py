# sensor_server.py
import asyncio
import websockets
import json
from datetime import datetime
import threading
import functools

class SensorServer:
    def __init__(self, host='0.0.0.0', port=8765):
        self.host = host
        self.port = port
        self.server = None
        self.loop = None
        self.server_thread = None
        self.running = False
        self.stop_event = asyncio.Event()
        self.connected_clients = set()  # Add this line

    async def handler(self, websocket):
        self.connected_clients.add(websocket)
        try:
            async for message in websocket:
                data = json.loads(message)
                if self.validate_data(data):
                    await self.process_message(websocket, data)
        except websockets.exceptions.ConnectionClosedOK:
            pass
        except Exception as e:
            print(f"Connection error: {str(e)}")
        finally:
            self.connected_clients.remove(websocket)

    def validate_data(self, data):
        required = ['loc_id', 'temperature', 'fire_alarm']
        return all(key in data for key in required)

    async def process_message(self, websocket, data):
        data['timestamp'] = datetime.now().isoformat()
        print(f"Received sensor data: {data}")
        # Broadcast to all connected clients
        await self.broadcast(data)
        await websocket.send(json.dumps({"status": "ACK"}))
        
    async def broadcast(self, data):
        """Send data to all connected clients"""
        if self.connected_clients:
            message = json.dumps(data)
            await asyncio.gather(
                *[client.send(message) for client in self.connected_clients]
            )

    async def server_main(self):
        handler = functools.partial(self.handler)
        async with websockets.serve(handler, self.host, self.port):
            await self.stop_event.wait()

    def start_server(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self.server_main())
        finally:
            self.loop.close()

    def start(self):
        if not self.running:
            self.running = True
            self.server_thread = threading.Thread(
                target=self.start_server, 
                daemon=True
            )
            self.server_thread.start()
            print(f"Server started on ws://{self.host}:{self.port}")

    def stop(self):
        if self.running:
            self.running = False
            self.loop.call_soon_threadsafe(self.stop_event.set)
            self.server_thread.join(timeout=5)
            print("Server stopped")

if __name__ == "__main__":
    server = SensorServer()
    try:
        server.start()
        # Keep main thread alive
        while True:
            pass
    except KeyboardInterrupt:
        server.stop()