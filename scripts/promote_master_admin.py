from __future__ import annotations
import argparse
from app.database.database import initialize_database,transaction
def main():
 p=argparse.ArgumentParser(description="Grant Master Admin to an existing active admin account.")
 p.add_argument("--username",required=True); a=p.parse_args(); initialize_database()
 with transaction() as c:
  u=c.execute("SELECT id,username,role,is_active,is_master_admin FROM users WHERE username=? COLLATE NOCASE",(a.username.strip(),)).fetchone()
  if u is None:p.error("User does not exist")
  if u["role"]!="admin" or not u["is_active"]:p.error("Target must be an active admin")
  if u["is_master_admin"]:print(f'{u["username"]} is already Master Admin');return 0
  c.execute("UPDATE users SET is_master_admin=1,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",(u["id"],))
 print(f"Granted Master Admin privileges to {u['username']}");return 0
if __name__=="__main__":raise SystemExit(main())
