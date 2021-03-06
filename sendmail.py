from cStringIO import StringIO
import email
import json
import imaplib
import logging
import smtplib

from credentials import GMAIL_PASSWORD

fromaddr = "dbkats@cs.toronto.edu"
username = "dbkats@gmail.com"
# app-specific password
password = GMAIL_PASSWORD

logger = logging.getLogger("ece1779-a1-email.sendmail")

def strip_html(msg):
    buf = StringIO(msg)
    line = buf.readline()
    final_msg = ""

    while line:
        if "<html>" in line:
            final_msg += line.split("<html>")[0]
            break
        elif "<div" in line:
            final_msg += line.split("<div")[0]
            break
        elif "<style>" in line:
            final_msg += line.split("<style>")[0]
            break
        elif "<p" in line:
            final_msg += line.split("<p")[0]
            break
        else:
            final_msg += line
        line = buf.readline()

    return final_msg.strip()


def get_new_mail(last_message_id):
    M = imaplib.IMAP4_SSL("imap.gmail.com")
    M.login(username, password)
    rv, mailboxes = M.list()
    M.select("ECE1779 A1 Registration")
    rv, data = M.search(None, "ALL")
    if rv != "OK":
        logger.info("no messages")
        return []
    logger.info("fetched messages, checking for new emails from students...")
    msg_list = []
    for num in data[0].split():
        rv, data = M.fetch(num, "(RFC822)")
        msg = email.message_from_string(data[0][1])
        from_email = email.utils.parseaddr(msg['From'])[1]
        if from_email in ["dbkats@gmail.com", "dbkats@cs.toronto.edu"]:
            last_message_id = int(num)
            logger.debug("Ignoring email from myself with ID %d", last_message_id)
            continue
        obj = {
            "from": from_email,
            "message": msg.get_payload(),
            "id": int(num)
        }

        if type(obj["message"]) == list:
            msg_text = "\n".join([item.get_payload() for item in obj["message"]])
            msg_text = strip_html(msg_text)
            obj["message"] = msg_text
        msg_list.append(obj)
        # update last message ID
        last_message_id = int(num)
    M.close()
    #write_last_message_id()
    return msg_list

def send_mail(toaddr, subject, content):
    msg = "\r\n".join([
        "From: %s" % fromaddr,
        "To: %s" % toaddr,
        "Subject: %s" % subject,
        "",
        content
    ])

    server = smtplib.SMTP("smtp.gmail.com:587")
    server.ehlo()
    server.starttls()
    server.login(username, password)
    server.sendmail(fromaddr, toaddr, msg)
    server.quit()
    logger.info("Email to %s sent successfully" % toaddr)
    return True

if __name__ == "__main__":
    mail = get_new_mail(0)
    print json.dumps(mail, indent=4)
