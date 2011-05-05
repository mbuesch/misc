#!/usr/bin/env python
# vim: set fileencoding=UTF-8 :
"""
# Geocaching.com stats tool
# (c) Copyright 2010-2011 Michael Buesch
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
import math


barTemplateUrl		= "http://img.geocaching.com/cache/log/f8db1278-8482-4aec-9dff-a16659e9d647.jpg"
cacheTypeIconUrl	= "http://www.geocaching.com/images/wpttypes/sm/%s.gif"
containerTypeIconUrl	= "http://www.geocaching.com/images/icons/container/%s.gif"
starsIconUrl		= "http://www.geocaching.com/images/stars/stars%s.gif"

urlRegex		= r'[\w\.\-:&%=\?/]+'

htmlBgColor		= "#D0D0E0"
htmlTitleBgColor	= "#606090"
htmlTableWidth		= 350

opt_localstorage = None
opt_offline = False


class Coordinate:
	COORD_REGEX = r'([NSEOW])\s+(\d+)\s*°?\s+([\d+\.]+)\s*\'?'
	COORD_REGEX_RAW = COORD_REGEX.replace('(', '').replace(')', '')

	def __init__(self, latString, lonString):
		self.lat = self.__parseCoord(latString)
		self.lon = self.__parseCoord(lonString)

	def __parseCoord(self, coordString):
		try:
			m = re.match(r'\s*' + self.COORD_REGEX + r'\s*',
				     coordString.upper())
			if not m:
				raise ValueError
			c = m.group(1)
			if c == "O":
				c = "E"
			integer = int(m.group(2))
			fractional = float(m.group(3))
			multiplier = 1
			if c in ("W", "S"):
				multiplier = -1
			return (float(integer) + fractional / 60.0) * multiplier
		except ValueError:
			raise gccom.GCException("Failed to parse coodinate")

	def __distance(self, coord):
		lat0 = math.radians(self.lat)
		lon0 = math.radians(self.lon)
		lat1 = math.radians(coord.lat)
		lon1 = math.radians(coord.lon)
		return math.acos((math.cos(lat0) * math.cos(lat1) * math.cos(lon1 - lon0)) +
				 (math.sin(lat0) * math.sin(lat1)))

	def distanceInKm(self, coord):
		return self.__distance(coord) * 6371.0

	def __repr__(self):
		return "latitude: %f  longitude: %f" % (self.lat, self.lon)

class IntRange:
	UNLIMITED = "nan"

	def __init__(self,
		     minValue=UNLIMITED,
		     maxValue=UNLIMITED,
		     prefix="", suffix=""):
		self.minValue = minValue
		self.maxValue = maxValue
		self.prefix = prefix
		self.suffix = suffix

	def valueIsInRange(self, val):
		if self.minValue == self.UNLIMITED and\
		   self.maxValue == self.UNLIMITED:
			return True
		if self.minValue == self.UNLIMITED:
			return val <= self.maxValue
		if self.maxValue == self.UNLIMITED:
			return val >= self.minValue
		return val >= self.minValue and val <= self.maxValue

	def __eq__(self, intRange):
		return self.minValue == intRange.minValue and\
		       self.maxValue == intRange.maxValue

	def __repr__(self):
		if self.minValue == self.UNLIMITED and\
		   self.maxValue == self.UNLIMITED:
			return "unlimited"
		if self.minValue == self.UNLIMITED:
			return "<= %s%d%s" % (self.prefix, self.maxValue, self.suffix)
		if self.maxValue == self.UNLIMITED:
			return ">= %s%d%s" % (self.prefix, self.minValue, self.suffix)
		return "%s%d - %s%d%s" % (self.prefix, self.minValue,
					  self.prefix, self.maxValue, self.suffix)

	def __hash__(self):
		minVal = self.minValue
		maxVal = self.maxValue
		if minVal == self.UNLIMITED:
			minVal = 0xFFFF
		if maxVal == self.UNLIMITED:
			maxVal = 0xFFFF
		assert((minVal & ~0xFFFF) == 0)
		assert((minVal & ~0xFFFF) == 0)
		return minVal | (maxVal << 16)

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

	distanceRanges = (
		IntRange(maxValue=9, suffix=" km"),
		IntRange(minValue=10, maxValue=19, suffix=" km"),
		IntRange(minValue=20, maxValue=29, suffix=" km"),
		IntRange(minValue=30, maxValue=39, suffix=" km"),
		IntRange(minValue=40, maxValue=49, suffix=" km"),
		IntRange(minValue=50, maxValue=99, suffix=" km"),
		IntRange(minValue=100, maxValue=199, suffix=" km"),
		IntRange(minValue=200, maxValue=499, suffix=" km"),
		IntRange(minValue=500, maxValue=999, suffix=" km"),
		IntRange(minValue=1000, suffix=" km"),
	)

	def __init__(self, guid):
		self.guid = guid
		self.gcId = None
		self.hiddenDate = None
		self.cacheType = None
		self.containerType = None
		self.difficulty = None
		self.terrain = None
		self.country = None
		self.cacheOwner = None
		self.cacheOwnerUrl = None
		self.homeDistance = None
		self.homeDistanceRange = None

	def setGcID(self, gcId):
		self.gcId = gcId
	def setHiddenDate(self, hiddenDate):
		self.hiddenDate = hiddenDate
	def setCacheType(self, cacheType):
		self.cacheType = cacheType
	def setContainerType(self, containerType):
		self.containerType = containerType
	def setDifficulty(self, difficulty):
		self.difficulty = difficulty
	def setTerrain(self, terrain):
		self.terrain = terrain
	def setCountry(self, country):
		self.country = country
	def setCacheOwner(self, owner):
		self.cacheOwner = owner
	def setCacheOwnerUrl(self, url):
		self.cacheOwnerUrl = url
	def setHomeDistance(self, distance):
		self.homeDistance = distance
		for rnge in self.distanceRanges:
			if rnge.valueIsInRange(int(round(distance))):
				self.homeDistanceRange = rnge
				break
		else:
			assert(False)

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
	def __init__(self, guid):
		Geocache.__init__(self, guid)
		self.foundDate = None
		self.foundWeekday = None

	def setFoundDate(self, foundDate):
		self.foundDate = foundDate
		self.foundWeekday = calendar.weekday(foundDate.year,
					foundDate.month, foundDate.day)

	@staticmethod
	def getFoundWeekdayText(foundWeekday):
		return calendar.day_name[foundWeekday]

class HiddenGeocache(Geocache):
	def __init__(self, guid):
		Geocache.__init__(self, guid)

def localCacheinfoGet(itemId, requestId):
	try:
		fd = file(opt_localstorage + "/" + itemId + "." + requestId, "r")
		info = fd.read()
		fd.close()
	except IOError:
		return None
	return info

def localCacheinfoPut(itemId, requestId, info):
	try:
		fd = file(opt_localstorage + "/" + itemId + "." + requestId, "w")
		fd.write(info)
		fd.close()
	except (IOError), e:
		raise gccom.GCException("Failed to write local cache info " +\
					itemId + "." + requestId)

def fetchGenericGeocacheInfo(gc, cache, homeCoord):
	guid = cache.guid
	raw = localCacheinfoGet(guid, "details")
	if not raw:
		print "Fetching cache details for", guid
		if opt_offline:
			raise gccom.GCException("Offline: Details for " + guid +\
				" not in local cache")
		raw = gc.getPage("/seek/cache_details.aspx?guid=" + guid)
		localCacheinfoPut(guid, "details", raw)

	m = re.match(r'.*\((GC\w+)\) was created by ([\w\s\-\'\"´`^°\.,;:+\*#&\|~]+) ' \
		     r'on \d\d/\d\d/\d\d\d\d\. ' \
		     r'It\'s a ([\w\s]+) size geocache, ' \
		     r'with difficulty of ([\d\.]+), ' \
		     r'terrain of ([\d\.]+)\. ' \
		     r'It\'s located in ([\w\s\-,&#;]+)\..*',
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
		cache.setGcID(m.group(1))
		cache.setCacheOwner(htmlUnescape(m.group(2)).lower())
		cache.setContainerType(containerMap[m.group(3).lower()])
		difficulty = int(float(m.group(4)) * 10)
		terrain = int(float(m.group(5)) * 10)
		if difficulty not in Geocache.LEVELS or\
		   terrain not in Geocache.LEVELS:
			raise ValueError
		cache.setDifficulty(difficulty)
		cache.setTerrain(terrain)
		cache.setCountry(htmlUnescape(m.group(6)))
	except (ValueError, KeyError):
		raise gccom.GCException("Failed to parse detail info of " + guid)

	m = re.match(r'.*<strong>\s+Hidden\s+:\s+</strong>\s+(\d\d/\d\d/\d\d\d\d).*',
		     raw, re.DOTALL)
	if not m:
		raise gccom.GCException("Hidden info regex failed on " + guid)
	try:
		cache.setHiddenDate(gcStringToDate(m.group(1)))
	except (ValueError):
		raise gccom.GCException("Failed to parse Hidden date of " + guid)

	m = re.match(r'.*title="About Cache Types"><img src="' + urlRegex +\
		     r'" alt="([\w\s\-]+)".*',
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
		cache.setCacheType(typeMap[m.group(1).lower()])
	except (KeyError):
		raise gccom.GCException("Unknown cache type: " + m.group(1))

	m = re.match(r'.*<strong>\s+A\s+cache\s+</strong>\s+by\s+<a href="(' +\
		     urlRegex + r')">.*',
		     raw, re.DOTALL)
	if not m:
		raise gccom.GCException("Cacheowner-URL regex failed on " + guid)
	cache.setCacheOwnerUrl(m.group(1))

	m = re.match(r'.*<span id="ctl00_ContentBody_LatLon" style="font-weight:bold;">'
		     r'(' + Coordinate.COORD_REGEX_RAW + r')' +\
		     r'(' + Coordinate.COORD_REGEX_RAW + r')' +\
		     r'</span>.*',
		     raw, re.DOTALL)
	if not m:
		raise gccom.GCException("Cache location regex failed on " + guid)
	lat = m.group(1)
	lon = m.group(2)
	cacheCoord = Coordinate(latString=lat, lonString=lon)
	cache.setHomeDistance(cacheCoord.distanceInKm(homeCoord))

def getAllFound(gc, homeCoord):
	# Returns a list of FoundGeocache objects
	print "Fetching found geocaches..."
	if opt_offline:
		foundit = localCacheinfoGet("found", "index")
		if not foundit:
			raise gccom.GCException("Offline: Failed to get cached found-index")
	else:
		foundit = gc.getPage("/my/logs.aspx?s=1&lt=2")
		localCacheinfoPut("found", "index", foundit)
	matches = re.findall(r'<td>\s*(\d\d/\d\d/\d\d\d\d)\s*</td>\s*'
			     r'<td>\s*'
			     r'(?:<span class="Strike OldWarning">)?'
			     r'<a href="http://www.geocaching.com/seek/cache_details.aspx'
			     r'\?guid=(' + gccom.guidRegex + r')"'
			     r'\s*class="ImageLink">',
			     foundit, re.DOTALL)
	print "Got %d found caches." % len(matches)
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
		cache = FoundGeocache(foundGuid)
		cache.setFoundDate(fdate)
		fetchGenericGeocacheInfo(gc, cache, homeCoord)
		found.append(cache)
	found = uniquifyList(found)
	return found

def getAllHidden(gc, homeCoord):
	# Returns a list of HiddenGeocache objects
	print "Fetching hidden geocaches..."
	if opt_offline:
		hiddenIndex = localCacheinfoGet("hidden", "index")
		if not hiddenIndex:
			raise gccom.GCException("Offline: Failed to get cached hidden-index")
	else:
		hiddenIndex = gc.getPage("/my/owned.aspx")
		localCacheinfoPut("hidden", "index", hiddenIndex)
	matches = re.findall(r'<td><a href="'
			     r'http://www\.geocaching\.com/seek/cache_details\.aspx\?guid='
			     r'(' + gccom.guidRegex + r')"\s*title="',
			     hiddenIndex, re.DOTALL)
	print "Got %d hidden caches." % len(matches)
	hidden = []
	for guid in matches:
		cache = HiddenGeocache(guid)
		fetchGenericGeocacheInfo(gc, cache, homeCoord)
		hidden.append(cache)
	assert(len(hidden) == len(uniquifyList(hidden)))
	return hidden

def getHomeCoordinates(gc):
	print "Fetching home coordinates..."
	if opt_offline:
		accountHome = localCacheinfoGet("account", "home")
		if not accountHome:
			raise gccom.GCException("Offline: Failed to get cached home coordinate")
	else:
		accountHome = gc.getPage("/account/default.aspx")
		localCacheinfoPut("account", "home", accountHome)
	m = re.match(r'.*Home Location \((' +\
		     Coordinate.COORD_REGEX_RAW + r')\s*(' +\
		     Coordinate.COORD_REGEX_RAW + r')\)</a>.*',
		     accountHome, re.DOTALL)
	if not m:
		raise gccom.GCException("Failed to parse home coordinates")
	lat = m.group(1)
	lon = m.group(2)
	homeCoord = Coordinate(latString=lat, lonString=lon)
	print "Home:", homeCoord
	return homeCoord

class HtmlTable:
	def __init__(self, fd, nrColumns, headline=None, width=-1):
		self.fd = fd
		self.nrColumns = nrColumns
		self.width = width

		styleWidth = ""
		if width >= 0:
			styleWidth = "width: %dpx;" % width
		fd.write('<table border="1" '
			 'style="margin: 5px; border: 1px solid #FFFFFF; %s">' % styleWidth)
		if headline:
			fd.write('<th colspan="%d" ' \
				 'style="%s background: %s; font-weight: bold; ' \
				 'line-height: 20px; font-size: 13px; ' \
				 'color: white; text-align: center; ">' %\
				 (nrColumns, styleWidth, htmlTitleBgColor))
			fd.write(htmlEscape(headline))
			fd.write('</th>')

	def addRow(self, *columns):
		assert(len(columns) == self.nrColumns)
		style = 'text-align: left; background: %s; ' % htmlBgColor +\
			'font-size: 13px; color: black;'
		self.fd.write('<tr style="%s">' % style)
		for column in columns:
			if not column.startswith('<td'):
				self.fd.write('<td>')
			self.fd.write(column)
			self.fd.write('</td>')
		self.fd.write('</tr>')

	def end(self):
		self.fd.write('</table>')
		self.fd = None

def htmlHistogramRow(tab, nrFound, count,
		     entityIconUrl, entityText, entityUrl):
	percent = float(count) * 100.0 / float(nrFound)
	col0 = ''
	if entityIconUrl:
		col0 += '<img src="' + entityIconUrl + '" /> '
	if entityUrl:
		col0 += '<a href="' + entityUrl + '" target="_blank">'
	col0 += htmlEscape(entityText)
	if entityUrl:
		col0 += '</a>'
	col1 = '%d' % count
	col2 = '%.01f %%' % percent
	col3 = '<td width="100px">'
	if count:
		col3 += '<img src="%s" width=%d height=12 />' %\
			(barTemplateUrl, max(int(percent), 1))
	else:
		col3 += '&nbsp;'
	tab.addRow(col0, col1, col2, col3)

def createHtmlHistogram(fd, foundCaches, attribute,
			entityName, headline,
			typeToIconUrl=lambda t: None,
			typeToText=lambda t: None,
			typeToTextUrl=lambda t: None,
			listOfPossibleTypes=[],
			sortByCount=0, onlyTop=0):
	byType = {}
	for possibleType in listOfPossibleTypes:
		byType[possibleType] = []
	for f in foundCaches:
		entityType = getattr(f, attribute)
		if entityType in byType.keys():
			byType[entityType].append(f)
		else:
			byType[entityType] = [f,]
	tab = HtmlTable(fd, nrColumns=4, headline=headline, width=htmlTableWidth)
	tab.addRow("<b>" + htmlEscape(entityName) + "</b>",
		   "<b>Count</b>", "<b>Percent</b>",
		   "<b>Hist</b>")
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
		htmlHistogramRow(tab, len(foundCaches), count,
				 typeToIconUrl(t),
				 typeToText(t),
				 typeToTextUrl(t))
		rows += 1
	if othersCount:
		htmlHistogramRow(tab, len(foundCaches), othersCount,
				 None, "others", None)
	tab.end()

def createHtmlStatsHistograms(fd, foundCaches):
	fd.write('<table border="0">')
	fd.write('<tr>')
	fd.write('<td valign="top">')
	createHtmlHistogram(fd, foundCaches, "cacheType",
			    "Type", "Finds by cache type",
			    typeToIconUrl=lambda t: Geocache.getCacheTypeIconUrl(t),
			    typeToText=lambda t: Geocache.getCacheTypeText(t),
			    sortByCount=-1)
	fd.write('<br /></td><td valign="top">')
	createHtmlHistogram(fd, foundCaches, "containerType",
			    "Container", "Finds by container type",
			    typeToIconUrl=lambda t: Geocache.getContainerTypeIconUrl(t),
			    typeToText=lambda t: Geocache.getContainerTypeText(t),
			    listOfPossibleTypes=Geocache.containerTypeToTextMap.keys())
	fd.write('</td>')
	fd.write('</tr><tr>')
	fd.write('<td valign="top">')
	createHtmlHistogram(fd, foundCaches, "difficulty",
			    "Difficulty", "Finds by difficulty level",
			    typeToIconUrl=lambda t: Geocache.getDifficultyIconUrl(t),
			    typeToText=lambda t: Geocache.getDifficultyText(t),
			    listOfPossibleTypes=Geocache.LEVELS)
	fd.write('<br /></td><td valign="top">')
	createHtmlHistogram(fd, foundCaches, "terrain",
			    "Terrain", "Finds by terrain level",
			    typeToIconUrl=lambda t: Geocache.getTerrainIconUrl(t),
			    typeToText=lambda t: Geocache.getTerrainText(t),
			    listOfPossibleTypes=Geocache.LEVELS)
	fd.write('<br /></td>')
	fd.write('</tr><tr>')
	fd.write('<td valign="top">')
	createHtmlHistogram(fd, foundCaches, "foundWeekday",
			    "Weekday", "Finds by day of week",
			    typeToText=lambda t: FoundGeocache.getFoundWeekdayText(t),
			    listOfPossibleTypes=range(7))

	weekday = 0
	weekend = 0
	for c in foundCaches:
		if c.foundWeekday in range(5):
			weekday += 1
		else:
			weekend += 1
	tab = HtmlTable(fd, nrColumns=2, width=htmlTableWidth)
	tab.addRow('Weekend finds: ', '%d (%.01f %%)' %\
		   (weekend, float(weekend) * 100.0 / len(foundCaches)))
	tab.addRow('Weekday finds: ', '%d (%.01f %%)' %\
		   (weekday, float(weekday) * 100.0 / len(foundCaches)))
	tab.end()

	fd.write('<br /></td><td valign="top">')
	createHtmlHistogram(fd, foundCaches, "homeDistanceRange",
			    "Distance", "Finds by distance from home",
			    typeToText=lambda t: str(t),
			    listOfPossibleTypes=Geocache.distanceRanges)
	fd.write('<br /></td>')
	fd.write('</tr><tr>')
	fd.write('<td valign="top">')
	createHtmlHistogram(fd, foundCaches, "country",
			    "Location", "Finds by cache location",
			    typeToText=lambda t: t,
			    sortByCount=-1)
	fd.write('<br /></td><td valign="top">')
	createHtmlHistogram(fd, foundCaches, "cacheOwner",
			    "Cache owner", "Finds by cache owner (Top 10)",
			    typeToText=lambda t: t,
			    typeToTextUrl=lambda t: [x for x in foundCaches if x.cacheOwner == t][0].cacheOwnerUrl,
			    sortByCount=-1, onlyTop=10)
	fd.write('<br /></td>')
	fd.write('</tr>')
	fd.write('</table>')

def createHtmlStatsHeader(fd, foundCaches, hiddenCaches):
	tab = HtmlTable(fd, nrColumns=2)
	tab.addRow("Total number of unique cache finds:",
		   "<b>%d</b>" % len(foundCaches))
	tab.addRow("Total number of hidden caches:",
		   "<b>%d</b>" % len(hiddenCaches))
	tab.end()
	fd.write('<br />')

def createHtmlStatsMisc(fd, foundCaches):
	foundDates = {}
	firstDate = None
	lastDate = None
	for c in foundCaches:
		if firstDate is None or c.foundDate < firstDate:
			firstDate = c.foundDate
		if lastDate is None or c.foundDate > lastDate:
			lastDate = c.foundDate
		if c.foundDate in foundDates:
			foundDates[c.foundDate].append(c)
		else:
			foundDates[c.foundDate] = [c,]
	nrCalendarDays = lastDate.toordinal() - firstDate.toordinal()
	nrCacheDays = len(foundDates.keys())
	mostPerDay = 0
	leastPerDay = 0xFFFFFFFF
	for d in foundDates.keys():
		mostPerDay = max(len(foundDates[d]), mostPerDay)
		leastPerDay = min(len(foundDates[d]), leastPerDay)
	avgCachesPerDay = float(len(foundCaches)) / nrCacheDays

	tab = HtmlTable(fd, nrColumns=2, headline="Miscellaneous statistics")
	tab.addRow("Number of caching days:",
		   "<b>%d caching days out of %d calendar days (%.01f %%)</b>" % \
		   (nrCacheDays, nrCalendarDays,
		    float(nrCacheDays) * 100.0 / float(nrCalendarDays)))
	tab.addRow("Average number of cache finds per caching day:",
		   "<b>%.1f</b>" % avgCachesPerDay)
	tab.addRow("Largest number of cache finds on one caching day:",
		   "<b>%d</b>" % mostPerDay)
	tab.addRow("Lowest number of cache finds on one caching day:",
		   "<b>%d</b>" % leastPerDay)
	tab.end()

def createHtmlStats(foundCaches, hiddenCaches, outdir):
	print "Generating HTML statistics..."
	try:
		fd = file(outdir + "/gcstats.html", "w")

		if foundCaches:
			createHtmlStatsHeader(fd, foundCaches, hiddenCaches)
			createHtmlStatsHistograms(fd, foundCaches)
			createHtmlStatsMisc(fd, foundCaches)

		fd.write('\n<p style="font-size: 10px; ">Generated by <a href="' \
			 'http://bues.ch/cms/hacking/geocaching.html' \
			 '">gcstats.py</a> on ' +\
			 time.strftime("%a, %d %b %Y %T %z") + '</p>')
		fd.close()
	except (IOError), e:
		raise gccom.GCException("Failed to write HTML stats: " + e.strerror)

def createStats(user, password, outdir, debug):
	gc = None
	if not opt_offline:
		gc = gccom.GC(user, password, debug=debug)

	homeCoord = getHomeCoordinates(gc)
	found = getAllFound(gc, homeCoord)
	hidden = getAllHidden(gc, homeCoord)
	createHtmlStats(found, hidden, outdir)

	if not opt_offline:
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
	print "-O|--offline               Offline mode. Only use local cache information."
	print ""
	print "-h|--help                  Print this help text"

def main():
	global opt_localstorage
	global opt_offline
	opt_user = None
	opt_password = None
	opt_outdir = "."
	opt_debug = False

	try:
		(opts, args) = getopt.getopt(sys.argv[1:],
			"hu:p:Ho:l:O",
			[ "help", "user=", "password=", "http", "outdir=",
			  "localstorage=", "debug", "offline", ])
	except getopt.GetoptError:
		usage()
		return 1
	for (o, v) in opts:
		if o == "--debug":
			opt_debug = True
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
		if o in ("-O", "--offline"):
			opt_offline = True
	if not opt_offline:
		if not opt_user:
			opt_user = raw_input("Geocaching.com username: ")
		if not opt_password:
			opt_password = raw_input("Geocaching.com password: ")
	if not opt_localstorage:
		opt_localstorage = opt_outdir + "/gcstats"
	mkdir_recursive(opt_localstorage)

	try:
		createStats(opt_user, opt_password, opt_outdir, opt_debug)
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
