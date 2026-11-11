"""Explicit opt-in store adapter. No runtime source rewriting, no deployment."""
import pathlib,sqlite3
from sqlite_state import StateTrial,create_jobs

def install(module):
 if hasattr(module,'_original_json_ingest'):return module._original_json_ingest
 original=module.ingest
 def sqlite_ingest(sources,destination,fetcher=None):
  dest=pathlib.Path(destination);dest.mkdir(parents=True,exist_ok=True);dbpath=dest/'state.sqlite'
  if not dbpath.exists():
   if (dest/'state.json').exists():
    from import_state import import_state
    import_state(dest/'state.json',dbpath)
   else:
    db=sqlite3.connect(dbpath);create_jobs(db)
    for name in ['sources','desc_fetch','metadata','section_presence']:db.execute('CREATE TABLE '+name+' (key TEXT PRIMARY KEY,payload TEXT NOT NULL)')
    db.execute("INSERT INTO section_presence VALUES('sources','true')");db.commit();db.close()
  with StateTrial(dbpath)as trial:
   report=original(sources,dest,fetcher=fetcher,state_trial=trial);trial.commit();return report
 module._original_json_ingest=original;module.ingest=sqlite_ingest;return original
