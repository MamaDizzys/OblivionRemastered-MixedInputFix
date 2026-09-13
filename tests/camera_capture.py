"""Offline trace regressions; these synthetic samples are not live findings."""
from pathlib import Path
import importlib.util
import json
import runpy
import struct
import sys
import types

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('analyze', root / 'tools/analyze_camera_capture.py')
analyzer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analyzer)
rows = []

def add(event, generation=1, **kwargs):
    row = {'seq': len(rows), 'event': event, 'thread': 't1', 'label': 'synthetic',
           'provenance': {'generation': generation, 'owner': 100, 'frame': 0x200000, 'valid': True}}
    row.update(kwargs)
    rows.append(row)
    return row['seq']


def val(x):
    return {'xyz': [x, 0.0, 0.0], 'type': 1}

add('capture_start')
add('reset')
add('mapping_input', action=200, instance=208, key='MouseX', mapping_input=val(-0.75))
add('merge_before', action=200, instance=208, key='MouseX', component=0, candidate=-0.75, accumulated=0.5)
add('merge_after', action=200, instance=208, key='MouseX', component=0, candidate=-0.75, accumulated=-0.75)
add('action_before', action=200, instance=208, value=val(-0.75))
add('action_after', action=200, instance=208, value=val(0.125)) # e.g. retained modifier history.
for axis, action, branch, value, out in [('X', 200, 'Mouse', 0.125, 0.5),
                                        ('X', 200, 'Gamepad', 0.125, -0.5),
                                        ('Y', 300, 'Mouse', 0.4, 0.9)]:
    dispatch_id = len(rows)
    add('dispatch_begin', action=action, instance=action+8, binding=1000+dispatch_id,
        dispatch_id=dispatch_id, value=val(value))
    camera_id = add(axis.lower()+'_entry', axis=axis, camera=999, dispatch_id=dispatch_id, input=val(value))
    add(axis.lower()+'_branch', axis=axis, camera_id=camera_id, getter_result=int(branch=='Gamepad'))
    scope={'generation': 1, 'frame': 0x200000, 'source': branch, 'axis': axis, 'generation_matches': True}
    add(axis.lower()+'_'+branch.lower()+'_output', axis=axis, camera=999, camera_id=camera_id,
        dispatch_id=dispatch_id, branch=branch, output=out,
        provenance={'generation': 1, 'owner':100, 'frame':0x200000, 'scope':scope})
    add('dispatch_end', dispatch_id=dispatch_id)
add('reset', generation=2)
# Same action in a new generation must not count as another dispatch in gen 1.
dispatch_id=len(rows)
add('dispatch_begin', generation=2, action=200, instance=208, binding=4000, dispatch_id=dispatch_id, value=val(0.8))
camera_id=add('x_entry', generation=2, axis='X', camera=999, dispatch_id=dispatch_id, input=val(0.8))
add('x_mouse_output', generation=2, axis='X', camera=999, dispatch_id=dispatch_id, camera_id=camera_id,
    branch='Mouse', output=0.2, provenance={'generation':2,'owner':100,'frame':0x200000,
    'scope':{'source':'Mouse','axis':'X','generation':1,'frame':0x200000,'generation_matches':False}})
add('capture_end')
result=analyzer.analyze(rows)
x=next(c for c in result['dispatch_counts'] if c['generation']==1 and c['axis']=='X')
y=next(c for c in result['dispatch_counts'] if c['generation']==1 and c['axis']=='Y')
assert x['dispatch_count']==2 and x['camera_handler_calls']==2 and x['closed_by_next_reset']
assert y['dispatch_count']==1
xgroup=next(g for g in result['output_groups'] if g['generation']==1 and g['axis']=='X')
ygroup=next(g for g in result['output_groups'] if g['generation']==1 and g['axis']=='Y')
assert xgroup['has_opposing_outputs'] and xgroup['arithmetic_sum']==0
assert ygroup['arithmetic_sum']==0.9 and not ygroup['has_opposing_outputs']
assert result['action_modifier_changes'][0]['changed']
assert result['camera_outputs'][-1]['generation_matches'] is False
assert result['camera_outputs'][-1]['snapshot_generation']==1
assert not analyzer.analyze(rows[:-1])['capture_ended']
assert analyzer.analyze([{'event':'capture_error','site':'test','error':'bad read'}])['capture_errors']
assert analyzer.token({'thread':'t', 'frame':1, 'owner':2,'provenance':{'frame':3,'owner':4,'generation':5}})==('t',5,2,1)

# Execute the actual observer's TLS decoder against bounded synthetic memory.
class Command:
    def __init__(self, *args, **kwargs): pass
fake=types.SimpleNamespace(Command=Command, Breakpoint=object, COMMAND_USER=0, write=lambda s: None)
sys.modules['gdb']=fake
module=runpy.run_path(str(root/'tools/camera_capture.py'))
Capture=module['Capture']
reader_globals=Capture.provenance.__globals__
blob=bytearray(0x5000)
def mem(address,size):
    if address<=0 or address+size>len(blob): raise ValueError('invalid synthetic read')
    return bytes(blob[address:address+size])
reader_globals['memory']=mem
p=0x108
struct.pack_into('<QQQ',blob,p,100,0x200000,9)
struct.pack_into('<QQBB',blob,p+24,200,208,1,1)
struct.pack_into('<QBB',blob,p+0xC18,1,1,0)
struct.pack_into('<Q',blob,208,200)
assert module['SITES']['tls_dispatch_offset'] == 0xC30
# Padding at TLS+0 deliberately remains zero: the previous decoder mistook it
# for current_dispatch. The linked input_type MOV uses +C30.
struct.pack_into('<Q',blob,0x100+0xC30,0x2000)
struct.pack_into('<QQQQQBB',blob,0x2000,100,0x200000,8,200,208,1,1)
cap=Capture.__new__(Capture)
snapshot=cap.provenance({'tls':0x100},208)
assert snapshot['record']['source']=='Mouse' and snapshot['record']['instance_matches']
assert snapshot['scope']['generation']==8 and not snapshot['scope']['generation_matches']
struct.pack_into('<Q',blob,0x2010,9)
assert cap.provenance({'tls':0x100})['scope']['generation_matches']
struct.pack_into('<Q',blob,p+0xC18,129)
try: cap.provenance({'tls':0x100}); assert False
except ValueError: pass
output = root/'build/simultaneous-camera/synthetic-trace.jsonl'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(''.join(json.dumps(r)+'\n' for r in rows))
assert len(analyzer.report(output).splitlines()) <= 150

# Actual linked helper signatures prove the decoder offset (independent of the
# synthetic memory layout), and the helper's TLS-ready register instruction.
sites = module['SITES']
assert bytes.fromhex('488bbe300c0000') in bytes.fromhex(sites['input_type_bytes'])
assert bytes.fromhex(sites['helper_bytes'])[0x13:0x1a] == bytes.fromhex('498d8108000000')

# GDB compiles source without __file__, and can inherit a foreign __file__.
source = (root/'tools/camera_capture.py').read_text()
for namespace in ({'__name__': '__test__'}, {'__name__': '__test__', '__file__': '/tmp/foreign.py'}):
    exec(compile(source, str(root/'tools/camera_capture.py'), 'exec'), namespace)
    assert namespace['SITES'] == sites

# Drive real observer handler/return logic with volatile RCX clobbered. The
# common mouse epilogue must not manufacture a second gamepad output return.
struct.pack_into('<Q',blob,p+0xC18,1)
regs = {'rsp': 0x4800, 'rcx': 0x2100, 'rdx': 0x1000, 'rsi': 0x2100, 'rax': 0}
struct.pack_into('<dddB',blob,0x1000,0.5,0,0,1)
struct.pack_into('<Q',blob,0x2100,0x200)
struct.pack_into('<Q',blob,0x200+0xD18,0x4000)
struct.pack_into('<B',blob,0x1900+0x91,0)
reader_globals['reg'] = regs.__getitem__
reader_globals['xmm_float'] = lambda name: 0.125
cap=Capture.__new__(Capture)
state={'tls':None,'dispatches':[],'cameras':[]}
cap.state=lambda: ('t',state)
cap.recording=True; cap.timing=None; cap.count=0; cap.limit=1000; cap.targets=set()
observed=[]
def record(row):
    observed.append(dict(row, seq=cap.count)); cap.count+=1
cap.write=record
cap.request_finish=lambda reason: (_ for _ in ()).throw(AssertionError(reason))
assert not cap.hit('x_entry')
regs.update(rsp=0x4600,rax=0x1900)
assert not cap.hit('x_getter_before')
regs.update(rcx=0xdead,rax=1)
assert not cap.hit('x_branch')
assert observed[-1]['common_input']==0x1900 and observed[-1]['common_type']==0
regs.update(rcx=0x2100)
assert not cap.hit('x_gamepad_output')
output_id=observed[-1]['seq']
assert not cap.hit('x_gamepad_after')
assert observed[-1]['output_id']==output_id
count=len(observed)
assert not cap.hit('x_mouse_after')
assert len(observed)==count
regs.update(rsp=0x4800,rsi=0xdead)
assert not cap.hit('x_return')
assert observed[-1]['camera']==0x2100 and not state['cameras']
result=analyzer.analyze(observed)
assert result['handler_calls'][0]['returned']
assert result['handler_calls'][0]['output_ids']==[output_id]
assert len(result['receiver_changes'])==1

# An entry and return without an output must remain visible, whereas an entry
# alone is partial. No downstream cancellation or stall verdict is inferred.
assert not cap.hit('x_entry')
assert not cap.hit('x_return')
result=analyzer.analyze(observed)
assert result['handler_calls'][-1]['returned'] and not result['handler_calls'][-1]['output_ids']

# Preparation, contiguous start, and closing boundary use the actual hit path.
cap.timing={'ready':None,'end':None}; enabled=[]
cap.sample_probes=enabled.append
clock=[100.0]
reader_globals['time']=types.SimpleNamespace(monotonic=lambda:clock[0])
regs.update(rsp=0x4500)
assert not cap.hit('reset') and cap.timing['ready']==108
clock[0]=108
assert not cap.hit('reset') and enabled==[True]
clock[0]=111
finished=[]; cap.request_finish=finished.append
assert cap.hit('reset') and finished==['timed_complete']
assert observed[-1]['closing_boundary']
result=analyzer.analyze(observed)
# No TLS here means no claim of an identified production generation.
assert result['capture_errors']==[]

# Exercise actual fail-closed setup validation with relocated synthetic image
# ranges; no breakpoints or game process are used. Independent changed bytes
# must fail before Capture can install probes.
game,dll,page=0x140000000,0x180000000,0x145000000
shim=page+0xB00
virtual={}
def put(address,data):
    virtual.update((address+i,b) for i,b in enumerate(data))
def read_virtual(address,size):
    return bytes(virtual[address+i] for i in range(size))
def call(address,target):
    put(address,b'\xe8'+struct.pack('<i',target-address-5))
put(dll,b'MZ')
put(dll+sites['helper_rva'],bytes.fromhex(sites['helper_bytes']))
put(dll+sites['input_type_rva'],bytes.fromhex(sites['input_type_bytes']))
put(shim,bytes.fromhex('9c4881ec60020000'))
put(shim+0x40,b'\x48\xb8'+struct.pack('<Q',dll+sites['helper_rva']))
put(shim+0x4A,bytes.fromhex('ffd0480fae4c2460'))
put(shim+0x75,bytes.fromhex('4881c4600200009dff2500000000'))
put(shim+0x83,struct.pack('<Q',game+0x3939FA0))
call(game+0x392B6A6,shim)
for rva,off in ((0x489D2F9,0x400),(0x488A0E9,0x600)):
    call(game+rva,page+off)
dispatch=game+0x392CD15
put(dispatch,b'\xff\x15'+struct.pack('<i',page+0xA10-dispatch-6))
put(page+0xA10,struct.pack('<Q',page+0x200))
for rva in (0x488AC43,0x488AD39,0x488AE33,0x488AF29):
    put(game+rva,b'\x75\x0f')
for site in sites['game_sites'].values():
    put(game+site['rva'],bytes.fromhex(site['bytes']))
reader_globals['memory']=read_virtual
cap=Capture.__new__(Capture); cap.game=game
cap.validate()
assert cap.dll==dll and cap.helper==dll+0x7A40
for address in (dll+0x7A40, dll+0x9700, shim+0x4A, game+0x489D2FF,
                game+0x488AC43, game+0x489D2F9+1, page+0xA10):
    original=virtual[address]; virtual[address]^=0xff
    try:
        cap.validate()
        raise AssertionError('Accepted changed byte at '+hex(address))
    except ValueError:
        pass
    finally:
        virtual[address]=original
print('PASS: per-generation/action dispatch counts, independent X/Y outputs, modifier deltas, stale scope detection, partial/error captures, bounded actual TLS decoding')
print('PASS: linked TLS offset, source without __file__, volatile getter RCX, shared epilogue, handler returns, timed capture boundaries, bounded report')
print('PASS: relocated production setup; reject wrong helper, reset return, camera comparison, movement branch, getter redirect and dispatch bridge')
