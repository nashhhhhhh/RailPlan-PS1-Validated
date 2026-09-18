"""Run against a seeded local API: python -m scripts.verify_features.
Creates one saved analysis and one score. Requires pip install -e '.[test]'.
"""
import argparse
from uuid import uuid4
import httpx
from app.seed import uid


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:8000')
    args=parser.parse_args()
    with httpx.Client(base_url=args.url,timeout=120) as client:
        def call(method,path,body=None):
            response=client.request(method,path,json=body)
            response.raise_for_status()
            return response.json()
        assert call('GET','/health/ready')['migration']=='0004'
        client.headers['X-Demo-User-Id']=str(uid('planner'))
        result=call('POST','/api/analyses',{'window_id':str(uid('window'))})
        if result['status']!='completed':
            raise RuntimeError(result.get('detail') or 'Analysis failed')
        findings=call('GET',f"/api/analyses/{result['id']}/conflicts")
        assert len(findings)==result['conflict_count'] and findings
        cid=findings[0]['id']
        client.headers['X-Demo-User-Id']=str(uid('scoring-admin'))
        context=call('GET',f'/api/conflicts/{cid}/scoring-context')
        score=call('POST',f'/api/conflicts/{cid}/scores',{
            'policy_id':str(uid('scoring-policy/1')),
            'expected_conflict_version':context['version'],
            'expected_input_fingerprint':context['input_fingerprint'],
            'idempotency_key':str(uuid4()),
        })
        assert call('GET',f'/api/conflicts/{cid}/scores/latest')['id']==score['id']
        print(f"Database ready; {len(findings)} conflicts persisted; score {score['id']} persisted.")
        print('All four backend features exercised successfully.')


if __name__=='__main__':
    main()
