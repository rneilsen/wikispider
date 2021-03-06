import sqlite3
import zlib
from initialise import INDEX_FILE_PATH

MAX_ROWS_AT_A_TIME = 10
COMMIT_FREQ = 1

conn = sqlite3.connect(INDEX_FILE_PATH, timeout=20.0)
cur = conn.cursor()

def get_more_rows(max_to_fetch):
    max_to_fetch = min(max_to_fetch, MAX_ROWS_AT_A_TIME)
    if max_to_fetch < 1: max_to_fetch = 1
    cur.execute('''SELECT pageid, title, raw_text, crawled FROM Pages 
                WHERE zip_text IS NULL 
                ORDER BY crawled LIMIT ?''', (max_to_fetch,))
    results = cur.fetchall()
    if len(results) < 1:
        raise Exception("No rows found!")
    return results

with open('stopwords.txt') as f:
    stop_words = {word.strip() for word in f.readlines()}

try:
    num_to_index = int(input("Index how many pages? (10) "))
except ValueError:
    num_to_index = 10

rows = get_more_rows(num_to_index)
indexed = 0
while indexed < num_to_index:
    if indexed % COMMIT_FREQ == 0:
        conn.commit()
    indexed += 1

    if len(rows) == 0:
        rows = get_more_rows(num_to_index - indexed)
    (pageid, title, raw_text, crawled) = rows.pop()
    print(f'Indexing {pageid}:', title, '...', end='', flush=True)
    
    words = {word.lower().strip() for word in raw_text.split()}
    words.difference_update(stop_words)

    for word in words:
        cur.execute('''SELECT id FROM Words WHERE word=?''', (word,))
        result = cur.fetchone()
        if result is None:
            cur.execute('''INSERT OR IGNORE INTO Words (word) VALUES (?)''', (word,))
            result = (cur.lastrowid,)
        word_id = result[0]

        cur.execute('''INSERT OR IGNORE INTO Mentions (word_id, pageid) VALUES (?,?)''',
                (word_id, pageid))
    
    cur.execute('''REPLACE INTO Pages (pageid, title, zip_text, crawled) VALUES (?,?,?,?)''', 
            (pageid, title, zlib.compress(raw_text.encode()), crawled))

    print('success!', flush=True)
    
conn.commit()
conn.close()
