"""Authoritative PvP hand state. No EV, threat model or hidden-hand data in client views."""
import time
from copy import deepcopy
from collections import Counter
from uuid import uuid4

from fastapi import HTTPException
from app.schemas import Meld
from app.core.action_generator import get_available_actions, detect_self_gang_actions
from app.core.deck_engine import setup_new_game
from app.core.evaluator import check_self_drawn_win, check_ron_win
from app.core.settlement import calculate_final_settlement
from app.core.scoring import calculate_unwon_player_points
from app.core.pvp_records import scoring_groups

WINDS = "ESWN"


class PvpMatch:
    def __init__(self, players, opening_seconds=3.6, deal=None, *, dealer_seat="E", hand_number=1, circle_number=1, scores=None, now_ms=None):
        self.now_ms = now_ms or (lambda: time.time() * 1000)
        self.dealer_seat = dealer_seat
        self.hand_number = hand_number
        self.circle_number = circle_number
        self.scores = dict(scores or {seat: 0 for seat in WINDS})
        self.next_ready = set()
        self.clocks = {}
        self.time_banks = {wind: 30000 for wind in WINDS}
        self.players = {p["seat_wind"]: dict(p) for p in players}
        self.deal = deal or setup_new_game(dealer_seat)
        self.hands = {wind: list(self.deal["hands"][wind]) for wind in WINDS}
        self.wall = list(self.deal["wall_tiles"])
        self.melds = {wind: [] for wind in WINDS}
        self.rivers = {wind: [] for wind in WINDS}
        self.game_id = f"GM-{uuid4().hex[:12].upper()}"
        self.god = self.deal["dealer_tile"]
        self.current = dealer_seat
        self.phase = "opening"
        self.opening_at = self.now_ms()
        self.opening_ends_at = self.opening_at + opening_seconds * 1000
        self.opening_ready = {seat for seat in WINDS if self.players[seat]["is_ai"]}
        self.revision = 0
        self.turns = 0
        self.drawn = {wind: None for wind in WINDS}
        self.drawn[dealer_seat] = self.hands[dealer_seat][-1]
        self.options = {wind: [] for wind in WINDS}
        self.pending = {}
        self.choices = {}
        self.last_discard = None
        self.pending_kong = None
        self.response_started_at = None
        self.result = None
        self.event = None
        self.history = []
        self.full_settlement = None
        self.archived = False

    def _event(self, action, seat, tile=None, is_zimo=False, concealed=False):
        self.event = {"id": self.revision + 1, "action": action, "seat": seat, "tile": tile, "isZimo": is_zimo, "concealed": concealed}

    def _models(self, seat):
        return [Meld.model_validate(m) for m in self.melds[seat]]

    def begin(self):
        if self.phase != "opening":
            return
        self.phase = "discard"
        self._turn_options()
        self._refresh_clocks()
        self.revision += 1

    def acknowledge_opening(self, seat, game_id):
        if game_id != self.game_id:
            raise HTTPException(409, "财神仪式不属于当前牌局")
        self.opening_ready.add(seat)

    def _win_info(self, seat, tile=None, zimo=False):
        if zimo:
            return check_self_drawn_win(self.hands[seat], self._models(seat), self.god, seat, is_dealer=seat == self.dealer_seat, win_tile=self.drawn[seat])
        return check_ron_win(self.hands[seat], self._models(seat), tile, self.god, seat, is_dealer=seat == self.dealer_seat)

    @staticmethod
    def _brief(info):
        return {"final_hu": info["final_hu"], "is_lazi": info["final_hu"] >= 100} if info else None

    def _turn_options(self):
        self.options = {wind: [] for wind in WINDS}
        seat = self.current
        rows = [{"action_type": "discard", "tiles": [tile]} for tile in dict.fromkeys(self.hands[seat])]
        if self.drawn[seat]:
            win = self._win_info(seat, zimo=True)
            if win:
                rows.append({"action_type": "self_draw_win", "tiles": [self.drawn[seat]], "hu_info": self._brief(win)})
        rows.extend(a.to_dict() for a in detect_self_gang_actions(self.hands[seat], self._models(seat), self.god))
        self.options[seat] = self._identify(rows)

    def _identify(self, rows):
        return [{**row, "action_id": f"{self.revision + 1}:{index}"} for index, row in enumerate(rows)]

    def act(self, seat, message, *, automatic=False):
        if message.get("game_id") != self.game_id or message.get("revision") != self.revision:
            raise HTTPException(409, "牌局已更新，请按当前牌面操作")
        if self.phase not in ("discard", "response"):
            raise HTTPException(409, "当前还不能行牌")
        selected = next((a for a in self.options[seat] if a["action_id"] == message.get("action_id")), None)
        if selected is None:
            raise HTTPException(403, "此操作不属于你的合法动作")
        clock = self.clocks.get(seat)
        if not automatic and clock and clock["deadline"] is not None and self.now_ms() >= clock["deadline"] + self.time_banks[seat]:
            raise HTTPException(409, "操作已超时，正在自动处理")
        if not automatic and clock and clock["paused"] and selected["action_type"] != "pass":
            raise HTTPException(409, "等待其他玩家的碰杠或胡牌优先响应")
        self._stop_clock(seat)
        kind = selected["action_type"]
        self.history.append({"at": self.now_ms(), "seat": seat, "action": kind, "tiles": list(selected.get('tiles', [])), "automatic": automatic})
        if self.phase == "response":
            self.choices[seat] = selected
            self.options[seat] = []
            self._maybe_resolve_responses()
        elif kind == "discard":
            self._discard(seat, selected["tiles"][0])
        elif kind == "self_draw_win":
            self._finish_win(seat, self.drawn[seat], "zimo")
        else:
            self._self_kong(seat, selected)
        self.revision += 1
        self._refresh_clocks()

    @staticmethod
    def _priority(row):
        return {"hu": 3, "ming_gang": 2, "pong": 2, "chi": 1, "pass": 0}[row["action_type"]]

    def _maybe_resolve_responses(self):
        """Do not wait for an irrelevant lower-priority claim after an interrupt wins."""
        provider = self.last_discard["seat"]
        def rank(seat, row):
            return (-self._priority(row), (WINDS.index(seat) - WINDS.index(provider)) % 4)
        claims = [(seat, row) for seat, row in self.choices.items() if self._priority(row)]
        if claims:
            best = min(rank(seat, row) for seat, row in claims)
            if any(rank(seat, row) < best for seat in self.pending if seat not in self.choices for row in self.options[seat]):
                return
            self._resolve_responses()
        elif all(seat in self.choices for seat in self.pending):
            self._resolve_responses()

    def bank_remaining(self, seat, now=None):
        """Snapshot a running bank without resetting its accounting origin."""
        clock = self.clocks.get(seat)
        elapsed = 0 if not clock or clock["paused"] else max(0, (self.now_ms() if now is None else now) - clock["deadline"])
        return max(0, self.time_banks[seat] - elapsed)

    def _stop_clock(self, seat):
        self.time_banks[seat] = self.bank_remaining(seat)
        return self.clocks.pop(seat, None)

    def _refresh_clocks(self):
        now = self.now_ms()
        active = {}
        for seat, rows in self.options.items():
            if not rows or self.phase not in ("discard", "response"):
                self._stop_clock(seat)
                continue
            is_win = any(row["action_type"] in ("hu", "self_draw_win") for row in rows)
            duration = 6000 if self.phase == "response" or is_win else 10000
            paused = self.phase == "response" and not is_win and any(row["action_type"] == "chi" for row in rows) and not any(row["action_type"] in ("pong", "ming_gang") for row in rows) and any(
                row["action_type"] in ("hu", "pong", "ming_gang") for other in self.pending if other != seat and other not in self.choices for row in self.options[other]
            )
            token = (self.phase, tuple(row["action_id"] for row in rows))
            clock = self.clocks.get(seat)
            if not clock or clock["token"] != token:
                self._stop_clock(seat)
                clock = {"token": token, "remaining_ms": duration, "deadline": None if paused else now + duration, "paused": paused, "kind": "win" if is_win else self.phase,
                         "started_at": now, "ai_remaining_ms": 3000 if self.phase == "response" or is_win else 6000,
                         "ai_decision_at": None if paused else now + (3000 if self.phase == "response" or is_win else 6000)}
            elif paused and not clock["paused"]:
                self.time_banks[seat] = self.bank_remaining(seat, now)
                clock["remaining_ms"] = max(0, clock["deadline"] - now)
                clock["ai_remaining_ms"] = max(0, clock["ai_decision_at"] - now)
                clock["deadline"] = None
                clock["ai_decision_at"] = None
                clock["paused"] = True
            elif not paused and clock["paused"]:
                clock["deadline"] = now + clock["remaining_ms"]
                clock["ai_decision_at"] = now + clock["ai_remaining_ms"]
                clock["paused"] = False
            active[seat] = clock
        self.clocks = active

    def tick(self):
        """Server-only expiry. Recompute after each action; new turns get full time."""
        changed = False
        for _ in range(4):
            expired = next((seat for seat, clock in self.clocks.items() if clock["deadline"] is not None and self.now_ms() >= clock["deadline"] + self.time_banks[seat]), None)
            if expired is None:
                break
            rows = self.options[expired]
            choice = next((row for row in rows if row["action_type"] in ("hu", "self_draw_win")), None)
            if choice is None and self.phase == "response":
                choice = next(row for row in rows if row["action_type"] == "pass")
            if choice is None:
                tile = self.drawn[expired] or self.hands[expired][-1]
                choice = next(row for row in rows if row["action_type"] == "discard" and row["tiles"][0] == tile)
            self.act(expired, {"game_id": self.game_id, "revision": self.revision, "action_id": choice["action_id"]}, automatic=True)
            changed = True
        return changed

    def confirm_next(self, seat, game_id):
        if self.phase != "finished" or game_id != self.game_id:
            raise HTTPException(409, "请等待本局结算后确认")
        if seat not in self.next_ready:
            self.next_ready.add(seat)
            self.revision += 1
        return all(wind in self.next_ready for wind in WINDS if not self.players[wind]["is_ai"])

    @property
    def next_dealer(self):
        if self.result and self.result.get("winner_seat") == self.dealer_seat:
            return self.dealer_seat
        return WINDS[(WINDS.index(self.dealer_seat) + 1) % 4]

    @property
    def circle_complete(self):
        return self.phase == "finished" and self.dealer_seat == "N" and self.next_dealer == "E"

    def _discard(self, seat, tile):
        self.hands[seat].remove(tile)
        self.drawn[seat] = None
        self.rivers[seat].append(tile)
        self.last_discard = {"seat": seat, "tile": tile}
        self.turns += 1
        self._event("DISCARD", seat, tile)
        self.pending_kong = None
        self._responses(seat, tile)

    def _responses(self, provider, tile, rob_kong=False):
        self.response_started_at = self.now_ms()
        self.options = {wind: [] for wind in WINDS}
        self.pending, self.choices = {}, {}
        for seat in WINDS:
            if seat == provider:
                continue
            rows = [a.to_dict() for a in get_available_actions(self.hands[seat], self._models(seat), tile, provider, seat, self.god)]
            if rob_kong:
                rows = [row for row in rows if row["action_type"] in ("hu", "pass")]
            if not any(row["action_type"] != "pass" for row in rows):
                continue
            for row in rows:
                if row["action_type"] == "hu":
                    row["hu_info"] = self._brief(self._win_info(seat, tile))
            self.pending[seat] = rows
            self.options[seat] = self._identify(rows)
        if self.pending:
            self.phase = "response"
        elif rob_kong:
            self._complete_add_kong()
        else:
            self._draw(WINDS[(WINDS.index(provider) + 1) % 4])

    def _resolve_responses(self):
        provider, tile = self.last_discard["seat"], self.last_discard["tile"]
        priority = {"hu": 3, "ming_gang": 2, "pong": 2, "chi": 1, "pass": 0}
        selected = [(seat, row) for seat, row in self.choices.items() if row["action_type"] != "pass"]
        selected.sort(key=lambda entry: (-priority[entry[1]["action_type"]], (WINDS.index(entry[0]) - WINDS.index(provider)) % 4))
        self.pending, self.choices = {}, {}
        if selected:
            seat, action = selected[0]
            kind = action["action_type"]
            if kind == "hu":
                if self.pending_kong:
                    # The added physical tile belongs to the robbed win, not the old pong.
                    self.hands[provider].remove(tile)
                    self.rivers[provider].append(tile)
                self._finish_win(seat, tile, "rob_kong" if self.pending_kong else "ron", provider)
                return
            needed = list(action["tiles"])
            needed.remove(tile)
            for physical in needed:
                self.hands[seat].remove(physical)
            self.rivers[provider].pop()
            self.melds[seat].append({"meld_type": kind, "tiles": list(action["tiles"]), "claimed_tile": tile, "provider_seat": provider})
            self.current = seat
            self.drawn[seat] = None
            self._event({"chi": "CHI", "pong": "PONG", "ming_gang": "GANG"}[kind], seat, tile)
            if kind == "ming_gang":
                self._draw(seat, replacement=True)
            else:
                self.phase = "discard"
                self._turn_options()
        elif self.pending_kong:
            self._complete_add_kong()
        else:
            self._draw(WINDS[(WINDS.index(provider) + 1) % 4])

    def _self_kong(self, seat, action):
        tile = action["tiles"][0]
        if action["action_type"] == "bu_gang":
            self.pending_kong = {"seat": seat, "tile": tile}
            self.last_discard = {"seat": seat, "tile": tile, "rob_kong": True}
            self._responses(seat, tile, rob_kong=True)
            return
        for _ in range(4):
            self.hands[seat].remove(tile)
        self.melds[seat].append({"meld_type": "an_gang", "tiles": [tile] * 4})
        self._event("GANG", seat, tile, concealed=True)
        self._draw(seat, replacement=True)

    def _complete_add_kong(self):
        seat, tile = self.pending_kong["seat"], self.pending_kong["tile"]
        self.hands[seat].remove(tile)
        meld = next(m for m in self.melds[seat] if m["meld_type"] == "pong" and m["tiles"][0] == tile)
        meld["meld_type"] = "ming_gang"
        meld["tiles"].append(tile)
        self.pending_kong = None
        self._event("GANG", seat, tile)
        self._draw(seat, replacement=True)

    def _draw(self, seat, replacement=False):
        self.pending, self.choices = {}, {}
        self.current = seat
        if not self.wall:
            self.phase = "finished"
            self.options = {wind: [] for wind in WINDS}
            details = {}
            for wind in WINDS:
                inherent = calculate_unwon_player_points(hand_tiles=self.hands[wind], melds=self._models(wind), seat_wind=wind, dealer_tile=self.god)
                details[wind] = {"net": 0, "is_dealer": wind == self.dealer_seat, "hand_tiles": [], "melds": [], "inherent": inherent, "scoring_groups": scoring_groups(inherent, self.hands[wind], self.god)}
            # Preserve the existing zero-payment PvP draw behavior.
            self.result = {"kind": "draw", "is_draw": True, "label": "荒牌流局", "game_id": self.game_id, "dealer_tile": self.god, "seat_details": details, "net_by_seat": dict.fromkeys(WINDS, 0)}
            self.full_settlement = deepcopy(self.result)
            return
        tile = self.wall.pop(-1 if replacement else 0)
        self.hands[seat].append(tile)
        self.drawn[seat] = tile
        self.phase = "discard"
        self._turn_options()

    def _finish_win(self, seat, tile, kind, provider=None):
        remain = list(self.hands[seat])
        if kind == "zimo":
            remain.remove(tile)
        players = [{"seat_wind": wind, "is_dealer": wind == self.dealer_seat, "hand_tiles": list(self.hands[wind]), "melds": self.melds[wind]} for wind in WINDS]
        settlement = calculate_final_settlement(winner_seat=seat, win_type=kind, dealer_tile=self.god, players=players, hand_tiles=remain, melds=self.melds[seat], win_tile=tile, discarder_seat=provider)
        self.full_settlement = deepcopy(settlement)
        self.result = deepcopy(settlement)
        self.result.update(kind="win", win_type=kind, label=settlement["win_type_label"], game_id=self.game_id, win_tile=tile)
        for wind, detail in self.result['seat_details'].items():
            if wind != seat:
                detail['scoring_groups'] = scoring_groups(detail['inherent'], self.hands[wind], self.god)
                detail['hand_tiles'] = []
                detail['melds'] = []
        for wind in WINDS:
            self.scores[wind] += settlement["net_by_seat"][wind]
        self.phase = "finished"
        self.options = {wind: [] for wind in WINDS}
        self._event("WIN", seat, tile, kind == "zimo")

    def archive_record(self):
        return {"game_id": self.game_id, "phase": self.phase, "players": list(self.players.values()), "initial_deal": deepcopy(self.deal), "dealer_seat": self.dealer_seat, "hand_number": self.hand_number, "circle_number": self.circle_number, "steps": deepcopy(self.history), "result": deepcopy(self.full_settlement or self.result), "final_hands": deepcopy(self.hands), "melds": deepcopy(self.melds), "rivers": deepcopy(self.rivers), "scores": dict(self.scores)}

    def bot_action(self, *, ready_only=False):
        for seat in WINDS:
            rows = self.options[seat]
            if not self.players[seat]["is_ai"] or not rows:
                continue
            clock = self.clocks.get(seat)
            if clock and clock["paused"]:
                continue
            if ready_only and (not clock or self.now_ms() < clock["ai_decision_at"]):
                continue
            win = next((a for a in rows if a["action_type"] in ("hu", "self_draw_win")), None)
            if win:
                return seat, win
            if self.phase == "response":
                return seat, next((a for a in rows if a["action_type"] in ("ming_gang", "pong")), next(a for a in rows if a["action_type"] == "pass"))
            kong = next((a for a in rows if a["action_type"] in ("an_gang", "bu_gang")), None)
            if kong:
                return seat, kong
            # Hand-local retention heuristic; never inspects another concealed hand.
            counts = Counter(self.hands[seat])
            def retain(action):
                tile = action["tiles"][0]
                if tile == self.god:
                    return 100
                value = (counts[tile] - 1) * 12
                face = self.god if tile == "P" and self.god != "P" else tile
                if len(face) == 2:
                    rank, suit = int(face[0]), face[1]
                    value += 4 - abs(5 - rank)
                    for delta, weight in [(-2, 2), (-1, 5), (1, 5), (2, 2)]:
                        value += counts.get(f"{rank + delta}{suit}", 0) * weight
                elif face in (seat, "C", "F", "P"):
                    value += 2
                return value
            return seat, min((a for a in rows if a["action_type"] == "discard"), key=retain)
        return None

    def view(self, seat):
        players = []
        for wind in WINDS:
            # Kong identities are public; the shared UI draws three backs and one face.
            melds = [{**m, "tiles": list(m["tiles"])} for m in self.melds[wind]]
            players.append({**self.players[wind], "hand_count": len(self.hands[wind]), "melds": melds, "discards": list(self.rivers[wind])})
        event = dict(self.event) if self.event else None
        now = self.now_ms()
        banks = {wind: self.bank_remaining(wind, now) for wind in WINDS}
        clocks = {}
        for wind, clock in self.clocks.items():
            # Responding rights and clock suspension are private hand information.
            if self.phase == 'response' and wind != seat:
                continue
            bank = not clock["paused"] and now >= clock["deadline"]
            clocks[wind] = {key: value for key, value in clock.items() if key not in ("token", "ai_decision_at", "ai_remaining_ms")}
            clocks[wind].update(stage="bank" if bank else "regular", bank_remaining_ms=banks[wind],
                                regular_deadline=clock["deadline"], bank_deadline=None if clock["paused"] else clock["deadline"] + self.time_banks[wind],
                                regular_remaining_ms=clock["remaining_ms"] if clock["paused"] else max(0, clock["deadline"] - now),
                                deadline=clock["deadline"] + self.time_banks[wind] if bank else clock["deadline"],
                                remaining_ms=banks[wind] if bank else clock["remaining_ms"])
        # Never expose hidden claim spending via per-seat bank changes, even after a pass.
        banks = {wind: balance if wind == seat or self.phase == 'discard' and wind == self.current else None for wind, balance in banks.items()}
        response_wait = {'started_at': self.response_started_at, 'deadline': self.response_started_at + 6000, 'remaining_ms': 6000} if self.phase == 'response' else None
        return {"game_id": self.game_id, "revision": self.revision, "dealer_tile": self.god, "dealer_seat": self.dealer_seat, "current_turn": self.current, "wall_count": len(self.wall), "hand_counts": {wind: len(self.hands[wind]) for wind in WINDS}, "hand_tiles": list(self.hands[seat]), "drawn_tile": self.drawn[seat], "seat_wind": seat, "players": players, "phase": self.phase, "opening_at": self.opening_at, "opening_ends_at": self.opening_ends_at, "turn_count": self.turns // 4 + 1, "actions": self.options[seat], "last_discard": self.last_discard, "result": self.result, "event": event, "clocks": clocks, "time_banks": banks, "response_wait": response_wait, "hand_number": self.hand_number, "circle_number": self.circle_number, "scores": dict(self.scores), "next_ready": list(self.next_ready), "circle_complete": self.circle_complete}
