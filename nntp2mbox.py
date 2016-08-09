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


def download(group, aggressive, dry_run, start=None):
    """
    The default behavior is to pause 30 seconds every 1000 messages while
    downloading to reduce the load on the load on the gmane servers.
    This can be skipped by supplying the aggressive flag.
    """

    mbox = mailbox.mbox(group + '.mbox')
    mbox.lock()

    nntpconn = nntplib.NNTP('news.gmane.org')

    resp, count, first, last, name = nntpconn.group(group)
    print(
        'Group %s has %d articles, range %d to %d' %
        (name, count, first, last))

    last = int(last)

    if start:
        startnr = start

        if startnr < first:
            startnr = first

        if startnr > last:
            startnr = last

    else:
        startnr = first

    if not start:
        print('No start message provided, starting at %d' % startnr)

    for msgno in range(startnr, last):
        try:
            if not aggressive and (msgno % 1000 == 0) and (msgno != startnr):
                print('%d: Sleep 30 seconds' % msgno)
                time.sleep(30)

            if dry_run:
                print('Dry-run: download message no. %d' % msgno)
                pass

            resp, info = nntpconn.article(str(msgno))

            text = str()
            for line in info.lines:
                text += line.decode(encoding='UTF-8') + "\n"

            msg = email.message_from_string(text)
            mbox.add(msg)

            print('%d(%s): %s' % (info.number, msgno, info.message_id))
        except:
            print(sys.exc_info()[0])
            pass

    mbox.flush()
    mbox.unlock()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-a",
                        "--aggressive",
                        help="Disable waiting during a download",
                        action="store_true")
    parser.add_argument("-n",
                        "--dry-run",
                        help="perform a trial run with no changes made",
                        action="store_true")
    parser.add_argument("-s",
                        "--start",
                        help="First message in range",
                        type=int)
    parser.add_argument("groups", default="[]", nargs="+")
    args = parser.parse_args()

    for group in args.groups:
        download(group, args.aggressive, args.dry_run, args.start)
