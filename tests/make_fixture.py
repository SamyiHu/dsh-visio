"""Build the browser fixture: a small drawing with three boxes and one connector.

    python tests/make_fixture.py

Writes tests/fixtures/connector.vsdx and connector-state.json (the panel state the
browser harness replays when it runs without the engine).
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'engine'))
import visio_bridge as vb  # noqa: E402

FIXTURES = os.path.join(ROOT, 'tests', 'fixtures')
PATH = os.path.join(FIXTURES, 'connector.vsdx')


def build():
    os.makedirs(FIXTURES, exist_ok=True)
    for name in os.listdir(FIXTURES):
        if name.startswith('connector.vsdx') or name == 'connector-state.json':
            os.remove(os.path.join(FIXTURES, name))
    vb.handle({'action': 'create', 'dir': FIXTURES, 'name': 'connector',
               'title': 'Connector', 'width': 11, 'height': 8.5})
    ids = []
    for text, x, y, w, h in (('A', 1.2, 6.4, 2.4, 1.0), ('B', 7.4, 6.4, 2.4, 1.0),
                             ('C', 4.3, 1.2, 2.4, 1.0)):
        state = vb.handle({'action': 'add_shape', 'path': PATH, 'page': 1, 'kind': 'rect',
                           'x': x, 'y': y, 'w': w, 'h': h, 'text': text})
        ids.append([s['id'] for s in state['shapes'] if not s['connector']][-1])
    state = vb.handle({'action': 'connect', 'path': PATH, 'page': 1,
                       'from': ids[0], 'to': ids[1], 'label': 'ab'})
    state = vb.build_state(PATH, 1, None)
    payload = {'state': state, 'details': {}}
    for shape in state['shapes']:
        payload['details'][shape['id']] = vb.detail_of(vb.load_doc(PATH), shape['id'], 1)
    out = os.path.join(FIXTURES, 'connector-state.json')
    with open(out, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    print('wrote', PATH)
    print('wrote', out)
    print('shapes', [(s['id'], s['connector']) for s in state['shapes']])


if __name__ == '__main__':
    build()
