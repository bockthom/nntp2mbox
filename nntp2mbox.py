#!/usr/bin/env python3
#
# Distributed under terms of the MIT license.
#
# Copyright (c) 2009 Sven Velt
#                    original code,
#                    please see https://github.com/wAmpIre/nntp2mbox
#                    for the original project by Sven
#
# Copyright (c) 2016 Olaf Lessenich
#                    ported to python3, change in functionality
#

import argparse
import email
import mailbox
import nntplib
import time
import sqlite3
import os.path
import traceback


status = '0 %'
attempts = 2  # number of attempts in case of temporary error


def log(target, action, number, msgno, msgid):
    print('%5s | %-4s | %-5s | %d(%s): %s' % (status, target, action, number,
                                              msgno, msgid))


def list_groups():
    nntpconn = nntplib.NNTP('news.gmane.org')
    resp, lists = nntpconn.list()

    for group, last, first, flag in lists:
        print(group)

    nntpconn.quit()


def contains(index, msgid):
    return index.execute('SELECT * FROM messages WHERE msgid=?',
                         (msgid,)).fetchone()


def stat(nntpconn, msgno):
    for attempt in range(attempts):
        try:
            resp, number, msgid = nntpconn.stat(str(msgno))
        except nntplib.NNTPTemporaryError:
            print('%d: Temporary error. Sleep 5 seconds and retry.' % msgno)
            if not aggressive:
                time.sleep(5)
            pass
        else:
            break
    else:
        print('%d: Failed to download after %d attempts' % (msgno, attempts))

    log('nntp', 'STAT', number, msgno, msgid)
    return number, msgid


def get(nntpconn, msgno):
    for attempt in range(attempts):
        try:
            resp, info = nntpconn.article(str(msgno))
        except nntplib.NNTPTemporaryError:
            print('%d: Temporary error. Sleep 5 seconds and retry.' % msgno)
            if not aggressive:
                time.sleep(5)
            pass
        else:
            break
    else:
        print('%d: Failed to download after %d attempts' % (msgno, attempts))

    text = str()
    for line in info.lines:
        text += line.decode(encoding='UTF-8') + "\n"

    log('nntp', 'GET', info.number, msgno, info.message_id)
    return(info.number, info.message_id, email.message_from_string(text))


def check(index, mbox, nntpconn, msgno, update):

    if update:
        number, msgid = stat(nntpconn, msgno)
    else:
        number = msgno
        msgid = 'unknown msg-id'

    if not update or not contains(index, msgid):
        queue = True
        action = 'QUEUE'
    else:
        queue = False
        action = 'SKIP'

    log('mbox', action, number, msgno, msgid)
    return queue


def store(index, mbox, nntpconn, msgno):
    number, msgid, msg = get(nntpconn, msgno)
    mbox.add(msg)
    index_msg(index, msg)
    index.commit()
    action = 'STORE'
    log('mbox', action, number, msgno, msgid)


def index_msg(index, msg):
    msgid = msg.get('Message-Id')
    date = msg.get('Date')
    sender = msg.get('From')
    subject = msg.get('Subject')
    index.execute('INSERT INTO messages VALUES(?,?,?,?)', (msgid, date, sender,
                                                           subject))


def initialize_index(indexfile, mbox):
    print('Initialize index...')
    index = sqlite3.connect(indexfile)

    index.execute('''CREATE TABLE messages
                  (msgid text, date text, sender text, subject text)''')

    for m in mbox.itervalues():
        index_msg(index, m)

    index.commit()
    return index


def download(group, aggressive, dry_run, number=None, start=None, update=None):
    """
    The default behavior is to pause 30 seconds every 1000 messages while
    downloading to reduce the load on the load on the gmane servers.
    This can be skipped by supplying the aggressive flag.

    If the update argument is supplied, only new messages (i.e., msgid not in
    mbox) will be added to the mbox.
    """

    global status

    if not dry_run:
        mbox = mailbox.mbox(group + '.mbox')
        mbox.lock()
        indexfile = group + '.db'

        if not os.path.isfile(indexfile):
            index = initialize_index(indexfile, mbox)
        else:
            index = sqlite3.connect(indexfile)

    nntpconn = nntplib.NNTP('news.gmane.org')

    resp, count, first, last, name = nntpconn.group(group)
    print(
        'Group %s has %d articles, range %d to %d' %
        (name, count, first, last))

    last = int(last)

    if start:
        startnr = max(first, start)
        startnr = min(startnr, last)

        if number:
            last = min(startnr + number, last)

    else:
        startnr = first

        if number:
            startnr = max(startnr, last - number)

    if not start:
        print('No start message provided, starting at %d' % startnr)

    print("Checking messages %d to %d." % (startnr, last))

    stack = []

    # Check which messages need to be retrieved
    for msgno in reversed(range(startnr, last + 1)):
        try:
            if not aggressive and (msgno % 1000 == 0) and (msgno != startnr):
                print('%d: Sleep 30 seconds' % msgno)
                time.sleep(30)

            if dry_run:
                print('Dry-run: download message no. %d' % msgno)
                continue

            status = str(int(100 * (last - msgno) / (last - startnr))) + ' %'

            if check(index, mbox, nntpconn, msgno, update):
                stack.append(msgno)
            else:
                print('Found a message that is already in the mbox.')
                break

        except:
            traceback.print_exc()
            pass

    # actually retrieve the messages
    length = len(stack)
    count = 0

    print("Retrieving %d messages." % length)

    while stack:
        count += 1
        status = str(int(100 * count / length)) + ' %'
        msgno = stack.pop()

        try:
            store(index, mbox, nntpconn, msgno)
        except:
            traceback.print_exc()
            pass

    if not dry_run:
        mbox.flush()
        mbox.unlock()
        index.close()

    nntpconn.quit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-a",
                        "--aggressive",
                        help="Disable waiting during a download",
                        action="store_true")
    parser.add_argument("-d",
                        "--dry-run",
                        help="perform a trial run with no changes made",
                        action="store_true")
    parser.add_argument("-n",
                        "--number",
                        help="Fetch the n most recent messages",
                        type=int)
    parser.add_argument("-l",
                        "--list-groups",
                        help="list all available groups and exit",
                        action="store_true")
    parser.add_argument("-s",
                        "--start",
                        help="First message in range",
                        type=int)
    parser.add_argument("-u",
                        "--update",
                        help="retrieve only new messages",
                        action="store_true")
    parser.add_argument("groups", default="[]", nargs="*")
    args = parser.parse_args()

    if args.list_groups:
        list_groups()
        return

    for group in args.groups:
        try:
            download(group,
                     args.aggressive,
                     args.dry_run,
                     args.number,
                     args.start,
                     args.update)
        except:
            traceback.print_exc()
            pass


if __name__ == "__main__":
    main()
