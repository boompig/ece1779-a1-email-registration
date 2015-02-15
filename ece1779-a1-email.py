#!/usr/bin/env python
import coloredlogs
import cStringIO
import json
import logging
import re
import subprocess
import string
import sqlite3
import sys
from time import sleep

# my imports
import datastore
import sendmail

UNDEF_GROUP = "undefined"
SLEEP_TIME = 60

########## setup logger ##############
logger = logging.getLogger("ece1779-a1-email")
coloredlogs.install(show_timestamps=False, show_hostname=False)
######################################



def read_group_ids(fname, used_fname):
    pattern = "CREATE USER 'group(\d+)' IDENTIFIED BY '(\d+)';"
    d = {}
    with open(fname) as fp:
        for line in fp:
            m = re.match(pattern, line)
            if m:
                d[ int(m.group(1)) ] = int(m.group(2))
    with open(used_fname) as fp:
        used_groups = set([int(line.split(" ")[1].strip()) for line in fp if line.strip()])
    for group_id in used_groups:
        del d[group_id]
    return d

def read_amazon_ids(fname, used_fname):
    with open(fname) as fp:
        ids = [line.strip() for line in fp]
    with open(used_fname) as fp:
        used_ids = [line.split(" ")[1].strip() for line in fp if line.strip()]
    for id in used_ids:
        ids.remove(id)
    return ids

def seek_to_group(buf):
    text = cStringIO.StringIO(buf)
    line = text.readline()
    while line:
        if line.strip().startswith("group"):
            group_num  = line.strip()[len("group "):]
            if group_num == "" or group_num == "007":
                group_num = UNDEF_GROUP
            return group_num, text

        line = text.readline()

    assert False, "Reached end of email without encountering group info"

def extract_num_members(text):
    line = text.readline()
    while line.strip() == "":
        assert line != "", "Reached end of email without encountering number of group members"
        line = text.readline()
    assert line.strip().isdigit(), "Number of group members must be an integer"
    return int(line.strip())

def extract_group_info(text, num_members):
    group = []
    for i in range(num_members):
        m = {}
        line = text.readline()
        while line.strip() == "":
            assert line != "", "Reached end of email without reading all of group info"
            line = text.readline()

        m['name'] = line.strip()
        assert m['name'] != "", "name for group member %d must not be blank" % (i + 1)
        line = text.readline()
        while line.strip() == "":
            assert line != "", "Reached end of email without reading all of group info"
            line = text.readline()

        m['student_num'] = line.strip()
        if m['student_num'].startswith("#"):
            m['student_num'] = m['student_num'][1:]
        assert m['student_num'].isdigit(), "student number must be all digits, got %s" % repr(m['student_num'])
        line = text.readline()
        while line.strip() == "":
            assert line != "", "Reached end of email without reading all of group info"
            line = text.readline()
        m['email'] = line.strip()
        if m['email'].endswith("?"):
            m['email'] = m['email'][:-1]
        if "<" in m['email']:
            m['email'] = m['email'].split("<")[0]
        assert m['email'] != "", "email for group member %d must not be blank" % (i + 1)
        group.append(m)
    return group

def read_submitted_ids(fname):
    with open(fname) as fp:
        reg = [line.strip() for line in fp]
    return reg

def read_email(email_text):
    obj = {}
    email_text = string.translate(email_text, None, "[]?*(),!&^%%$#+=/\\|{}~`:;'\"_")
    print "Message:\n%s\n------------------" % email_text
    obj['group_num'], text = seek_to_group(email_text)
    obj['num_members'] = extract_num_members(text)
    obj['students'] = extract_group_info(text, obj['num_members'])
    return obj

def write_student(student_num):
    with open("students.txt", "a") as fp:
        fp.write("%s\n" % student_num)

def register_group(obj):
    group_logins = read_group_ids("groups.txt", "used_groups.txt")
    prev_reg = read_submitted_ids("students.txt")
    amazon_ids = read_amazon_ids("amazon_ids.txt", "amazon_used.txt")
    amazon_mappings = {}
    for student in obj['students']:
        if student['student_num'] in prev_reg:
            assert False, "Student number %s already registered for an Amazon key" % student['student_num']
        else:
            amazon_mappings[student['student_num']] = amazon_ids.pop()
    if obj['group_num'] == UNDEF_GROUP or obj['group_num'] not in group_logins:
        obj['group_num'] = max(group_logins.keys())
    else:
        obj['group_num'] = int(obj['group_num'])
    assert obj['group_num'] in group_logins, "Group number is invalid"
    database_pwd = group_logins[obj['group_num']]

    for student_num, aws_key in amazon_mappings.iteritems():
        # write that these are now used
        write_used_amazon_key(student_num, aws_key)
        write_student(student_num)
    write_used_group(obj)
    return amazon_mappings, database_pwd

def write_used_amazon_key(student_num, aws_key):
    with open("amazon_used.txt", "a") as fp:
        fp.write("%s %s\n" % (student_num, aws_key))

def write_used_group(obj):
    with open("used_groups.txt", "a") as fp:
        for student in obj['students']:
            fp.write("%s %s\n" % (student['student_num'], obj['group_num']))

def respond_to_email(obj):
    emails = {}
    for student in obj['students']:
        email_content = """
Dear %(name)s,
your group number is %(group_num)d.
Your group login for the database is:
    username: group%(group_num)d
    password: %(database_pwd)s
Your *individual* AWS coupon code is %(amazon_code)s
The database is located at ece1779winter2015db.cf2zhhwzx2tf.us-east-1.rds.amazonaws.com

Good luck!
Sincerely,
Daniel Kats's auto-mailing bot
        """ % ({
            "name": student['name'],
            "group_num": obj['group_num'],
            "database_pwd": obj['password'],
            "amazon_code": student['amazon_code']
        })
        emails[student['email']] = email_content
    return emails

def confirm_save_respond(message_id, is_error):
    confirm = raw_input("Save responded in database? ")
    if confirm == "y":
        logger.info("saving...")
        try:
            datastore.save_respond_msg(message_id, is_error)
            logger.info("saved")
        except sqlite3.IntegrityError:
            logger.error("saving failed, ID already exists")
    else:
        logger.info("not saving")


def main(content, author, message_id):
    try:
        obj = read_email(content)
        assert datastore.get_next_data(obj), "There are no more group logins in the database"

        flag = True
        for student in obj['students']:
            if datastore.student_exists(student['student_num']):
                logger.info("Already registered student # %s" % student['student_num'])
            else:
                flag = False
        if flag:
            logger.info("All students in email already registered, returning")
            confirm_save_respond(message_id, False)
            return

        emails = respond_to_email(obj)
        print "[main] Successfully processed email"
        print json.dumps(obj, indent=4)
        confirm = raw_input("ok to send? ")
        if confirm == "y":
            datastore.save_group_info(obj)
            for addr, email in emails.iteritems():
                print addr
                print email
                sendmail.send_mail(addr, "RE: ECE1779 A1 Registration", email)
            try:
                datastore.save_respond_msg(message_id, False)
            except sqlite3.IntegrityError:
                #whatevs
                pass
        else:
            confirm_save_respond(message_id, is_error)
    except AssertionError as e:
        response_content = """
Dear student,
There is an error somewhere in your email. When parsing, got the following error:
    Error: %(error)s

Please correct this and send another email. See http://www.cs.toronto.edu/~dbkats/#ece1779-a1 for reference.

Good luck!
Sincerely,
Daniel Kats's auto-mailing bot""" % ({"error": str(e)})
        logger.error( "Error: %s" % e )
        print "Message was:"
        print content
        print "-" * 30
        print "Response will be:"
        print response_content
        confirm = raw_input("OK to send error message to %s? " % author)
        if confirm == "y":
            sendmail.send_mail(author, "RE: ECE1779 A1 Registration", response_content)
            confirm_save_respond(message_id, True)
        else:
            confirm_save_respond(message_id, True)

def check_mail_loop():
    while True:
        last_message_id = datastore.last_message_id()
        new_mail_content_list = sendmail.get_new_mail(last_message_id)
        action_items = []
        for email in new_mail_content_list:
            if datastore.message_exists(email['id']):
                logger.debug("Already responded to email with ID %d", email['id'])
            else:
                action_items.append(email)

        if len(action_items) > 0:
            subprocess.call(["say", "you have new mail from students"])
        else:
            logger.info("no new mail")

        for email in action_items:
            logger.info("new mail from %s with ID %d!" % (email['from'], email['id']))
            main(email['message'], email['from'], email['id'])
        logger.info("going to sleep for %d seconds", SLEEP_TIME)
        sleep(SLEEP_TIME)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        logger.debug("Trying to read email from file %s", sys.argv[1])
        with open (sys.argv[1]) as fp:
            content = fp.read()
            main(content, "dbkats@gmail.com", 1)
    else:
        check_mail_loop()
