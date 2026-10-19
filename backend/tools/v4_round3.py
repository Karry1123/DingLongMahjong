"""R2 power planning and conservative O'Brien--Fleming shaped spending."""
import math
from statistics import NormalDist
from tools.sensitivity_scan import KONGS

NORMAL = NormalDist()
ALPHA = .05 / 3

def required_walls(delta, sd=9.2, alpha=ALPHA, power=.8):
    if delta <= 0 or sd <= 0 or not 0 < alpha < .5 or not .5 < power < 1:
        raise ValueError('Invalid power inputs')
    return math.ceil(((NORMAL.inv_cdf(1-alpha)+NORMAL.inv_cdf(power))*sd/delta)**2)

def achieved_power(walls, delta=.4, sd=9.2, alpha=ALPHA):
    return NORMAL.cdf(delta*math.sqrt(walls)/sd-NORMAL.inv_cdf(1-alpha))

def spending(walls, alpha=ALPHA):
    """OF-shaped cumulative budget; incremental local tests give union-bound control.

    This is deliberately more conservative than correlated canonical OF boundaries.
    """
    nodes=sorted(set([math.ceil(walls/3),math.ceil(2*walls/3),walls]))
    previous=0; result=[]
    for n in nodes:
        t=n/walls
        cumulative=1-NORMAL.cdf(NORMAL.inv_cdf(1-alpha)/math.sqrt(t))
        local=cumulative-previous
        result.append(dict(walls=n,fraction=t,cumulative_alpha=cumulative,alpha=local,z=NORMAL.inv_cdf(1-local)))
        previous=cumulative
    return result

def adjusted_net(net, alpha):
    return dict(normal_lower=net['mean']-NORMAL.inv_cdf(1-alpha)*net['se'],alpha=alpha)

def kong_gates(counts):
    g={}
    for t in KONGS:
        x=counts[t];n=x.get('states',0);p=x.get('parent_take',0);c=x.get('candidate_take',0);b=x.get('benefit',0)
        g['opportunities_'+t]=n>=200
        g['rate_'+t]=p>0 and .75<=c/p<=1.25
        g['noncollapse_'+t]=b>0 and x.get('benefit_candidate_take',0)/b >= x.get('benefit_parent_take',0)/b-.02-1e-12 and c<n
    return g

def allocate(seconds_per_hand, desired_main, budget=14400):
    # Reserve 20% for enrichment, bootstrap, reporting and regressions, plus training screen.
    capacity=max(40,int((budget*.8)/seconds_per_hand)-20-1500)
    sizes=dict(main=desired_main,pressure=1000,anchor=1000)
    excess=2*sizes['main']+8*sizes['pressure']+sizes['anchor']-capacity
    for key,mult in [('anchor',1),('pressure',8),('main',2)]:
        if excess<=0:break
        cut=min(sizes[key]-8,4*math.ceil(excess/(4*mult)))
        sizes[key]-=cut;excess-=cut*mult
    return sizes
