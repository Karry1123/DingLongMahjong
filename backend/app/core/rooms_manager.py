"""Single-worker authoritative room lifecycle. All mutations and broadcasts are serialized."""
import asyncio
import time
import logging
import json

from fastapi import HTTPException

from app.core.pvp_match import PvpMatch


class RoomsManager:
    def __init__(self, countdown_seconds=3, opening_seconds=3.6):
        self.connections = {}
        self.countdowns = {}
        self.games = {}
        self.game_tasks = {}
        self.countdown_seconds = countdown_seconds
        self.opening_seconds = opening_seconds
        self.lock = asyncio.Lock()
        self.disconnect_seconds = 60
        self.disconnects = {}
        self.roster_locked = set()

    async def attach(self, room_id, user_id, socket):
        from app.storage.db import connect
        from app.core.match_repository import membership_snapshot
        async with self.lock:
            if user_id in self.connections.get(room_id, {}):
                raise HTTPException(409, "此玩家已在另一窗口入席")
            with connect() as db:
                membership_snapshot(db, room_id, user_id)
            task = self.disconnects.pop((room_id, user_id), None)
            if task: task.cancel()
            self.connections.setdefault(room_id, {})[user_id] = socket
            await self._broadcast(room_id)

    async def _send(self, socket, message):
        try:
            await asyncio.wait_for(socket.send_json(message), timeout=2)
            return True
        except Exception:
            return False

    async def _broadcast(self, room_id):
        from app.storage.db import connect
        from app.core.match_repository import membership_snapshot
        game = self.games.get(room_id)
        if game and game.phase == 'finished' and not game.archived:
            from app.core.pvp_records import archive_pvp_game
            try:
                await asyncio.to_thread(archive_pvp_game, game.archive_record())
                with connect() as db:
                    from app.storage.db import utcnow
                    db.execute('INSERT INTO match_hands(match_id,game_id,hand_number,scores,finished_at) VALUES(?,?,?,?,?) ON CONFLICT(game_id) DO NOTHING', (room_id,game.game_id,game.hand_number,json.dumps(game.room_scores),utcnow()))
                game.archived = True
                game.result.pop('archive_error', None)
            except Exception:
                logging.exception('PvP archive failed for %s', game.game_id)
                game.result['archive_error'] = '牌谱保存失败'
        sockets = list(self.connections.get(room_id, {}).items())
        messages = []
        with connect() as db:
            for user_id, socket in sockets:
                room = membership_snapshot(db, room_id, user_id)
                room["players"] = [{**p, "connected": p["is_ai"] or self._seat_connected(db, room_id, p["seat"])} for p in room["players"]]
                message = {"type": "room_state", "room": room, "server_time": time.time() * 1000}
                if room["status"] == "playing":
                    game = self.games.get(room_id)
                    if game:
                        message["game"] = game.view(game.wind_for_room_seat("ESWN"[room["my_seat"]]))
                messages.append((socket, message))
        results = await asyncio.gather(*(self._send(socket, message) for socket, message in messages))
        if not all(results):
            for (user_id, socket), ok in zip(sockets, results):
                if not ok:
                    self._disconnect(room_id, user_id, socket)
            if self.connections.get(room_id):
                await self._broadcast(room_id)

    def _seat_connected(self, db, room_id, seat):
        member = db.execute("SELECT user_id FROM match_members WHERE match_id=? AND seat=?", (room_id, seat + 1)).fetchone()
        return bool(member and member["user_id"] in self.connections.get(room_id, {}))

    async def handle(self, room_id, user_id, socket, message):
        from app.storage.db import connect
        from app.core.match_repository import membership_snapshot
        async with self.lock:
            if self.connections.get(room_id, {}).get(user_id) is not socket:
                raise HTTPException(403, "连接已失效")
            kind = message.get("type")
            if kind == "ping":
                await self._send(socket, {"type": "pong", "server_time": time.time() * 1000})
                return
            if kind == "leave":
                await self._leave(room_id, user_id)
                return
            if kind in ("game_action", "opening_complete", "next_hand"):
                with connect() as db:
                    room = membership_snapshot(db, room_id, user_id)
                game = self.games.get(room_id)
                if not game:
                    raise HTTPException(409, "牌局尚未开始")
                if kind == "opening_complete":
                    game.acknowledge_opening(game.wind_for_room_seat("ESWN"[room["my_seat"]]), message.get("game_id"))
                    return
                if kind == "next_hand":
                    if game.phase == 'finished' and message.get('game_id') == game.game_id and not game.archived:
                        await self._broadcast(room_id)
                        if not game.archived:
                            raise HTTPException(503, '牌谱保存失败，请稍后重试')
                    if game.confirm_next(game.wind_for_room_seat("ESWN"[room["my_seat"]]), message.get("game_id")):
                        previous_task = self.game_tasks.pop(room_id, None)
                        if previous_task:
                            previous_task.cancel()
                        self.games[room_id] = PvpMatch(room["players"], opening_seconds=self.opening_seconds, dealer_seat=game.next_dealer, hand_number=game.hand_number + 1, circle_number=game.circle_number + int(game.circle_complete), scores=game.room_scores)
                        self.game_tasks[room_id] = asyncio.create_task(self._run_game(room_id, opening=True))
                    await self._broadcast(room_id)
                    return
                if game.tick():
                    await self._broadcast(room_id)
                game.act(game.wind_for_room_seat("ESWN"[room["my_seat"]]), message)
                await self._broadcast(room_id)
                self._schedule_bots(room_id)
                return
            with connect() as db:
                room = membership_snapshot(db, room_id, user_id)
                if room["status"] == "playing":
                    raise HTTPException(409, "对局已开始，不能换座或修改准备状态")
                if kind == "seat":
                    wind = message.get("seat")
                    if wind not in ("E", "S", "W", "N"):
                        raise HTTPException(422, "请选择有效风位")
                    seat = "ESWN".index(wind)
                    occupant = db.execute("SELECT user_id FROM match_members WHERE match_id=? AND seat=?", (room_id, seat + 1)).fetchone()
                    if occupant and occupant["user_id"] != user_id:
                        raise HTTPException(409, "此风位已有玩家，请选择空位")
                    if seat == room["my_seat"]:
                        return
                    db.execute("UPDATE match_members SET seat=?, ready=0 WHERE match_id=? AND user_id=?", (seat + 1, room_id, user_id))
                elif kind == "ready":
                    if not isinstance(message.get("ready"), bool):
                        raise HTTPException(422, "准备状态必须为布尔值")
                    db.execute("UPDATE match_members SET ready=? WHERE match_id=? AND user_id=?", (int(message["ready"]), room_id, user_id))
                else:
                    raise HTTPException(422, "暂不支持此房间操作")
                updated = membership_snapshot(db, room_id, user_id)
                humans = [p for p in updated["players"] if not p["is_ai"]]
                all_ready = len(humans) == updated["capacity"] and all(p["ready"] for p in humans) and len(self.connections.get(room_id, {})) == len(humans)
                if all_ready and updated["status"] == "waiting" and room_id in self.roster_locked:
                    deadline = time.time() + self.countdown_seconds
                    db.execute("UPDATE matches SET status='countdown', start_at=? WHERE id=?", (deadline * 1000, room_id))
                    self.countdowns[room_id] = asyncio.create_task(self._start_after(room_id, deadline))
                elif not all_ready and updated["status"] == "countdown":
                    self._cancel_countdown(room_id)
                    db.execute("UPDATE matches SET status='waiting', start_at=NULL WHERE id=?", (room_id,))
            await self._broadcast(room_id)

    def _cancel_countdown(self, room_id):
        task = self.countdowns.pop(room_id, None)
        if task and task is not asyncio.current_task():
            task.cancel()

    async def _start_after(self, room_id, deadline):
        from app.storage.db import connect
        from app.core.match_repository import snapshot
        try:
            await asyncio.sleep(max(0, deadline - time.time()))
            async with self.lock:
                with connect() as db:
                    room = snapshot(db, room_id)
                    humans = [p for p in room["players"] if not p["is_ai"]]
                    if room["status"] != "countdown" or len(humans) != room["capacity"] or not all(p["ready"] for p in humans):
                        return
                    self.games[room_id] = PvpMatch(room["players"], opening_seconds=self.opening_seconds)
                    db.execute("UPDATE matches SET status='playing' WHERE id=?", (room_id,))
                await self._broadcast(room_id)
                if room_id in self.games:
                    self.game_tasks[room_id] = asyncio.create_task(self._run_game(room_id, opening=True))
        except asyncio.CancelledError:
            pass
        finally:
            # A cancelled old task must not remove a newer countdown for this room.
            if self.countdowns.get(room_id) is asyncio.current_task():
                self.countdowns.pop(room_id, None)

    def _schedule_bots(self, room_id):
        if room_id in self.games and room_id not in self.game_tasks:
            self.game_tasks[room_id] = asyncio.create_task(self._run_game(room_id))

    async def _run_game(self, room_id, opening=False):
        try:
            if opening:
                game = self.games[room_id]
                await asyncio.sleep(max(0, (game.opening_ends_at - time.time() * 1000) / 1000))
                while True:
                    async with self.lock:
                        if room_id not in self.games:
                            return
                        if len(game.opening_ready) == 4:
                            game.begin()
                            await self._broadcast(room_id)
                            break
                    await asyncio.sleep(.05)
            last_clock_broadcast = time.monotonic()
            while room_id in self.games:
                await asyncio.sleep(.05)
                async with self.lock:
                    game = self.games.get(room_id)
                    if not game:
                        return
                    changed = game.tick()
                    if game.phase == "finished":
                        if changed:
                            await self._broadcast(room_id)
                        return
                    choice = game.bot_action(ready_only=True)
                    if choice:
                        seat, action = choice
                        game.act(seat, {"game_id": game.game_id, "revision": game.revision, "action_id": action["action_id"]})
                        changed = True
                    if changed or time.monotonic() - last_clock_broadcast >= 1:
                        await self._broadcast(room_id)
                        last_clock_broadcast = time.monotonic()

        except asyncio.CancelledError:
            pass
        finally:
            if self.game_tasks.get(room_id) is asyncio.current_task():
                self.game_tasks.pop(room_id, None)

    async def _dissolve_for_player(self, room_id, user_id, action):
        from app.storage.db import connect
        from app.core.match_repository import membership_snapshot
        with connect() as db:
            room = membership_snapshot(db, room_id, user_id)
        name = next(p["nickname"] for p in room["players"] if p["seat"] == room["my_seat"])
        await self._dissolve(room_id, f"玩家 {name} {action}，房间已解散")

    async def _dissolve(self, room_id, reason):
        from app.storage.db import connect
        self._cancel_countdown(room_id)
        game_task = self.game_tasks.pop(room_id, None)
        if game_task and game_task is not asyncio.current_task():
            game_task.cancel()
        self.games.pop(room_id, None)
        self.roster_locked.discard(room_id)
        for key, task in list(self.disconnects.items()):
            if key[0] == room_id:
                self.disconnects.pop(key, None)
                if task is not asyncio.current_task(): task.cancel()
        with connect() as db:
            from app.storage.db import utcnow
            row = db.execute('SELECT status FROM matches WHERE id=?', (room_id,)).fetchone()
            status = "aborted" if reason == "disconnect_timeout" else ("finished" if row and row['status'] == 'playing' else "cancelled")
            db.execute("UPDATE matches SET status=?, start_at=NULL, updated_at=? WHERE id=?", (status, utcnow(), room_id))
            db.execute("UPDATE invitations SET status='cancelled', responded_at=? WHERE match_id=? AND status='pending'", (utcnow(), room_id))
        sockets = list(self.connections.pop(room_id, {}).values())
        await asyncio.gather(*(self._send(socket, {"type": "room_closed", "message": reason, "reason": reason, "code": reason}) for socket in sockets))
        async def close(socket):
            try:
                await asyncio.wait_for(socket.close(code=1000), timeout=2)
            except Exception:
                pass
        await asyncio.gather(*(close(socket) for socket in sockets))

    async def dissolve(self, room_id, user_id, action):
        async with self.lock:
            await self._dissolve_for_player(room_id, user_id, action)

    async def detach(self, room_id, user_id, socket):
        async with self.lock:
            # A rejected duplicate connection must never evict the original player.
            if self.connections.get(room_id, {}).get(user_id) is socket:
                self._disconnect(room_id, user_id, socket)
                await self._broadcast(room_id)

    def _disconnect(self, room_id, user_id, socket):
        if self.connections.get(room_id, {}).get(user_id) is not socket:
            return
        self.connections[room_id].pop(user_id, None)
        from app.storage.db import connect
        with connect() as db:
            db.execute("UPDATE matches SET status='waiting',start_at=NULL WHERE id=? AND status='countdown'", (room_id,))
        self._cancel_countdown(room_id)
        key = (room_id, user_id)
        if key not in self.disconnects:
            self.disconnects[key] = asyncio.create_task(self._disconnect_timeout(room_id,user_id))

    async def _disconnect_timeout(self, room_id, user_id):
        try:
            await asyncio.sleep(self.disconnect_seconds)
            async with self.lock:
                if user_id not in self.connections.get(room_id, {}):
                    await self._dissolve(room_id, 'disconnect_timeout')
        except asyncio.CancelledError:
            pass
        finally:
            key = (room_id, user_id)
            if self.disconnects.get(key) is asyncio.current_task():
                self.disconnects.pop(key, None)

    async def start(self, room_id, user_id):
        from app.storage.db import connect, utcnow
        from app.core.match_repository import member_match, snapshot
        from app.auth import fail
        async with self.lock:
            with connect() as db:
                row=member_match(db,room_id,user_id)
                if row['host_id']!=user_id: fail(403,'host_required','仅房主可以开局')
                if row['status'] not in ('inviting','waiting'): fail(409,'roster_locked','对局已经开始')
                room=snapshot(db,room_id)
                if room['human_count']<2: fail(409,'not_enough_players','至少需要两位真人')
                if not all(p['ready'] for p in room['players']): fail(409,'not_ready','请等待所有玩家准备')
                deadline=time.time()+self.countdown_seconds
                db.execute("UPDATE invitations SET status='cancelled',responded_at=? WHERE match_id=? AND status='pending'",(utcnow(),room_id))
                db.execute("UPDATE matches SET status='countdown',start_at=?,updated_at=? WHERE id=?",(deadline*1000,utcnow(),room_id))
            self.roster_locked.add(room_id)
            self._cancel_countdown(room_id)
            self.countdowns[room_id]=asyncio.create_task(self._start_after(room_id,deadline))

    async def _leave(self, room_id, user_id):
        from app.storage.db import connect, utcnow
        from app.core.match_repository import member_match, ACTIVE
        from app.auth import fail
        with connect() as db:
            row=member_match(db,room_id,user_id)
            if row['status'] not in ACTIVE:
                fail(409, 'match_ended', '对局已结束')
            dissolve=row['host_id']==user_id or row['status']=='playing'
            if not dissolve:
                db.execute('DELETE FROM match_members WHERE match_id=? AND user_id=?',(room_id,user_id))
                db.execute("UPDATE matches SET status='waiting',start_at=NULL,updated_at=? WHERE id=?",(utcnow(),room_id))
        if dissolve:
            await self._dissolve_for_player(room_id,user_id,'退出')
        else:
            self._cancel_countdown(room_id)
            task=self.disconnects.pop((room_id,user_id),None)
            if task: task.cancel()
            socket=self.connections.get(room_id,{}).pop(user_id,None)
            if socket:
                await self._send(socket,{'type':'room_closed','message':'你已离开对局'})
                await socket.close(code=1000)
            await self._broadcast(room_id)

    async def leave(self, room_id, user_id):
        async with self.lock:
            await self._leave(room_id,user_id)
