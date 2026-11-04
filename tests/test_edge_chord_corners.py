import math
from collections import Counter
import pytest
from steltic_openbim.review_model import CaseModel
from steltic_openbim.review_edge_chords import apply, DIAMETER, BEND_RADIUS, TAIL
from steltic_openbim.review_assemblies import build_scene


def fixture():
    b = object.__new__(CaseModel)
    b.key = 'hr28'; b.members = []; b.connections = []; b.profiles = {}; b.changes = []; b.notes = []
    b.used_records = set(); b.levels = [(0, 'BASE', 0), (1, 'TOS', 192)]
    rid = 'connections/conn-edge-chord-bars'
    b.records = {rid: dict(id=rid, data=dict(components='Six #5 long-edge bars, three short-edge bars; 66 in laps and same-size corner bars'))}
    pid = b.custom('REBAR5', 'round', dict(d=DIAMETER))
    for along in (0, 1):
        for side in (0, 1):
            for j in range(6 if along == 0 else 3):
                a = [0, 0, 196.5]; d = a[:]
                a[along] = 2; d[along] = (2160, 1440)[along] - 2
                a[1-along] = d[1-along] = (2 + j*1.5) if side == 0 else (2160, 1440)[1-along] - 2 - j*1.5
                b.member(f'CHORD-L1-{along}-{side}-{j}', pid, 'diaphragm_chord_bar', a, d, 1, 'S', records=[rid])
    return b


def centre(ring):
    return [sum(q[i] for q in ring)/len(ring) for i in range(3)]


@pytest.mark.parametrize('corner', [(0,0), (0,1), (1,0), (1,1)])
def test_all_corner_bars_join_tangent_solids_and_retain_real_laps(corner):
    b = fixture(); apply(b)
    assert len(b.members) == 18 and len(b.endpoint_links) == 36
    assert len({(r['member_id'], r['end']) for r in b.endpoint_links}) == 36
    c = next(c for c in b.connections if c['id'].endswith(f'-{corner[0]}-{corner[1]}'))
    scene = build_scene(dict(pilot='hr28', members=b.members, profiles=list(b.profiles.values())),
                        dict(design_records=list(b.records.values())), c)
    parts = {p['id']: p for p in scene['parts']}
    assert len(scene['welds']) == len(scene['fasteners']) == 0
    for j in range(6):
        bend = parts['BEND'+str(j)]; x = parts['X'+str(j)]['member']
        lap = parts['LAPX'+str(j)]['member']; tail = parts['TAIL'+str(j)]['member']
        caps = [centre(bend['faces'][i]) for i in (0, 1)]
        assert min(math.dist(q, lap['axis'][0]) for q in caps) < 1e-8
        assert min(math.dist(q, tail['axis'][0]) for q in caps) < 1e-8
        assert math.dist(*lap['axis']) == pytest.approx(TAIL)
        assert abs(x['axis'][0][2] - lap['axis'][0][2]) == pytest.approx(DIAMETER)
        assert x['axis'][0][1] == pytest.approx(lap['axis'][0][1])
        assert parts['LAPX'+str(j)]['representation_role'] == 'assembly_component'
        edges = Counter()
        for f in bend['faces']:
            for a,d in zip(f, f[1:]+f[:1]):
                edges[tuple(sorted((tuple(round(v,7) for v in a), tuple(round(v,7) for v in d))))] += 1
        assert set(edges.values()) == {2}
        if j < 3:
            y = parts['Y'+str(j)]['member']
            assert y['axis'][0][0] == pytest.approx(tail['axis'][0][0])
            assert abs(y['axis'][0][2]-tail['axis'][0][2]) == pytest.approx(DIAMETER)
            yy = sorted(q[1] for q in y['axis']); tt = sorted(q[1] for q in tail['axis'])
            assert min(yy[1],tt[1])-max(yy[0],tt[0]) == pytest.approx(TAIL)
        assert bend['bounds'][0][1] <= 90 and bend['bounds'][1][1] <= 90
    assert BEND_RADIUS-DIAMETER/2 == pytest.approx(3*DIAMETER)
    assert all(parts[n]['member']['source_member_index'] == j for j,n in enumerate(
        ['X'+str(j) for j in range(6)]+['Y'+str(j) for j in range(3)]))


def test_unexpected_source_bar_count_is_not_silently_filled():
    b = fixture(); b.members.pop()
    with pytest.raises(ValueError, match='selected six X and three Y'):
        apply(b)
