import json
import sys
import httpx

from scripts import run_query_smoke as runner


def rows():
    return [{"garment_zone": zone, "text": "fitted cropped top", "direction_id": "A"}
            for zone, count in [("upper_body", 5), ("lower_body", 5), ("one_piece", 2)]
            for _ in range(count)]


def test_spec_parser_uses_the_exact_fifteen_smoke_ids():
    text = '\n'.join(f'| {identifier} | input {identifier} | expected | avoid |'
                     for identifier in reversed(runner.SMOKE_IDS))
    text += '\n| PRO-02 | not a smoke case | other | other |'
    assert [case['id'] for case in runner.read_cases(text)] == runner.SMOKE_IDS


def test_structural_checks_do_not_replace_semantic_review():
    assert all(runner.checks({"queries": rows()}).values())
    bad = rows()
    bad[0]["text"] = "中文"
    assert not runner.checks({"queries": bad})["ascii_english"]


def test_runner_stops_at_query_api_and_resumes_without_paid_repeats(tmp_path, monkeypatch):
    spec = tmp_path / 'spec.md'
    spec.write_text('\n'.join(f'| {identifier} | request | expected | avoid |'
                             for identifier in runner.SMOKE_IDS), encoding='utf-8')
    output = tmp_path / 'output'
    calls = []
    class Response:
        def __init__(self, data): self.data = data
        def raise_for_status(self): pass
        def json(self): return self.data
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, route): return Response({"status": "ok"})
        def post(self, route, json):
            calls.append(route)
            if route == '/api/query-plans/clarify': return Response({"requirements": {}})
            assert route == '/api/query-plans'
            return Response({"queries": rows()})
    monkeypatch.setattr(runner.httpx, 'Client', Client)
    monkeypatch.setattr(sys, 'argv', ['runner', '--spec', str(spec), '--output-dir', str(output), '--case', 'PRO-01'])
    runner.main()
    runner.main()
    assert calls == ['/api/query-plans/clarify', '/api/query-plans']
    saved = json.loads((output / 'PRO-01.json').read_text(encoding='utf-8'))
    assert saved['status'] == 'completed'
    assert (output / 'RESULTS.md').exists()


def test_quota_error_stops_remaining_api_calls(tmp_path, monkeypatch):
    spec = tmp_path / 'spec.md'
    spec.write_text('\n'.join(f'| {identifier} | request | expected | avoid |'
                             for identifier in runner.SMOKE_IDS), encoding='utf-8')
    calls = []
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, route): return httpx.Response(200, request=httpx.Request('GET', 'http://test/health'))
        def post(self, route, json):
            calls.append(route)
            return httpx.Response(503, request=httpx.Request('POST', 'http://test/clarify'),
                                  json={'detail': 'credit_balance_exhausted'})
    monkeypatch.setattr(runner.httpx, 'Client', Client)
    monkeypatch.setattr(sys, 'argv', ['runner', '--spec', str(spec), '--output-dir', str(tmp_path / 'output'), '--workers', '1'])
    runner.main()
    assert calls == ['/api/query-plans/clarify']
    assert len(list((tmp_path / 'output').glob('*-*.json'))) == 15
