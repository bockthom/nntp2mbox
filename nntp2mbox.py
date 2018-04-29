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
    resp, number, msgid = nntpconn.stat(str(msgno))
    log('nntp', 'STAT', number, msgno, msgid)
    return number, msgid


def get(nntpconn, msgno):
    resp, info = nntpconn.article(str(msgno))
    text = b'\r\n'.join(info.lines)
    log('nntp', 'GET', info.number, msgno, info.message_id)
    return(info.number, info.message_id, email.message_from_bytes(text))


def check(index, mbox, nntpconn, msgno):
    number, msgid = stat(nntpconn, msgno)
    return not contains(index, msgid)


def store(index, mbox, nntpconn, msgno):
    try:
        number, msgid, msg = get(nntpconn, msgno)
        mbox.add(msg)
        index_msg(index, msg)
        action = 'STORE'
        log('mbox', action, number, msgno, msgid)
    except nntplib.NNTPTemporaryError:
        pass
    except:
        traceback.print_exc()
        pass


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
            last = min(startnr + number - 1, last)

    else:
        startnr = first
        print('No start message provided, starting at %d' % startnr)

        if number and not update:
            startnr = max(startnr, last - number)

    if update:
        print("Checking messages %d to %d whether they need to be retrieved."
              % (startnr, last))
        # Check which messages need to be retrieved
        lo = startnr
        hi = last
        while lo < hi:
            mid = (lo+hi)//2
            try:
                if check(index, mbox, nntpconn, mid):
                    # msg is new
                    hi = mid
                else:
                    # msg already in the mbox
                    lo = mid+1
            except nntplib.NNTPTemporaryError:
                pass
            except:
                traceback.print_exc()
                pass

        startnr = lo
        if number:
            last = min(startnr + number - 1, last)

    print("First to fetch: %d" % startnr)
    print("Last to fetch: %d" % last)

    if dry_run:
        mbox.flush()
        mbox.unlock()
        index.commit()
        index.close()
        return

    length = last + 1 - startnr
    count = 0
    print("Retrieving %d messages." % length)

    for msgno in range(startnr, last + 1):
        if dry_run:
            print('Dry-run: download message no. %d' % msgno)
            continue

        count += 1
        status = str(int(100 * count / length)) + ' %'

        try:
            store(index, mbox, nntpconn, msgno)
        except:
            traceback.print_exc()
            pass

        if count % 1000 == 0:
            mbox.flush()
            index.commit()
            if not aggressive and (msgno != startnr):
                print('%d: Sleep 30 seconds' % msgno)
                time.sleep(30)

    mbox.flush()
    mbox.unlock()
    index.commit()
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
