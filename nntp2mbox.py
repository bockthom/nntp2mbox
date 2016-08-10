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
import sys
import time


def log(action, number, msgno, msgid):
    print('%s %d(%s): %s' % (action, number, msgno, msgid))


def contains(mbox, msgid):
    for m in mbox.itervalues():
        if m.get('Message-Id') == msgid:
            return True
    return False


def stat(nntpconn, msgno):
    action = 'nntp [ STAT  ]'
    resp, number, msgid = nntpconn.stat(str(msgno))
    log(action, number, msgno, msgid)
    return number, msgid


def get(nntpconn, msgno):
    action = 'nntp [ GET   ]'
    resp, info = nntpconn.article(str(msgno))

    text = str()
    for line in info.lines:
        text += line.decode(encoding='UTF-8') + "\n"

    log(action, info.number, msgno, info.message_id)
    return(info.number, info.message_id, email.message_from_string(text))


def store(mbox, nntpconn, msgno, update):
    if update:
        number, msgid = stat(nntpconn, msgno)

    if not update or not contains(mbox, msgid):
        number, msgid, msg = get(nntpconn, msgno)
        mbox.add(msg)
        action = 'mbox [ STORE  ]'
    else:
        action = 'mbox [ SKIP  ]'

    log(action, number, msgno, msgid)


def download(group, aggressive, dry_run, number=None, start=None, update=None):
    """
    The default behavior is to pause 30 seconds every 1000 messages while
    downloading to reduce the load on the load on the gmane servers.
    This can be skipped by supplying the aggressive flag.

    If the update argument is supplied, only new messages (i.e., msgid not in
    mbox) will be added to the mbox.
    """

    if not dry_run:
        mbox = mailbox.mbox(group + '.mbox')
        mbox.lock()

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

    print("Retrieving messages %d to %d." % (startnr, last))

    for msgno in range(startnr, last):
        try:
            if not aggressive and (msgno % 1000 == 0) and (msgno != startnr):
                print('%d: Sleep 30 seconds' % msgno)
                time.sleep(30)

            if dry_run:
                print('Dry-run: download message no. %d' % msgno)
                continue

            store(mbox, nntpconn, msgno, update)

        except:
            print(sys.exc_info()[0])
            pass

    if not dry_run:
        mbox.flush()
        mbox.unlock()


if __name__ == "__main__":
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
    parser.add_argument("-s",
                        "--start",
                        help="First message in range",
                        type=int)
    parser.add_argument("-u",
                        "--update",
                        help="retrieve only new messages",
                        action="store_true")
    parser.add_argument("groups", default="[]", nargs="+")
    args = parser.parse_args()

    for group in args.groups:
        download(group,
                 args.aggressive,
                 args.dry_run,
                 args.number,
                 args.start,
                 args.update)
