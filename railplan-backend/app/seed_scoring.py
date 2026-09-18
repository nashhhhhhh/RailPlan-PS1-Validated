"""Idempotent demo policy setup, usable after existing demo data is installed.

python -m app.seed_scoring creates a dedicated local demo administrator and an
unvalidated policy. It does not change existing users' roles or activate policy.
"""
from sqlalchemy import text
from app.database import engine
from app.seed import uid
from app.scoring import PolicyCreate, canonical

def seed_scoring(db):
    if not db.execute(text("SELECT 1 FROM railplan.operators WHERE id=:id"),{"id":uid("operator")}).scalar():
        raise RuntimeError("Run python -m app.seed first")
    db.execute(text("""INSERT INTO railplan.users(id,department_id,auth_subject,display_name)
      VALUES(:id,:dep,'demo-scoring-admin','Demo Scoring Administrator') ON CONFLICT DO NOTHING"""),
      {"id":uid("scoring-admin"),"dep":uid("department")})
    db.execute(text("""INSERT INTO railplan.user_roles(id,user_id,role_id) VALUES(:id,:u,:r) ON CONFLICT DO NOTHING"""),
      {"id":uid("scoring-admin-role"),"u":uid("scoring-admin"),"r":uid("role/administrator")})
    p=PolicyCreate().model_dump(mode="json")
    db.execute(text("""INSERT INTO railplan.scoring_policies(id,code,version,weights,is_validated,operator_id,definition)
      VALUES(:id,:code,1,CAST(:w AS jsonb),false,:op,CAST(:d AS jsonb)) ON CONFLICT DO NOTHING"""),
      {"id":uid("scoring-policy/1"),"code":p["code"],"w":canonical(p["weights"]),"op":uid("operator"),"d":canonical(p)})

if __name__=="__main__":
    with engine().begin() as db: seed_scoring(db)
    print("Demo scoring policy:",uid("scoring-policy/1"))
    print("Demo scoring administrator:",uid("scoring-admin"))
