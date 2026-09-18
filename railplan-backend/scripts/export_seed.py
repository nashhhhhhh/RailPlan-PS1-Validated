"""Print SQL equivalent of the Python fixtures; never connects to a database."""
import re
from sqlalchemy import bindparam
from sqlalchemy.dialects import postgresql
from app.seed import seed, uid

class Result:
    def scalar(self):
        return None

class Recorder:
    def execute(self, statement, params):
        if re.search(r"INSERT INTO railplan\.", str(statement)):
            bound=statement.bindparams(*(bindparam(k,value=v) for k,v in params.items()))
            print(str(bound.compile(dialect=postgresql.dialect(),compile_kwargs={"literal_binds":True}))+";")
        return Result()

print("-- Generated from app/seed.py. Synthetic only. Idempotent as a fixture set.")
print("DO $seed$ BEGIN")
print("IF NOT EXISTS (SELECT 1 FROM railplan.operators WHERE id='"+str(uid("operator"))+"') THEN")
seed(Recorder())
print("END IF; END $seed$;")
