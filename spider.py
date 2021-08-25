'''Downloads pages and enters new links to be crawled'''

import sqlite3, wikipedia
from time import time

MAX_CONSEC_FAILS = 5
COMMIT_FREQ = 1
MAX_ROWS_AT_A_TIME = 10
DO_PRELOAD = False
RECRAWL_TIME = 86400        # num seconds before recrawling a previously-crawled page
FAILURE_PENALTY = 86400     # num seconds to add to crawl time for a failed pageload
wikipedia.set_rate_limiting(True)

def get_more_rows(cur, max_to_fetch):
    max_to_fetch = min(MAX_ROWS_AT_A_TIME, max_to_fetch)
    if max_to_fetch < 1: max_to_fetch = 1
    cur.execute(f'SELECT NULL, title FROM Open_Links ORDER BY added LIMIT {max_to_fetch}')
    rows = []
    more_rows = cur.fetchall()
    if more_rows is None:
        print("Warning: no rows found in Open_Links table")
    else:
        rows += more_rows
    if len(rows) < max_to_fetch:
        cur.execute(f'SELECT page_id, title FROM Pages ORDER BY crawled LIMIT {max_to_fetch - len(rows)}')
        more_rows = cur.fetchall()
        if more_rows is not None:
            rows += more_rows
    if len(rows) == 0:
        raise Exception("No rows to fetch!")
    return rows


conn = sqlite3.connect('wsindex.sqlite')
cur = conn.cursor()

try:
    num_to_crawl = int(input("Crawl how many pages? (10) "))
except ValueError:
    num_to_crawl = 10

rows = get_more_rows(cur, num_to_crawl)
(crawled, fails) = (0, 0)

while crawled < num_to_crawl:
    if fails >= MAX_CONSEC_FAILS:
        print(f'{fails} failures in a row, terminating...')
        break

    if crawled % COMMIT_FREQ == 0:
        conn.commit()
    crawled += 1
    
    if len(rows) == 0:
        conn.commit()
        rows = get_more_rows(cur, num_to_crawl - crawled)
    
    (page_id, title) = rows.pop()
    
    # handling disambig pages is not yet supported
    if title.endswith('(disambiguation)'):
        print(f"Warning: {title} in links list, replacing in Open_Links")
        cur.execute('''UPDATE Open_Links SET added=? WHERE title = ?''' , 
                (crawl_time + FAILURE_PENALTY, title) )
        continue

    # Fetch page
    print("Attempting to open", (page_id, title), "... ", end='', flush=True)
    crawl_time = int(time())
    if page_id is not None:
        wp = wikipedia.page(pageid=page_id, preload=DO_PRELOAD)
    else:
        try:
            wp = wikipedia.page(title, preload=DO_PRELOAD, auto_suggest=False)
        except wikipedia.exceptions.PageError:
            print('Could not find title, replacing in Open_Links')
            fails += 1
            cur.execute('''UPDATE Open_Links SET added=? WHERE title = ?''' , 
                    (crawl_time + FAILURE_PENALTY, title) )
            continue
    print('success!', wp, flush=True)

    # Resolve all links to this title in Open_Links
    cur.execute('''SELECT from_id FROM Open_Links WHERE title=? OR title=?''',
            (title, wp.title))
    from_ids = cur.fetchall()
    cur.executemany(f'''DELETE FROM Open_Links WHERE 
            (title=? OR title=?) AND (from_id IS NULL OR from_id=?)''', 
            [(title, wp.title, from_id[0]) for from_id in from_ids] )
    cur.executemany(f'''INSERT OR IGNORE INTO Links (from_id, to_id) VALUES (?,?)''',
            [(from_id[0], wp.pageid) for from_id in from_ids if from_id is not None] )

    # Check if we've already crawled this page recently, skip if so
    cur.execute('''SELECT crawled FROM Pages WHERE page_id=?''', (wp.pageid,))
    found_record = cur.fetchone()
    if found_record is not None:
        if found_record[0] >= crawl_time - RECRAWL_TIME:
            continue

    # Enter page into Pages
    cur.execute('''INSERT OR REPLACE INTO Pages 
            (page_id, title, raw_text, crawled) VALUES (?, ?, ?, ?)''',
            (wp.pageid, wp.title, wp.content, crawl_time) )

    # Add all of this article's links into Links (if already crawled) or Open_Links (if not)
    links = wp.links
    for link in links:
        cur.execute('''SELECT page_id FROM Pages WHERE title=?''', (link,))
        found_link = cur.fetchone()
        if found_link is not None:
            cur.execute('''INSERT OR IGNORE INTO Links (from_id, to_id) VALUES (?,?)''', 
                    (wp.pageid, found_link[0]))
        else:
            cur.execute('''INSERT OR IGNORE INTO Open_Links 
                    (title, added, from_id) VALUES (?,?,?)''',
                    (link, crawl_time, wp.pageid))

    
conn.commit()
conn.close()
