"""Authenticated social WebSocket presence and invalidation hints."""
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.auth import authenticate_token

router=APIRouter(prefix='/api')
connections={}
def online(user_id): return bool(connections.get(user_id))

async def notify(user_id,message):
    for socket in list(connections.get(user_id,())):
        try: await asyncio.wait_for(socket.send_json(message),2)
        except Exception: connections.get(user_id,set()).discard(socket)

async def authenticate_socket(socket):
    origin=socket.headers.get('origin')
    if origin:
        from app.main import allowed_origins
        from app.core.origins import origin_allowed
        if not origin_allowed(origin,allowed_origins):
            await socket.close(code=1008); return None
    await socket.accept()
    try:
        hello=await asyncio.wait_for(socket.receive_json(),5)
        user=authenticate_token(hello.get('token','')) if isinstance(hello,dict) and hello.get('type')=='authenticate' else None
        if user: return user
    except (asyncio.TimeoutError,ValueError,WebSocketDisconnect): pass
    await socket.close(code=4401)
    return None

@router.websocket('/realtime/ws')
async def realtime(socket:WebSocket):
    user=await authenticate_socket(socket)
    if not user: return
    uid=user['id']; connections.setdefault(uid,set()).add(socket)
    try:
        await socket.send_json({'type':'authenticated','user_id':uid})
        while True:
            message=await socket.receive_json()
            if isinstance(message,dict) and message.get('type')=='ping': await socket.send_json({'type':'pong'})
    except (WebSocketDisconnect,RuntimeError,ValueError): pass
    finally:
        connections.get(uid,set()).discard(socket)
        if not connections.get(uid): connections.pop(uid,None)
