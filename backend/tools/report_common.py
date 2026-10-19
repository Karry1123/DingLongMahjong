"""Small pure Markdown report helpers (no source rewriting)."""
def number(value):
    return '证据不足' if value is None else f'{value:.6f}'

def table(headers,rows):
    return ['| '+' | '.join(map(str,headers))+' |','|'+'|'.join('---' for _ in headers)+'|',
            *['| '+' | '.join(map(str,row))+' |' for row in rows]]

def intervals(comparison,keys=('net','dealin','zimo','progress','low_tenpai')):
    return table(('指标','均值差','正态下界','bootstrap下界','正态上界','bootstrap上界'),
        [(k,*[number(comparison.get(k,{}).get(x)) if comparison.get(k) else '证据不足' for x in ('mean','normal_lower','bootstrap_lower','normal_upper','bootstrap_upper')]) for k in keys])
