# SPDX-License-Identifier: AGPL-3.0-or-later
"""Persistent JSON-lines adapter for the pinned iztro structural study engine."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess

VERSION = 'OBS-R8-ZW-1.0'


class ZiweiEngine:
    def __init__(self, node='node', node_modules=None):
        env=os.environ.copy()
        if node_modules is not None:env['OBS_NODE_MODULES']=str(node_modules)
        self.process=subprocess.Popen([node,str(Path(__file__).with_name('ziwei_bridge.cjs'))],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1,env=env)

    def compute(self,row,years,shift_minutes=0,include_chart=False,detailed=False):
        request={'row':row,'years':[int(x) for x in years],'shift_minutes':shift_minutes,'include_chart':include_chart,'detailed':detailed}
        if self.process.poll() is not None:raise RuntimeError('Ziwei subprocess has exited: '+self.process.stderr.read()[:500])
        self.process.stdin.write(json.dumps(request,ensure_ascii=False,allow_nan=False)+'\n');self.process.stdin.flush()
        result=self.process.stdout.readline()
        if not result:raise RuntimeError('Ziwei bridge returned no record: '+self.process.stderr.read()[:500])
        return json.loads(result)

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            try:self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:self.process.terminate();self.process.wait(timeout=5)
        self.process.stdout.close();self.process.stderr.close()

    def __enter__(self):return self
    def __exit__(self,*args):self.close()


def evaluate(row,years,shift_minutes=0,include_chart=False,detailed=False,node_modules=None):
    with ZiweiEngine(node_modules=node_modules) as engine:
        return engine.compute(row,years,shift_minutes,include_chart,detailed)


_shared_engine = None

def _shared():
    global _shared_engine
    if _shared_engine is None or _shared_engine.process.poll() is not None:
        _shared_engine = ZiweiEngine()
    return _shared_engine


def build_natal(birth, shift_minutes=0):
    result = _shared().compute(birth, [], shift_minutes, include_chart=True)
    if result['status'] == 'abstain':
        raise ValueError(result.get('reason','Invalid Ziwei birth input'))
    return {'engine':VERSION,'birth_input':dict(birth),'shift_minutes':shift_minutes,'chart':result['chart'],'status':result['status']}


def annual_signals(natal, year, detailed=False):
    result = _shared().compute(natal['birth_input'], [int(year)], natal['shift_minutes'], detailed=detailed)
    annual = result['annual'][0]
    return {'primary_score':annual.get('score'),'status':annual['status'],'components':annual}


def close_shared_engine():
    global _shared_engine
    if _shared_engine is not None:_shared_engine.close();_shared_engine=None


import atexit
atexit.register(close_shared_engine)
