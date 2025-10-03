from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.orm import Session
from database.structure import get_session
from oauth2.ws_auth import get_current_ws
from typing import Dict
import asyncio
router = APIRouter()

active_connections : dict[str, WebSocket] = {}

# runs in the background without interrupting the uvicorn reload task
async def heartbeat(ws: WebSocket, email:str):
    try:
        while True:
            await asyncio.sleep(30)   # <-- wait 30 seconds
            await ws.send_text("__ping__")  # <-- send heartbeat
    except (WebSocketDisconnect, RuntimeError):        
        # stop sending pings once the socket is closed
        print("Heartbeat stopped (client disconnected)")
        active_connections.pop(email, None)
    
# For basic notifications
@router.websocket('/ws/notifications')
async def notifications(websocket:WebSocket, session:Session = Depends(get_session)):
    await websocket.accept()
    email = None
  
    current_user = await get_current_ws(websocket, session)
    if not current_user: 
        print('Connection failed')
        return
    print('connection open')
    email = current_user.email
    active_connections[email] = websocket 
    print('email stored in wbesocket', websocket)
    print(active_connections)
    
    asyncio.create_task(heartbeat(websocket, email))
    try:
        # Keep connection open
        while True:
            await websocket.receive_text()  # <== This keeps it alive
    except (WebSocketDisconnect, RuntimeError):
        active_connections.pop(email, None)
        print("Connection closed and removed")
        