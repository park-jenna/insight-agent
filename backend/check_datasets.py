import asyncio, os, asyncpg
from dotenv import load_dotenv
load_dotenv()
async def main():
    conn = await asyncpg.connect(os.getenv("DATABASE_URL"))
    rows = await conn.fetch("SELECT id, name, original_filename, row_count FROM datasets ORDER BY uploaded_at")
    for r in rows:
        print(f"id={r['id']}  name={r['name']!r}  file={r['original_filename']!r}  rows={r['row_count']}")
    await conn.close()
asyncio.run(main())
