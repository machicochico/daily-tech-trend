from db import connect

MAP = {
    "製造": "manufacturing",
    "AI": "ai",
    "開発": "dev",
    "システム": "system",
    "セキュリティ": "security",
}

def main():
    import time
    t0 = time.perf_counter()
    print("[TIME] step=normalize_categories start")
    conn = connect()
    cur = conn.cursor()

    updated = 0
    for src, dst in MAP.items():
        cur.execute("UPDATE articles SET category=? WHERE category=?", (dst, src))
        updated += cur.rowcount
        cur.execute("UPDATE topics SET category=? WHERE category=?", (dst, src))
        updated += cur.rowcount

    conn.commit()
    conn.close()
    print(f"[TIME] step=normalize_categories end sec={time.perf_counter() - t0:.1f} updated={updated}")

if __name__ == "__main__":
    main()
