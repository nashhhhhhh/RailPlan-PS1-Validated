"""Opt-in synthetic rule configuration; does not rewrite existing policy versions."""
from uuid import NAMESPACE_URL, uuid5
from sqlalchemy import text
from app.conflict_engine import RULES
from app.database import engine


def configure_demo_rules(conn):
    for code, (name, category, severity, blocking) in RULES.items():
        conn.execute(text("""INSERT INTO railplan.rule_definitions
          (id,code,version,name,category,severity,blocking,enabled,authority_reference)
          VALUES (:id,:code,1,:name,:category,:severity,:blocking,true,
          'SYNTHETIC - not an operational rule') ON CONFLICT (code,version) DO NOTHING"""),
          {"id": uuid5(NAMESPACE_URL, "railplan-engine/"+code), "code": code, "name": name,
           "category": category, "severity": severity, "blocking": blocking})
    # Only the two named synthetic types: never classify other work by guesswork.
    conn.execute(text("""INSERT INTO railplan.compatibility_rules
      (id,first_work_type_id,second_work_type_id,compatible,version,rationale)
      SELECT :id,least(a.id,b.id),greatest(a.id,b.id),false,1,
        'SYNTHETIC - signal inspection and rail renewal are exclusive in this demo'
      FROM railplan.work_types a CROSS JOIN railplan.work_types b
      WHERE a.id=:a AND b.id=:b
      ON CONFLICT(first_work_type_id,second_work_type_id,version) DO NOTHING"""),
      {"id": uuid5(NAMESPACE_URL,"railplan-engine/demo-compatibility"),
       "a": uuid5(NAMESPACE_URL,"railplan-demo/type/Signal inspection"),
       "b": uuid5(NAMESPACE_URL,"railplan-demo/type/Rail renewal")})


if __name__ == "__main__":
    with engine().begin() as conn:
        configure_demo_rules(conn)
    print("Synthetic conflict rules configured. Existing policies were not overwritten.")
