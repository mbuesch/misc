#!/usr/bin/env python
"""
# Jamendo.com RSS streamer
#
# Copyright (c) 2010 Michael Buesch <mb@bu3sch.de>
#
# Licensed under the GNU/GPL version 2 or (at your option) any later version
"""

import sys
import random
import re
import feedparser
import httplib
import subprocess
import time


hostname = "www.jamendo.com"

feeds = (
	("Popular albums this week",		"http://www.jamendo.com/en/rss/popular-albums"),
	("Latest albums",			"http://www.jamendo.com/en/rss/last-albums"),
	("Latest albums (Germany)",		"http://www.jamendo.com/en/rss/last-albums/DEU"),
	("This week's 100 most listened to",	"http://www.jamendo.com/en/rss/top-track-week"),
)

defaultHttpHeader = {
	"User-Agent" : "User-Agent: Mozilla/5.0 (Windows; U; " \
		       "Windows NT 5.1; en-us; rv:1.9.0.10) Gecko/20051213 Firefox/1.5",
	"Accept" : "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
	"Accept-Language" : "en-us,en;q=0.5",
	"Accept-Charset" : "ISO-8859-1,utf-8;q=0.7,*;q=0.7",
	"Keep-Alive" : "300",
	"Connection" : "keep-alive",
}


def die(message, retcode=1):
	print message
	sys.exit(retcode)

def jamendoFetchPage(path):
	for i in range(0, 10):
		http = httplib.HTTPConnection(hostname)
		header = defaultHttpHeader.copy()
		http.request("GET", path, None, header)
		resp = http.getresponse()
		path = resp.getheader("location")
		if not path:
			return resp.read()
	die("Failed to fetch " + path + " (recursion limit exceed)")

def parseM3U(m3u):
	ret = []
	curTitle = None
	for line in m3u.splitlines():
		if line.startswith("#EXTM3U"):
			continue
		if line.startswith("#EXTINF"):
			curTitle = line[line.find(",") + 1 : ]
			continue
		if line.startswith("#EXTALBUMARTURL"):
			continue
		if line.startswith("#"):
			die("M3U unknown # directive: " + line)
		if not curTitle:
			die("M3U did not find title")
		ret.append( (line, curTitle) )
		curTitle = None
	return ret

if len(sys.argv) > 1:
	sel = sys.argv[1]
else:
	for i in range(0, len(feeds)):
		print str(i) + ") " + feeds[i][0]
	sel = raw_input("Which feed? ")
try:
	sel = sel.split(",")
	sel = map(lambda x: int(x), sel)
	fsel = filter(lambda x: x >= 0 and x < len(feeds), sel)
	if fsel != sel or not sel:
		raise ValueError
except ValueError:
	die("Invalid feed")

items = []
for feedNr in sel:
	(feedName, feedUrl) = feeds[feedNr]
	feed = feedparser.parse(feedUrl)
	items.extend(feed["items"])
random.shuffle(items)

m3u_re = re.compile(r".*<a href=\"([\w/?=&]*m3u[\w/?=&]*)\".*", re.DOTALL)

for item in items:
	albumTitle = item["title"]
	url = item["link"]
	print "Playing  [" + albumTitle + "]  " + url

	path = url.replace("http://" + hostname, "")
	html = jamendoFetchPage(path)
	m = m3u_re.match(html)
	if not m:
		die("Did not find M3U URL")
	m3uPath = m.group(1)
	m3u = jamendoFetchPage(m3uPath)
	for (streamUrl, songTitle) in parseM3U(m3u):
		try:
			p = subprocess.Popen( ("mplayer", streamUrl) )
			p.wait()
		except KeyboardInterrupt:
			time.sleep(0.5)
			while True:
				print "0) Next song"
				print "1) Next album"
				print "2) Terminate"
				try:
					sel = int(raw_input("What do? "))
					if sel < 0 or sel > 2:
						raise ValueError
				except ValueError:
					continue
				break
			if sel == 0:
				continue
			if sel == 1:
				break
			if sel == 2:
				die("Terminated", retcode=0)
