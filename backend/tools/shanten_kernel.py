"""Offline indexed equivalent of the existing Counter DFS (same branch order).

No alternative Mahjong rules or approximated shanten. Keep production's head
enumeration, bounds, joker anchors and early stops; replace string/Counter work
inside recursion with a 34-element integer array and a running tile count.
"""
from functools import lru_cache
from app.core.constants import ALL_TILES, JOKER
from app.core import evaluator as reference

INDEX={t:i for i,t in enumerate(ALL_TILES)}
SEQUENCES={}
PARTNERS={}
_spare=lru_cache(maxsize=4096)(reference._best_with_spare_jokers)
for tile,i in INDEX.items():
    if len(tile)==2:
        num,suit=int(tile[0]),tile[1]
        SEQUENCES[i]=tuple(tuple(INDEX[f'{start+k}{suit}'] for k in range(3)) for start in (num,num-1,num-2) if 1<=start<=7)
        PARTNERS[i]=tuple(INDEX[f'{num+d}{suit}'] for d in (1,2) if num+d<=9)

@lru_cache(maxsize=65536)
def standard(key,jokers,needed):
    counts=list(key)
    best=2*needed
    lower=reference._optimistic_remaining_shanten
    spare=_spare
    active=tuple(i for i,n in enumerate(key) if n)
    units=tuple(1<<(5*i) for i in range(len(key)))
    initial_code=sum(n*units[i] for i,n in enumerate(key))
    visited=set()
    def dfs(j,m,t,h,remain,code):
        nonlocal best
        if lower(m,t,h,remain,needed)>=best: return
        state=(code,j,m,t,h)
        # best only decreases. A state fully visited under a looser bound cannot
        # improve on a revisit; its previously pruned branches remain prunable.
        if state in visited: return
        visited.add(state)
        first=None
        for i in active:
            if counts[i]: first=i;break
        if first is None:
            best=min(best,spare(m,t,h,j,needed));return
        have=counts[first]
        if m<needed:
            if have+j>=3:
                use=min(have,3);counts[first]-=use
                dfs(j-(3-use),m+1,t,h,remain-3,code-use*units[first])
                counts[first]+=use
            for seq in SEQUENCES.get(first,()):
                taken=[];need=0
                for i in seq:
                    if counts[i]: counts[i]-=1;taken.append(i)
                    else: need+=1
                if taken and need<=j: dfs(j-need,m+1,t,h,remain-3,code-sum(units[i] for i in taken))
                for i in taken: counts[i]+=1
        if m+t<needed:
            if have+j>=2:
                use=min(have,2);counts[first]-=use
                dfs(j-(2-use),m,t+1,h,remain-2,code-use*units[first])
                counts[first]+=use
            for other in PARTNERS.get(first,()):
                if counts[other]:
                    counts[first]-=1;counts[other]-=1
                    dfs(j,m,t+1,h,remain-2,code-units[first]-units[other])
                    counts[first]+=1;counts[other]+=1
                elif j:
                    counts[first]-=1
                    dfs(j-1,m,t+1,h,remain-2,code-units[first])
                    counts[first]+=1
        n=counts[first];counts[first]=0
        dfs(j,m,t,h,remain-n,code-n*units[first])
        counts[first]=n
    total=sum(counts)+jokers
    dfs(jokers,0,0,False,total,initial_code)
    # Production's key is lexically sorted, not ALL_TILES order, for head trials.
    if best>-1:
        for tile in sorted(t for t,i in INDEX.items() if counts[i]):
            i=INDEX[tile];n=counts[i]
            if n>=2:
                counts[i]-=2;dfs(jokers,0,0,True,total-2,initial_code-2*units[i]);counts[i]+=2
            elif n==1 and jokers>=1:
                counts[i]-=1;dfs(jokers-1,0,0,True,total-2,initial_code-units[i]);counts[i]+=1
            if best<=0: break
    if jokers>=2 and best>0: dfs(jokers-2,0,0,True,total-2,initial_code)
    return best

def shanten(tiles,joker_count=0,needed_melds=4):
    if not 0<=needed_melds<=4: raise ValueError('needed_melds must be in 0..4')
    # Preserve authoritative complete-hand and discard enumeration semantics.
    if len(tiles)+joker_count==needed_melds*3+2:
        return reference.check_win_or_shanten(list(tiles),joker_count,needed_melds)
    counts=[0]*len(ALL_TILES);jokers=joker_count
    for tile in tiles:
        if tile==JOKER:jokers+=1
        else:counts[INDEX[tile]]+=1
    if max(counts)>=32: return reference.check_win_or_shanten(list(tiles),joker_count,needed_melds)
    return standard(tuple(counts),jokers,needed_melds)
