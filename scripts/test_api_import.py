import sys
sys.path.insert(0, 'd:/IrriVise/services/api')
sys.path.insert(0, 'd:/IrriVise/packages/irrivise_core')

from irrivise_api.main import app
print('API imports OK')

from irrivise_api.storage import connect
db = connect()
tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print('Tables:', sorted(tables))

assert 'experiments' in tables, "experiments table missing!"
assert 'experiment_jobs' in tables, "experiment_jobs table missing!"
print('Schema OK - all required tables present')
