"""Frozen native dataclasses/session-key and runner subsets, not package bootstrap."""
from __future__ import annotations
import ast,dataclasses,logging,weakref
from dataclasses import dataclass,field
from contextlib import suppress
from pathlib import Path
from enum import Enum
from typing import Any,Optional,Callable
R=Path(__file__).resolve().parent
logger=logging.getLogger('context-native-subset')
def load(rel,names,env,root='snapshot'):
    path=R/root/rel;tree=ast.parse(path.read_text(encoding='utf-8'))
    nodes=[n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names]
    if len(nodes)!=len(names) or {n.name for n in nodes}!=set(names):raise ValueError('subset selection')
    exec(compile(ast.fix_missing_locations(ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0)]+nodes,type_ignores=[])),str(path),'exec'),env)
    return env
load('gateway/config.py',{'Platform'},globals())
load('gateway/session_identity.py',{'RoutingIdentity'},globals())
load('gateway/session.py',{'SessionSource','build_session_key','_session_key_namespace','_canonical_participant'},globals())
load('gateway/turn_context.py',{'TurnContext'},globals())
