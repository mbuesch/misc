#!/usr/bin/env python
# vim: set fileencoding=UTF-8 :
"""
# Geocaching.com stats tool
# (c) Copyright 2010 Michael Buesch
# Licensed under the GNU/GPL version 2 or later.
"""

import gccom
import sys
import os
import getopt
import re
import time
import datetime
import calendar
import htmllib
import cgi


barTemplateUrl		= "http://img.geocaching.com/cache/log/f8db1278-8482-4aec-9dff-a16659e9d647.jpg"
cacheTypeIconUrl	= "http://www.geocaching.com/images/wpttypes/sm/%s.gif"
containerTypeIconUrl	= "http://www.geocaching.com/images/icons/container/%s.gif"
starsIconUrl		= "http://www.geocaching.com/images/stars/stars%s.gif"


opt_localstorage = None


def mkdir_recursive(filename, mode=0755):
	try:
		os.makedirs(filename, mode)
	except (OSError), e:
		if e.strerror.find("File exists") >= 0:
			return
		raise

def gcStringToDate(string):
	# Convert a xx/xx/xxxx date to a datetime.date object.
	# May raise ValueError
	try:
		elements = string.split("/")
		return datetime.date(year=int(elements[2]),
				     month=int(elements[0]),
				     day=int(elements[1]))
	except ValueError, IndexError:
		raise ValueError

def htmlEscape(string):
	return cgi.escape(string)

def htmlUnescape(string):
	p = htmllib.HTMLParser(None)
	p.save_bgn()
	p.feed(string)
	return p.save_end()

def uniquifyList(l): 
	ret = []
	for e in l:
		if e not in ret:
			ret.append(e)
	return ret

class Geocache:
	# Cache types
	CACHE_TRADITIONAL	= 0
	CACHE_MULTI		= 1
	CACHE_MYSTERY		= 2
	CACHE_EARTH		= 3
	CACHE_VIRTUAL		= 4

	cacheTypeToIconUrlMap = {
		CACHE_TRADITIONAL	: cacheTypeIconUrl % "2",
		CACHE_MULTI		: cacheTypeIconUrl % "3",
		CACHE_MYSTERY		: cacheTypeIconUrl % "8",
		CACHE_EARTH		: cacheTypeIconUrl % "earthcache",
		CACHE_VIRTUAL		: cacheTypeIconUrl % "4",
	}
	cacheTypeToTextMap = {
		CACHE_TRADITIONAL	: "traditional",
		CACHE_MULTI		: "multi",
		CACHE_MYSTERY		: "mystery",
		CACHE_EARTH		: "earth",
		CACHE_VIRTUAL		: "virtual",
	}

	# Container types
	CONTAINER_NOTCHOSEN	= 0
	CONTAINER_MICRO		= 1
	CONTAINER_SMALL		= 2
	CONTAINER_REGULAR	= 3
	CONTAINER_LARGE		= 4
	CONTAINER_VIRTUAL	= 5
	CONTAINER_OTHER		= 6

	containerTypeToIconUrlMap = {
		CONTAINER_NOTCHOSEN	: containerTypeIconUrl % "not_chosen",
		CONTAINER_MICRO		: containerTypeIconUrl % "micro",
		CONTAINER_SMALL		: containerTypeIconUrl % "small",
		CONTAINER_REGULAR	: containerTypeIconUrl % "regular",
		CONTAINER_LARGE		: containerTypeIconUrl % "large",
		CONTAINER_VIRTUAL	: containerTypeIconUrl % "virtual",
		CONTAINER_OTHER		: containerTypeIconUrl % "other",
	}
	containerTypeToTextMap = {
		CONTAINER_NOTCHOSEN	: "not chosen",
		CONTAINER_MICRO		: "micro",
		CONTAINER_SMALL		: "small",
		CONTAINER_REGULAR	: "regular",
		CONTAINER_LARGE		: "large",
		CONTAINER_VIRTUAL	: "virtual",
		CONTAINER_OTHER		: "other",
	}

	# Valid level values for "terrain" and "difficulty"
	LEVELS = (10, 15, 20, 25, 30, 35, 40, 45, 50)

	def __init__(self, guid, gcId, hiddenDate,
		     cacheType, containerType,
		     difficulty, terrain, country,
		     cacheOwner):
		self.guid = guid
		self.gcId = gcId
		self.hiddenDate = hiddenDate
		self.cacheType = cacheType
		self.containerType = containerType
		self.difficulty = difficulty
		self.terrain = terrain
		self.country = country
		self.cacheOwner = cacheOwner

	def __eq__(self, x):
		return self.guid == x.guid

	@staticmethod
	def __getLevelIconUrl(level):
		if level % 10 == 0:
			return starsIconUrl % (str(level)[0])
		return starsIconUrl % (str(level)[0] + "_" + str(level)[1])

	@staticmethod
	def __getLevelText(level):
		return "%.01f" % (float(level) / 10.0)

	@staticmethod
	def getDifficultyIconUrl(difficulty):
		return Geocache.__getLevelIconUrl(difficulty)

	@staticmethod
	def getDifficultyText(difficulty):
		return Geocache.__getLevelText(difficulty)

	@staticmethod
	def getTerrainIconUrl(terrain):
		return Geocache.__getLevelIconUrl(terrain)

	@staticmethod
	def getTerrainText(terrain):
		return Geocache.__getLevelText(terrain)

	@staticmethod
	def getCacheTypeIconUrl(cacheType):
		return Geocache.cacheTypeToIconUrlMap[cacheType]

	@staticmethod
	def getCacheTypeText(cacheType):
		return Geocache.cacheTypeToTextMap[cacheType]

	@staticmethod
	def getContainerTypeIconUrl(containerType):
		return Geocache.containerTypeToIconUrlMap[containerType]

	@staticmethod
	def getContainerTypeText(containerType):
		return Geocache.containerTypeToTextMap[containerType]

class FoundGeocache(Geocache):
	def __init__(self, guid, gcId, hiddenDate,
		     cacheType, containerType,
		     difficulty, terrain, country,
		     cacheOwner, foundDate):
		Geocache.__init__(self, guid, gcId, hiddenDate,
				  cacheType, containerType,
				  difficulty, terrain, country,
				  cacheOwner)
		self.foundDate = foundDate
		self.foundWeekday = calendar.weekday(foundDate.year,
					foundDate.month, foundDate.day)

	@staticmethod
	def getFoundWeekdayText(foundWeekday):
		return calendar.day_name[foundWeekday]

def dbgOut(data, outdir="."):
	fd = file(outdir + "/gcstats.debug", "w")
	fd.write(data)
	fd.close()

def localCacheinfoGet(guid, requestId):
	try:
		fd = file(opt_localstorage + "/" + guid + "." + requestId, "r")
		info = fd.read()
		fd.close()
	except IOError:
		return None
	return info

def localCacheinfoPut(guid, requestId, info):
	try:
		fd = file(opt_localstorage + "/" + guid + "." + requestId, "w")
		fd.write(info)
		fd.close()
	except (IOError), e:
		raise gccom.GCException("Failed to write local cache info \"" +\
					requestId + "\" for " + guid)

def buildFoundGeocacheInfo(gc, guid, foundDate):
	# Download information and build a FoundGeocache object
	raw = localCacheinfoGet(guid, "details")
	if not raw:
		print "Fetching cache details for", guid
		raw = gc.getPage("/seek/cache_details.aspx?guid=" + guid)
		localCacheinfoPut(guid, "details", raw)

	m = re.match(r".*It's a ([\w\s]+) size geocache, " +\
		     r"with difficulty of ([\d\.]+), " +\
		     r"terrain of ([\d\.]+)\. " +\
		     r"It's located in ([\w\s\-,&#;]+)\..*",
		     raw, re.DOTALL)
	if not m:
		raise gccom.GCException("Detail info regex failed on " + guid)
	try:
		containerMap = {
			"not chosen"	: Geocache.CONTAINER_NOTCHOSEN,
			"micro"		: Geocache.CONTAINER_MICRO,
			"small"		: Geocache.CONTAINER_SMALL,
			"regular"	: Geocache.CONTAINER_REGULAR,
			"large"		: Geocache.CONTAINER_LARGE,
			"virtual"	: Geocache.CONTAINER_VIRTUAL,
			"other"		: Geocache.CONTAINER_OTHER,
		}
		containerType = containerMap[m.group(1).lower()]
		difficulty = int(float(m.group(2)) * 10)
		terrain = int(float(m.group(3)) * 10)
		if difficulty not in Geocache.LEVELS or\
		   terrain not in Geocache.LEVELS:
			raise ValueError
		country = htmlUnescape(m.group(4))
	except (ValueError, KeyError):
		raise gccom.GCException("Failed to parse detail info of " + guid)

	m = re.match(r".*<strong>\s+Hidden\s+:\s+</strong>\s+(\d\d/\d\d/\d\d\d\d).*",
		     raw, re.DOTALL)
	if not m:
		raise gccom.GCException("Hidden info regex failed on " + guid)
	try:
		hiddenDate = gcStringToDate(m.group(1))
	except (ValueError):
		raise gccom.GCException("Failed to parse Hidden date of " + guid)

	m = re.match(r".*<title>\s+(GC\w+)\s.*", raw, re.DOTALL)
	if not m:
		raise gccom.GCException("GC-id regex failed on " + guid)
	gcId = m.group(1)

	m = re.match(r".*title=\"About Cache Types\"><img src=\"[\w\.\-/]+\" alt=\"([\w\s\-]+)\".*",
		     raw, re.DOTALL)
	if not m:
		raise gccom.GCException("Cachetype regex failed on " + guid)
	try:
		typeMap = {
			"traditional cache"	: Geocache.CACHE_TRADITIONAL,
			"multi-cache"		: Geocache.CACHE_MULTI,
			"unknown cache"		: Geocache.CACHE_MYSTERY,
			"earthcache"		: Geocache.CACHE_EARTH,
			"virtual cache"		: Geocache.CACHE_VIRTUAL,
		}
		cacheType = typeMap[m.group(1).lower()]
	except (KeyError):
		raise gccom.GCException("Unknown cache type: " + m.group(1))

	m = re.match(r".*\(GC[\w]+\) was created by ([\w\s\-\'\"´`^°\.,;:+\*#&\|~]+) on \d\d/\d\d/\d\d\d\d.*",
		     raw, re.DOTALL)
	if not m:
		raise gccom.GCException("Cacheowner regex failed on " + guid)
	owner = htmlUnescape(m.group(1).strip())

	return FoundGeocache(guid=guid, gcId=gcId, hiddenDate=hiddenDate,
			     cacheType=cacheType, containerType=containerType,
			     difficulty=difficulty, terrain=terrain,
			     country=country, cacheOwner=owner,
			     foundDate=foundDate)

def getAllFound(gc):
	# Returns a list of FoundGC (found geocaches)
	print "Fetching \"found-it\" summary..."
	foundit = gc.getPage("/my/logs.aspx?s=1&lt=2")
	matches = re.findall(r"<td>\s*(\d\d/\d\d/\d\d\d\d)\s*</td>\s*<td>[\s\w=<>\"]*" +\
			r"<a href=\"http://www\.geocaching\.com/seek/cache_details\.aspx" +\
			r"\?guid=(" + gccom.guidRegex + r")\" class=\"lnk\">",
			foundit, re.DOTALL)
	print "Got %d \"found-it\" caches." % len(matches)
	found = []
	for (foundDate, foundGuid) in matches:
		localf = localCacheinfoGet(foundGuid, "founddate")
		if localf:
			if localf != foundDate:
				raise gccom.GCException("Local found-date mismatch for " +\
					foundGuid +\
					" (got " + foundDate + ", local " + localf + ")")
		else:
			localCacheinfoPut(foundGuid, "founddate", foundDate)

		try:
			fdate = gcStringToDate(foundDate)
		except (ValueError):
			raise gccom.GCException("Failed to parse date " + foundDate)
		found.append(buildFoundGeocacheInfo(gc, foundGuid, fdate))
	found = uniquifyList(found)
	return found

def htmlHistogramRow(fd, nrFound, count,
		     iconUrl, entityText):
	percent = float(count) * 100.0 / float(nrFound)
	fd.write('<tr>')
	fd.write('<td>')
	if iconUrl:
		fd.write('<img src="' + iconUrl + '" /> ')
	fd.write(htmlEscape(entityText) + '</td>')
	fd.write('<td>%d</td>' % count)
	fd.write('<td>%.01f %%</td>' % percent)
	fd.write('<td width="100px">')
	if count:
		fd.write('<img src="%s" width=%d height=12 />' %\
			 (barTemplateUrl, max(int(percent), 1)))
	else:
		fd.write('&nbsp;')
	fd.write('</td>')
	fd.write('</tr>')

def createHtmlHistogram(fd, foundCaches, attribute,
			entityName, headline,
			typeToIconUrl, typeToText,
			listOfPossibleTypes=[],
			sortByCount=0, onlyTop=0):
	headerDiv = '<div style="width:350px; background: #000080; ' +\
		    'font-weight: bold; line-height: 20px; font-size: ' +\
		    '13px; color: white; border: 1px solid #000000; ' +\
		    'text-align: center;">'
	tableStart = '<table border="1" width="350px" ' +\
		     'style="text-align: left; background: #EEEEFF; ' +\
		     'font-size: 13px; color: black; ">'
	byType = {}
	for possibleType in listOfPossibleTypes:
		byType[possibleType] = []
	for f in foundCaches:
		entityType = getattr(f, attribute)
		if entityType in byType.keys():
			byType[entityType].append(f)
		else:
			byType[entityType] = [f,]
	fd.write(headerDiv + headline + '</div>')
	fd.write(tableStart)
	fd.write('<tr>')
	fd.write('<td>%s</td>' % htmlEscape(entityName))
	fd.write('<td>Count</td>')
	fd.write('<td>Percent</td>')
	fd.write('<td>Hist</td>')
	fd.write('</tr>')
	types = byType.keys()
	if sortByCount:
		# Sort by "Count" column
		types.sort(key = lambda x: len(byType[x]),
			   reverse=(sortByCount < 0))
	else:
		# Sort by "entity name" column
		types.sort()
	othersCount = 0
	rows = 0
	for t in types:
		count = len(byType[t])
		if onlyTop and rows >= onlyTop:
			othersCount += count
			continue
		htmlHistogramRow(fd, len(foundCaches), count,
				 typeToIconUrl(t),
				 typeToText(t))
		rows += 1
	if othersCount:
		htmlHistogramRow(fd, len(foundCaches), othersCount,
				 None, "<others>")
	fd.write('</table><br />')

def createHtmlStats(foundCaches, outdir):
	print "Generating HTML statistics..."
	try:
		fd = file(outdir + "/gcstats.html", "w")

		foundDates = {}
		for c in foundCaches:
			if c.foundDate in foundDates:
				foundDates[c.foundDate].append(c)
			else:
				foundDates[c.foundDate] = [c,]
		nrCacheDays = len(foundDates.keys())
		mostPerDay = 0
		for d in foundDates.keys():
			mostPerDay = max(len(foundDates[d]), mostPerDay)
		avgCachesPerDay = float(len(foundCaches)) / nrCacheDays

		# Header information
		fd.write('<table border="0" style="text-align: left; ' +\
			 'background: #EEEEFF;' +\
			 'font-size: 16px; color: black; ">')
		fd.write('<tr>')
		fd.write('<td>Total number of unique cache finds:</td>')
		fd.write('<td style="font-weight: bold; ">%d</td>' % len(foundCaches))
		fd.write('</tr><tr>')
		fd.write('<td>Largest number of cache finds on one day:</td>')
		fd.write('<td style="font-weight: bold; ">%d</td>' % mostPerDay)
		fd.write('</tr><tr>')
		fd.write('<td>Average number of cache finds per caching day:</td>')
		fd.write('<td style="font-weight: bold; ">%.1f</td>' % avgCachesPerDay)
		fd.write('</tr>')
		fd.write('</table>')
		fd.write('<br />')

		# Tables
		fd.write('<table border="0">')
		fd.write('<tr>')
		fd.write('<td valign="top">')
		createHtmlHistogram(fd, foundCaches, "cacheType",
				    "Type", "Finds by cache type",
				    lambda t: Geocache.getCacheTypeIconUrl(t),
				    lambda t: Geocache.getCacheTypeText(t),
				    sortByCount=-1)
		fd.write('</td><td valign="top">')
		createHtmlHistogram(fd, foundCaches, "containerType",
				    "Container", "Finds by container type",
				    lambda t: Geocache.getContainerTypeIconUrl(t),
				    lambda t: Geocache.getContainerTypeText(t),
				    listOfPossibleTypes=Geocache.containerTypeToTextMap.keys())
		fd.write('</td>')
		fd.write('</tr><tr>')
		fd.write('<td valign="top">')
		createHtmlHistogram(fd, foundCaches, "difficulty",
				    "Difficulty", "Finds by difficulty level",
				    lambda t: Geocache.getDifficultyIconUrl(t),
				    lambda t: Geocache.getDifficultyText(t),
				    listOfPossibleTypes=Geocache.LEVELS)
		fd.write('</td><td valign="top">')
		createHtmlHistogram(fd, foundCaches, "terrain",
				    "Terrain", "Finds by terrain level",
				    lambda t: Geocache.getTerrainIconUrl(t),
				    lambda t: Geocache.getTerrainText(t),
				    listOfPossibleTypes=Geocache.LEVELS)
		fd.write('</td>')
		fd.write('</tr><tr>')
		fd.write('<td valign="top">')
		createHtmlHistogram(fd, foundCaches, "foundWeekday",
				    "Weekday", "Finds by day of week",
				    lambda t: None,
				    lambda t: FoundGeocache.getFoundWeekdayText(t),
				    listOfPossibleTypes=[x for x in range(7)])
		fd.write('</td><td valign="top">')
		createHtmlHistogram(fd, foundCaches, "cacheOwner",
				    "Cache owner", "Finds by cache owner (Top 10)",
				    lambda t: None,
				    lambda t: t,
				    sortByCount=-1, onlyTop=10)
		fd.write('</td>')
		fd.write('</tr>')
		fd.write('</table>')

		fd.write('\n<p style="font-size: 10px; ">Generated by <a href="' +\
			 'http://bu3sch.de/joomla/index.php/geocaching-tools' +\
			 '">gcstats.py</a> on ' + time.asctime() + '</p>')
		fd.close()
	except (IOError), e:
		raise gccom.GCException("Failed to write HTML stats: " + e.strerror)

def createStats(user, password, outdir):
	gc = gccom.GC(user, password)

	found = getAllFound(gc)
	createHtmlStats(found, outdir)

	gc.logout()

def usage():
	print "Geocaching.com stats tool"
	print ""
	print "-u|--user USER             The gc.com username"
	print "-p|--password PASS         The gc.com password"
	print "-H|--http                  Use HTTP instead of HTTPS"
	print ""
	print "-o|--outdir                Output directory (defaults to PWD)"
	print "-l|--localstorage          Local storage directory (defaults to $outdir/gcstats)"
	print ""
	print "-h|--help                  Print this help text"

def main():
	global opt_localstorage
	opt_user = None
	opt_password = None
	opt_outdir = "."

	try:
		(opts, args) = getopt.getopt(sys.argv[1:],
			"hu:p:Ho:l:",
			[ "help", "user=", "password=", "http", "outdir=",
			  "localstorage=", "debug", ])
	except getopt.GetoptError:
		usage()
		return 1
	for (o, v) in opts:
		if o == "--debug":
			gccom.opt_debug = True
		if o in ("-h", "--help"):
			usage()
			return 0
		if o in ("-u", "--user"):
			opt_user = v
		if o in ("-p", "--password"):
			opt_password = v
		if o in ("-H", "--http"):
			gccom.opt_useHTTPS = False;
		if o in ("-o", "--outdir"):
			opt_outdir = v
		if o in ("-l", "--localstorage"):
			opt_localstorage = v
	if not opt_user:
		opt_user = raw_input("Geocaching.com username: ")
	if not opt_password:
		opt_password = raw_input("Geocaching.com password: ")
	if not opt_localstorage:
		opt_localstorage = opt_outdir + "/gcstats"
	mkdir_recursive(opt_localstorage)

	try:
		createStats(opt_user, opt_password, opt_outdir)
	except gccom.GCException, e:
		print e
		return 1
	except gccom.socket.error, e:
		print "Socket error:"
		print e
		return 1
	except gccom.httplib.HTTPException, e:
		print "HTTP error:"
		print e.__class__
		return 1
	except IOError, e:
		print "IO error:", e
		return 1

if __name__ == "__main__":
	sys.exit(main())
