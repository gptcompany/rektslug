import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from fastapi import WebSocket
from src.liquidationheatmap.api.websocket import ConnectionManager

@pytest.fixture
def manager():
    return ConnectionManager(max_connections_per_key=2)

@pytest.mark.asyncio
async def test_connect_accepts_and_caps(manager):
    ws1 = AsyncMock(spec=WebSocket)
    ws2 = AsyncMock(spec=WebSocket)
    ws3 = AsyncMock(spec=WebSocket)
    
    key = "test_stream"
    
    assert await manager.connect(key, ws1) is True
    ws1.accept.assert_awaited_once()
    
    assert await manager.connect(key, ws2) is True
    ws2.accept.assert_awaited_once()
    
    assert await manager.connect(key, ws3) is False
    ws3.accept.assert_awaited_once()
    ws3.close.assert_awaited_once_with(code=1008, reason="Max connections reached for this stream")
    
    assert len(manager.active_connections[key]) == 2

@pytest.mark.asyncio
async def test_disconnect(manager):
    ws = AsyncMock(spec=WebSocket)
    key = "test_stream"
    
    await manager.connect(key, ws)
    assert len(manager.active_connections[key]) == 1
    
    manager.disconnect(key, ws)
    assert key not in manager.active_connections

@pytest.mark.asyncio
async def test_broadcast_removes_failed_connections(manager):
    ws1 = AsyncMock(spec=WebSocket)
    ws2 = AsyncMock(spec=WebSocket)
    
    # ws2 will fail on send
    ws2.send_json.side_effect = Exception("Connection closed")
    
    key = "test_stream"
    await manager.connect(key, ws1)
    await manager.connect(key, ws2)
    
    payload = {"data": "test"}
    await manager.broadcast(key, payload)
    
    ws1.send_json.assert_awaited_once_with(payload)
    ws2.send_json.assert_awaited_once_with(payload)
    
    # ws2 should be removed
    assert len(manager.active_connections[key]) == 1
    assert ws1 in manager.active_connections[key]
