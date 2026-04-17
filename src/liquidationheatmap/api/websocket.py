import asyncio
import logging
from typing import Dict, List, Set, Any
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self, max_connections_per_key: int = 100):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.max_connections_per_key = max_connections_per_key
        self._heartbeat_task = None

    async def connect(self, key: str, websocket: WebSocket) -> bool:
        await websocket.accept()
        
        if key not in self.active_connections:
            self.active_connections[key] = set()
            
        if len(self.active_connections[key]) >= self.max_connections_per_key:
            # Reached cap, reject connection
            await websocket.close(code=1008, reason="Max connections reached for this stream")
            return False
            
        self.active_connections[key].add(websocket)
        
        try:
            stream_type, symbol, _ = key.split(":")
            from src.liquidationheatmap.api.metrics import WS_ACTIVE_CONNECTIONS
            WS_ACTIVE_CONNECTIONS.labels(stream_type=stream_type, symbol=symbol).inc()
        except ValueError:
            pass

        logger.info(f"WebSocket connected to {key}. Total: {len(self.active_connections[key])}")
        return True

    def disconnect(self, key: str, websocket: WebSocket):
        if key in self.active_connections:
            self.active_connections[key].discard(websocket)
            if not self.active_connections[key]:
                del self.active_connections[key]
                
            try:
                stream_type, symbol, _ = key.split(":")
                from src.liquidationheatmap.api.metrics import WS_ACTIVE_CONNECTIONS
                WS_ACTIVE_CONNECTIONS.labels(stream_type=stream_type, symbol=symbol).dec()
            except ValueError:
                pass
                
            logger.info(f"WebSocket disconnected from {key}.")

    async def broadcast(self, key: str, payload: Any):
        if key not in self.active_connections:
            return
            
        disconnected = set()
        for connection in self.active_connections[key]:
            try:
                await connection.send_json(payload)
            except Exception as e:
                logger.warning(f"Error broadcasting to a connection on {key}: {e}")
                disconnected.add(connection)
                
        # Clean up failed connections
        for connection in disconnected:
            self.disconnect(key, connection)

    async def heartbeat_loop(self, interval_seconds: int = 30):
        """Periodically ping all connections to detect stale ones."""
        while True:
            await asyncio.sleep(interval_seconds)
            for key, connections in list(self.active_connections.items()):
                disconnected = set()
                for connection in connections:
                    try:
                        # sending a simple ping text message or json payload
                        await connection.send_json({"type": "heartbeat", "status": "ok"})
                    except Exception:
                        disconnected.add(connection)
                        
                for connection in disconnected:
                    self.disconnect(key, connection)

    def start_heartbeat(self, interval_seconds: int = 30):
        """Start heartbeat loop as background task if event loop is running."""
        try:
            loop = asyncio.get_running_loop()
            self._heartbeat_task = loop.create_task(self.heartbeat_loop(interval_seconds))
        except RuntimeError:
            pass

manager = ConnectionManager()
