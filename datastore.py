import re
import sqlite3

def db_connect():
    return sqlite3.connect("ece1779_a1.db")

def db_init():
    conn = db_connect()
    cur = conn.cursor()

    cur.execute(
        "CREATE TABLE IF NOT EXISTS groups (group_num INTEGER PRIMARY KEY, username VARCHAR, password VARCHAR, in_use BOOLEAN NOT NULL)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS students (student_num INTEGER PRIMARY KEY, group_num INTEGER REFERENCES groups(group_num))"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS amazon_credits (credit VARCHAR PRIMARY KEY, student INTEGER REFERENCES students (student_num))"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS messages (message_id INTEGER PRIMARY KEY, responded BOOLEAN DEFAULT FALSE, success BOOLEAN DEFAULT FALSE)"
    )

    conn.commit()
    conn.close()

def load_existing_data_amazon():
    with open("amazon_ids.txt") as fp:
        l = [(line.strip(), ) for line in fp if line.strip()]

    conn = db_connect()
    cur = conn.cursor()

    cur.executemany("INSERT INTO amazon_credits (credit) VALUES (?)", l)

    conn.commit()
    conn.close()

def load_existing_data_groups(fname):
    l = []
    with open(fname) as fp:
        for line in fp:
            m = re.match("CREATE USER '(group(\d+))' IDENTIFIED BY '(.*?)'", line)
            group_num = m.group(2)
            username = m.group(1)
            password = m.group(3)
            l.append( (group_num, username, password) )

    conn = db_connect()
    cur = conn.cursor()
    cur.executemany("INSERT INTO groups (group_num, username, password, in_use) VALUES (?, ?, ?, 0)", l)
    conn.commit()
    conn.close()
    return True

def last_message_id():
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT MAX(message_id) FROM messages WHERE responded=1")
    message_id = cur.fetchone()[0]
    conn.close()
    if message_id is None:
        return 50
    else:
        return int(message_id)

def save_respond_msg(message_id, is_error):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("INSERT INTO messages (message_id, success, responded) VALUES (?, ?, 1)",
        [message_id, int(not is_error)]
    )
    conn.commit()
    conn.close()
    return True

def save_group_info(group_info):
    conn = db_connect()
    cur = conn.cursor()
    for student in group_info['students']:
        cur.execute("INSERT INTO students (student_num, group_num) VALUES (?, ?)",
                [student['student_num'], group_info['group_num']])
        cur.execute("UPDATE groups SET in_use=1 WHERE group_num=?",
                [group_info['group_num']])
        cur.execute("UPDATE amazon_credits SET student=? WHERE credit=?",
                [student['student_num'], student['amazon_code']])
    conn.commit()
    conn.close()
    return True

def get_next_data(group_info):
    """Insert the following global fields: group_num, username, password
    Insert the following local field: amazon_code"""

    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT MAX(group_num) FROM groups WHERE in_use=0")
    try:
        next_group = int(cur.fetchone()[0])
    except TypeError:
        # no next ID
        return False
    group_info['group_num'] = next_group
    cur.execute("SELECT username, password FROM groups WHERE group_num=?", [next_group])
    next_login = cur.fetchone()
    group_info['username'] = next_login[0]
    group_info['password'] = next_login[1]
    cur.execute("SELECT credit FROM amazon_credits WHERE student IS NULL LIMIT ?",
            [group_info['num_members']])
    results = cur.fetchall()
    for i, student in enumerate(group_info['students']):
        student['amazon_code'] = results[i][0]
    conn.commit()
    conn.close()
    return True

def import_data_amazon():
    l = []
    with open ("amazon_used.txt") as fp:
        for line in fp:
            if line.strip():
                l.append( tuple(line.split()) )
    conn = db_connect()
    cur = conn.cursor()
    cur.executemany("UPDATE amazon_credits SET student=? WHERE credit=?", l)
    conn.commit()
    conn.close()

def import_data_groups():
    l = []
    with open ("used_groups.txt") as fp:
        for line in fp:
            if line.strip():
                l.append( tuple(line.split()) )
    conn = db_connect()
    cur = conn.cursor()
    cur.executemany("INSERT INTO students (student_num, group_num) VALUES (?, ?)", l)

    group_nums = set([ (item[1], ) for item in l ])
    cur.executemany("UPDATE groups SET in_use=1 WHERE group_num=?", group_nums)
    conn.commit()
    conn.close()


def message_exists(message_id):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM messages WHERE message_id=?", [message_id])
    rows = cur.fetchall()
    result = len(rows) > 0
    conn.close()
    return result

def student_exists(student_num):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM students WHERE student_num=?", [student_num])
    rows = cur.fetchall()
    result = len(rows) > 0
    conn.close()
    return result

def db_clear():
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("UPDATE amazon_credits SET student=NULL WHERE 1=1")
    cur.execute("DELETE FROM students WHERE 1=1")
    cur.execute("UPDATE groups SET in_use=0 WHERE 1=1")
    conn.commit()
    conn.close()

if __name__ == "__main__":
    load_existing_data_groups("more_groups.txt")
