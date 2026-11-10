# SPDX-License-Identifier: Apache-2.0
"""Synthetic in-memory usage aggregation benchmark; never connects to user data."""
from statistics import median
from time import perf_counter
import tracemalloc
from uuid import uuid4
from sqlalchemy import event
from praxioj.problems import load_problem_package
from praxioj_api.models import Base, User, Problem, ProblemVersion, SolveSession, ProviderCall, WorkspaceRun
from praxioj_api.database import make_engine, session_factory
from praxioj_api.runs import usage_for
from praxioj_api import job_models, retention_models
engine=make_engine('sqlite:///:memory:')
Base.metadata.create_all(engine)
factory=session_factory(engine)
manifest=load_problem_package('examples/problems/release-plan')
with factory.begin() as db:
    user=User(identity_token_hash='a'*64,username='synthetic_benchmark',is_active=True)
    db.add(user); db.flush()
    db.add(Problem(id='release-plan')); db.flush()
    version=ProblemVersion(problem_id='release-plan',version='1.0.0',manifest_sha256='b'*64,manifest=manifest.model_dump(mode='json'))
    db.add(version); db.flush()
    session=SolveSession(user_id=user.id,problem_version_id=version.id,model_configuration={},profile_snapshot={})
    db.add(session); db.flush(); sid=session.id
    for i in range(100):
        run=WorkspaceRun(session_id=sid,request_id=str(uuid4()),content_sha256='c'*64,status='completed',tool_calls=[str(i)])
        db.add(run); db.flush()
        db.add(ProviderCall(session_id=sid,run_id=run.id,status='completed',input_tokens=100,output_tokens=50,estimated=False))
with factory() as db:
    session=db.get(SolveSession,sid)
    assert usage_for(db,session,manifest)['model_calls']==100
    samples=[]
    for _ in range(7):
        start=perf_counter()
        for _ in range(100):
            result=usage_for(db,session,manifest)
        samples.append((perf_counter()-start)*10)
    tracemalloc.start()
    result=usage_for(db,session,manifest)
    current,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
    print({'workload':'100 completed calls, 100 completed runs, one tool each; 7x100 reads; SQLite memory; Python3.13; warm connection','ms_per_read_samples':samples,'median_ms':median(samples),'peak_python_bytes':peak,'result':{k:result[k] for k in ('model_calls','tool_calls','input_tokens','output_tokens','usage_complete','estimated')}})
engine.dispose()
