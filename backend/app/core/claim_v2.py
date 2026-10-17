"""V2 claim experiment. Shared waiting-state value for PASS/CHI/PONG/KONG.

Installed only into an isolated policy graph. Historical V0/V1 and the live
service keep their original implementation until V2 is explicitly activated.
Scores are heuristic EV units (8-tile reference), not calibrated money EV.
"""
import math
from .action_generator import ActionType, get_legal_turn_actions

BOUNDS = {
    'redundant_chow_penalty': (45., 60.),
    'no_advance_chow_penalty': (15., 22.),
    'claim_to_tenpai_reward': (35., 45.),
    'pung_value_incentive': (0.8, 1.25),
    'kong_risk_reward_factor': (0.9, 1.1),
}
DEFAULTS = dict(zip(BOUNDS, (55., 18., 40., 1., 1.)))


def validate_claim_weights(values):
    if set(values) != set(BOUNDS):
        raise ValueError('Missing/unknown claim weight')
    for key, (low, high) in BOUNDS.items():
        value = values[key]
        if type(value) not in (float, int) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError('Invalid claim weight: ' + key)
    return values


class ClaimEvaluator:
    def __init__(self, ev, legacy, weights):
        self.ev, self.legacy = ev, legacy
        self.weights = dict(validate_claim_weights(weights))
        self.discards = ev.calculate_best_discards

    def remaining(self, hand, melds, river, opponents, god):
        public = [t for m in melds for t in m.tiles]
        public += [t for o in opponents for m in o.melds for t in m.tiles]
        return self.ev._build_rem_map(hand, river, public, god)

    def waiting(self, hand, melds, god, seat, dealer, rem, round_wind='E'):
        """One formula for every waiting state; no imaginary discard rewards.

        Near/far shanten use the same V1 approximation and penalty in all
        branches. Winning tiles use actual scoring (including hard-hu), with
        the same 8-tile denominator. No separate PASS hard-hu discount.
        """
        e = self.ev
        shanten = int(e.check_win_or_shanten(e.preprocess_hand(hand, god), 0, 4-len(melds)))
        ukeire = e._collect_ukeire(hand, rem, god, seat, dealer, 4-len(melds), melds, light=shanten > 0)
        count = sum(u['rem'] for u in ukeire)
        if shanten == 0:
            attack = sum(u['rem'] * u['est_win_points'] for u in ukeire) / e._TENPAI_RYANMEN_BASELINE
        else:
            quality = e._deep_quality_ukeire_count(hand, ukeire, god, seat_wind=seat, round_wind=round_wind, shanten=shanten)
            attack = (quality * e._UKEIRE_QUALITY_WEIGHT + e._shape_quality_score(hand, god)
                      + e._yakuhai_potential_score(hand, god, seat, rem, round_wind)
                      + e._substitute_honor_keep_bonus(hand, god, rem)
                      - e._guest_wind_hold_penalty(hand, god, seat, rem, round_wind)
                      - max(0, shanten) * e._DEEP_SHANTEN_UNIT)
        return dict(value=attack-max(0, shanten)*e.SHANTEN_PENALTY,
                    shanten=shanten, count=count, ukeire=ukeire)

    @staticmethod
    def dominated(before, after, same_tile=False):
        """Hard guard independent of tunable penalties, including their minima."""
        if after['shanten'] > before['shanten']:
            return True
        if after['shanten'] != before['shanten']:
            return False
        # Same-tile return cannot earn a tempo bonus or improve concealed options.
        if same_tile:
            return True
        if before['shanten'] == 0:
            old = {u['tile']: u for u in before['ukeire']}
            no_gain = after['count'] <= before['count'] and after['value'] <= before['value']
            return no_gain or all(u['tile'] in old and u['rem'] <= old[u['tile']]['rem']
                       and u['est_win_points'] <= old[u['tile']]['est_win_points']
                       for u in after['ukeire'])
        return after['count'] <= before['count'] and after['value'] <= before['value']

    def after_discard(self, hand, melds, god, seat, dealer, river, opponents, round_wind, rem=None):
        """Follow the actual frozen V1 discard policy, then value its end state."""
        rem = rem if rem is not None else self.remaining(hand, melds, river, opponents, god)
        result = self.discards(hand, god, dealer, seat, discarded_tiles=river, melds=melds,
                               opponents=opponents, rem_tiles=rem, include_self_gang=False, round_wind=round_wind)
        cut = result['candidates'][0]
        after = list(hand); after.remove(cut['tile'])
        state = self.waiting(after, melds, god, seat, dealer, rem, round_wind)
        return state['value']-cut['defense_loss'], state, cut

    @staticmethod
    def unchanged_waits(before, after):
        def signature(state):
            return sorted((u['tile'], u['rem'], u['est_base_points'],
                           u['est_final_points'], u['est_win_points'], u['is_hard_hu'])
                          for u in state['ukeire'])
        return (before['shanten'] == after['shanten'] == 0
                and signature(before) == signature(after))

    def filter_actions(self, actions, before, previews, disc, god):
        """Policy eligibility only: never change authoritative/manual legality.

        Keep rejected evaluations as -inf audit rows, but remove them from the
        decision's available_actions before evaluating any tunable reward.
        """
        eligible, rejected = [], []
        for action in actions:
            preview = previews.get(id(action))
            if action.action_type == ActionType.CHI and preview:
                _, after, cut = preview
                same = self.ev._logical_tile(cut['tile'], god) == self.ev._logical_tile(disc, god)
                if same and self.unchanged_waits(before, after):
                    rejected.append(action)
                    continue
            eligible.append(action)
        return eligible, rejected

    def kong(self, hand, melds, god, seat, dealer, river, opponents, round_wind, rem=None):
        """All possible replacement draws, weighted by the SAME unseen pool.

        No truncated top-tile sample or unconditional kong-over-pong floor.
        Kong meld points are already present in the scorer; do not add again.
        """
        e = self.ev
        rem = rem if rem is not None else self.remaining(hand, melds, river, opponents, god)
        total = sum(rem.values())
        if not total:
            return self.waiting(hand, melds, god, seat, dealer, rem, round_wind)['value']
        reward = risk = 0.
        for tile, count in rem.items():
            if count <= 0:
                continue
            trial = hand+[tile]
            if e.check_win_or_shanten(e.preprocess_hand(trial, god), 0, 4-len(melds)) == -1:
                hu = e._best_hu_points(melds=melds, hand_tiles=hand, win_tile=tile, seat_wind=seat, dealer_tile=god)
                value = float(hu['final_hu']) * e._settlement_factor(dealer)
                loss = 0.
            else:
                next_rem = dict(rem); next_rem[tile] -= 1
                value, state, cut = self.after_discard(trial, melds, god, seat, dealer, river, opponents, round_wind, next_rem)
                loss = cut['defense_loss']; value += loss
            reward += count*value/total
            risk += count*loss/total
        # Vary risk aversion only, never multiply negative/positive future values.
        return reward-self.weights['kong_risk_reward_factor']*risk

    def evaluate(self, available_actions, hand_tiles, melds, opponents, dealer_tile,
                 seat_wind, round_wind, is_dealer, *, discarded_tile=None,
                 discarded_tiles=None, turn_count=None):
        c, e, w = self.legacy, self.ev, self.weights
        actions = list(available_actions); melds = list(melds); opponents = list(opponents)
        disc = discarded_tile or c._infer_discarded_tile(actions)
        river = list(discarded_tiles or [])
        if disc not in river: river.append(disc)
        rem = self.remaining(hand_tiles, melds, river, opponents, dealer_tile)
        before = self.waiting(hand_tiles, melds, dealer_tile, seat_wind, is_dealer, rem, round_wind)
        # The same next normal draw is represented by waiting() in every branch.
        # PASS alone retains the imminent turn skipped by CHI/PONG (also in tenpai).
        # waiting() already includes tenpai draw opportunities via Rem/8. Giving
        # an extra fixed draw credit to an already-tenpai PASS double counts it.
        draw_credit = (c._PASS_DRAW_TURN_BASE + min(before['count'], c._PASS_DRAW_UKEIRE_CAP)*c._PASS_DRAW_UKEIRE_SCALE) if before['shanten'] > 0 else 0.
        pass_ev = before['value'] + draw_credit
        previews = {}
        for action in actions:
            if action.action_type == ActionType.CHI:
                hand, new_melds = c._apply_meld_action(hand_tiles, melds, action, disc)
                previews[id(action)] = self.after_discard(hand, new_melds, dealer_tile, seat_wind, is_dealer, river, opponents, round_wind, rem)
        actions, rejected = self.filter_actions(actions, before, previews, disc, dealer_tile)
        scores = [c.CallActionScore(a, float('-inf'), '硬过滤：原样打回且听口/胡数不变') for a in rejected]
        for action in actions:
            kind = action.action_type
            if kind == ActionType.PASS:
                scores.append(c.CallActionScore(action, pass_ev, '统一待摸估值 + 保留下次摸牌机会', pass_ev=pass_ev)); continue
            if kind == ActionType.HU:
                # Preserve immediate legal HU priority used by the arena.
                hu = e._best_hu_points(melds=melds, hand_tiles=hand_tiles, win_tile=disc, seat_wind=seat_wind, dealer_tile=dealer_tile)
                income = float(hu['final_hu'])*e._settlement_factor(is_dealer)
                scores.append(c.CallActionScore(action, income, '即时和牌', hu_ev=income)); continue
            if kind not in (ActionType.CHI, ActionType.PONG, ActionType.MING_GANG):
                continue
            hand, new_melds = c._apply_meld_action(hand_tiles, melds, action, disc)
            # River -> meld transfer leaves the number of unseen tiles unchanged.
            if kind == ActionType.MING_GANG:
                value = self.kong(hand, new_melds, dealer_tile, seat_wind, is_dealer, river, opponents, round_wind, rem)
                note = '全进张岭上加权；杠胡已入计分，不重复奖励'
            else:
                value, after, cut = previews[id(action)] if id(action) in previews else self.after_discard(hand, new_melds, dealer_tile, seat_wind, is_dealer, river, opponents, round_wind, rem)
                note = f"统一尺度；切 {cut['tile']}；向听 {before['shanten']}→{after['shanten']}"
                if before['shanten'] > 0 and after['shanten'] == 0:
                    value += w['claim_to_tenpai_reward']*min(1., after['count']/4.)
                if kind == ActionType.CHI:
                    redundant = c.is_redundant_complete_sequence_chi(hand_tiles, disc, action.tiles, dealer_tile)
                    if redundant: value -= w['redundant_chow_penalty']
                    if after['shanten'] >= before['shanten']: value -= w['no_advance_chow_penalty']
                    same = e._logical_tile(cut['tile'], dealer_tile) == e._logical_tile(disc, dealer_tile)
                    if self.dominated(before, after):
                        value = min(value, pass_ev-max(1., w['redundant_chow_penalty']))
                        note += '；冗余/倒退吃牌守护：严格劣于过牌'
                elif after['shanten'] > 0:
                    # Only approximate non-tenpai valuation needs a fixed-meld credit.
                    # Tenpai scoring already includes the actual pung, fans and hard-hu.
                    terminal = c._is_terminal_or_honor(e._logical_tile(disc, dealer_tile))
                    hu = c.PONG_TERMINAL_HONOR_HU if terminal else c.PONG_SIMPLE_HU
                    value += hu*w['pung_value_incentive']*e._settlement_factor(is_dealer)
            scores.append(c.CallActionScore(action, value, note))
        best = next((s for s in scores if s.action.action_type == ActionType.HU), None)
        best = best or max(scores, key=lambda s:s.net_ev)
        class FilteredResponse(c.CallDecisionResponse):
            def to_dict(self):
                result = super().to_dict()
                result['available_actions'] = [a.to_dict() for a in actions]
                return result
        return FilteredResponse(best.action, best.note, sorted(scores,key=lambda s:s.net_ev,reverse=True), pass_ev=pass_ev)


def install(modules, weights):
    evaluator = ClaimEvaluator(modules['ev_engine'], modules['call_decision'], weights)
    modules['call_decision'].evaluate_call_decision = evaluator.evaluate
    modules['call_evaluator_v2'] = evaluator
    # Self kong uses the same replacement-draw evaluator and no forced bu-gang.
    def discard_policy(*args, **kwargs):
        include = kwargs.get('include_self_gang', True)
        kwargs['include_self_gang'] = False
        result = evaluator.discards(*args, **kwargs)
        if not include: return result
        import inspect
        bound = inspect.signature(evaluator.discards).bind(*args, **kwargs)
        bound.apply_defaults(); k = bound.arguments
        hand=k['hand_tiles']; melds=list(k['melds'] or []); god=k['dealer_tile']
        river=list(k['discarded_tiles'] or []); opponents=list(k['opponents'] or [])
        rem=evaluator.remaining(hand,melds,river,opponents,god)
        common=(god,k['seat_wind'],k['is_dealer'],river,opponents,k['round_wind'])
        best,_,_=evaluator.after_discard(hand,melds,*common,rem)
        for action in get_legal_turn_actions(hand,melds,god):
            if action.action_type not in (ActionType.AN_GANG,ActionType.BU_GANG):continue
            nh,nm,_,_=modules['ev_engine']._apply_self_gang_for_eval(hand,melds,action,god)
            score=evaluator.kong(nh,nm,*common,rem)
            if action.action_type == ActionType.BU_GANG:
                # Conservative public-information rob-kong risk, not hidden hands.
                probs=modules['tenpai_model'].estimate_opponents_tenpai(opponents,dealer_tile=god,rem_map=rem)
                risk=sum(probs.get(o.seat_wind,0)*modules['danger_model'].estimate_tile_danger(action.tiles[0],o,rem,god,hand_tiles=hand)*modules['ev_engine']._build_opponent_threat(o,god,k['is_dealer'])['loss_ron'] for o in opponents)
                score -= evaluator.weights['kong_risk_reward_factor']*risk
            result['self_gang_candidates'].append({'action_type':action.action_type.value,
                'tile':action.tiles[0],'tiles':list(action.tiles),'ev_score':score,
                'note':'V2 统一岭上估值（补杠含公开抢杠风险）'})
            if score > best:
                best=score;result['best_action']={'action_type':action.action_type.value,'tile':action.tiles[0],'ev_score':score}
        return result
    modules['ev_engine'].calculate_best_discards = discard_policy
    return evaluator
