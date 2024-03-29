"""
# gamestats.py
# Copyright (c) 2010-2011 Michael Buesch <m@bues.ch>
# Licensed under the GNU/GPL version 2 or later.
"""

import sys
import re
import datetime
import errno
import getopt
import pygraphviz as gv


debug = False

re_iso_timestamp = re.compile(r'(\d\d\d\d)-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)\.(\d\d\d\d\d\d)')
ISO_TIMESTAMP_LEN = 26


class Warn(Exception): pass
class Error(Exception): pass

def debugMsg(msg):
	if debug:
		print(msg)

def clearscreen():
	sys.stdout.write("\33[2J\33[0;0H")
	sys.stdout.flush()

def filterPlayers(options, players):
	if options.filterLeft:
		players = [p for p in players if not p.disconnectedInGame]
	if options.filterJoinIG:
		players = [p for p in players if not p.connectedInGame]
	return players

class Options(object):
	def __init__(self):
		self.myname = None
		self.liveUpdate = False
		self.alwaysSortByFrags = False
		self.filterLeft = False
		self.filterJoinIG = False
		self.splitLogs = False
		self.rawlogdir = None
		self.fragGraphDir = None

class Event(object):
	def __init__(self, timestamp):
		self.timestamp = timestamp

class Events(object):
	def __init__(self, options):
		self.options = options
		self.events = []

	def addEvent(self, event):
		self.events.append(event)

	def countAll(self):
		return len(self.events)

class PlayerEvents(object):
	def __init__(self, options, players={}):
		self.options = options
		self.players = players.copy()

	def copy(self):
		return PlayerEvents(self.options, self.players)

	def extend(self, other):
		self.players.update(other.players)

	def addEvent(self, event, player):
		self.players.setdefault(player, []).append(event)

	def countAll(self):
		return sum(len(evs) for evs in self.players.values())

	def countFor(self, player):
		return len(self.players[player])

	def getPlayersUnfiltered(self):
		return list(self.players.keys())

	def getPlayers(self):
		return filterPlayers(self.options, self.getPlayersUnfiltered())

class Player(object):
	def __init__(self, name, realName, game):
		self.name = name
		self.realName = realName
		self.game = game
		self.frags = PlayerEvents(game.options)
		self.teamkills = PlayerEvents(game.options)
		self.deaths = PlayerEvents(game.options)
		self.ctfScores = Events(game.options)
		self.ctfDrops = Events(game.options)
		self.ctfPicks = Events(game.options)
		self.ctfStolen = Events(game.options)
		self.ctfReturns = Events(game.options)
		self.suicides = Events(game.options)
		self.connectedInGame = False
		self.disconnectedInGame = False
		#FIXME Is there a way to detect connectedInGame for self?

	def connected(self):
		if not self.game.ended and self.game.hadFirstBlood:
			self.connectedInGame = True
			self.disconnectedInGame = False

	def disconnected(self):
		if not self.game.ended:
			self.disconnectedInGame = True

	def addFrag(self, timestamp, fraggedPlayer):
		if not self.game.ended:
			self.frags.addEvent(Event(timestamp), fraggedPlayer)
			fraggedPlayer.__addDeath(timestamp, self)

	def getFrags(self):
		# Returns PlayerEvents instance
		return self.frags

	def getNrFrags(self):
		return self.getFrags().countAll() - self.getNrTeamkills()

	def addTeamkill(self, timestamp, fraggedPlayer):
		if not self.game.ended:
			self.teamkills.addEvent(Event(timestamp), fraggedPlayer)
			fraggedPlayer.__addDeath(timestamp, self)

	def getTeamkills(self):
		# Returns PlayerEvents instance
		return self.teamkills

	def getNrTeamkills(self):
		return self.getTeamkills().countAll()

	def getKills(self):
		# Returns a PlayerEvents instance with all kills (= frags + teamkills)
		kills = self.getFrags().copy()
		kills.extend(self.getTeamkills())
		return kills

	def __addDeath(self, timestamp, killer):
		if not self.game.ended:
			self.deaths.addEvent(Event(timestamp), killer)

	def getDeaths(self):
		# Returns PlayerEvents instance
		return self.deaths

	def getNrDeaths(self):
		return self.getDeaths().countAll()

	def addSuicide(self, timestamp):
		if not self.game.ended:
			self.suicides.addEvent(Event(timestamp))

	def getNrSuicides(self):
		return self.suicides.countAll()

	def addCtfScore(self, timestamp):
		if not self.game.ended and self.game.isCtf():
			self.ctfScores.addEvent(Event(timestamp))

	def getNrCtfScores(self):
		return self.ctfScores.countAll()

	def addCtfDrop(self, timestamp):
		if not self.game.ended and self.game.isCtf():
			self.ctfDrops.addEvent(Event(timestamp))

	def getNrCtfDrops(self):
		return self.ctfDrops.countAll()

	def addCtfPick(self, timestamp):
		if not self.game.ended and self.game.isCtf():
			self.ctfPicks.addEvent(Event(timestamp))

	def getNrCtfPicks(self):
		return self.ctfPicks.countAll()

	def addCtfSteal(self, timestamp):
		if not self.game.ended and self.game.isCtf():
			self.ctfStolen.addEvent(Event(timestamp))

	def getNrCtfStolen(self):
		return self.ctfStolen.countAll()

	def addCtfReturn(self, timestamp):
		if not self.game.ended and self.game.isCtf():
			self.ctfReturns.addEvent(Event(timestamp))

	def getNrCtfReturns(self):
		return self.ctfReturns.countAll()

	def rename(self, newName):
		self.game.renamePlayer(self.realName, newName)

	def generateStats(self):
		extra = []
		if self.connectedInGame:
			extra.append("join-ig")
		if self.disconnectedInGame:
			extra.append("left")
		extra = " (" + ", ".join(extra) + ")" if extra else ""
		name = self.realName
		if self.name == "self":
			name = "==> " + name + " <=="
		frags = self.getNrFrags()
		tks = self.getNrTeamkills()
		deaths = self.getNrDeaths()
		suicides = self.getNrSuicides()
		ctf = ""
		if self.game.isCtf():
			ctfScores = self.getNrCtfScores()
			ctfDrops = self.getNrCtfDrops()
			ctfPicks = self.getNrCtfPicks()
			ctfStolen = self.getNrCtfStolen()
			ctfReturns = self.getNrCtfReturns()
			ctf = " %2.1d sco %2.1d ret %2.1d drp %2.1d stol %2.1d pck" %\
				(ctfScores, ctfReturns, ctfDrops, ctfStolen, ctfPicks)
		return "%20s: %3.1d frg %2.1d tk %3.1d dth %2.1d sk%s%s" %\
			(name, frags, tks, deaths, suicides, ctf, extra)

class Game(object):
	def __init__(self, options, timestamp, mode, mapname, selfIDs=[]):
		self.options = options
		self.mode = mode.lower()
		self.mapname = mapname
		self.hadFirstBlood = False
		self.started = timestamp
		self.ended = False
		self.selfIDs = selfIDs
		myname = self.options.myname if self.options.myname else "self"
		self.players = {
			"self"	: Player("self", myname, self)
		}
		debugMsg("New game: mode=%s" % mode)

	def __saneName(self, name):
		return re.sub(r'\s+', '-', name)

	def getSaneName(self, sep="-"):
		items = []
		items.append(self.__saneName(self.started.strftime("%Y%m%d-%H%M%S")))
		items.append(self.__saneName(self.mode))
		items.append(self.__saneName(self.mapname))
		return sep.join(items)

	def __mkPlayerKey(self, name):
		return "player_" + name

	def player(self, name):
		if self.options.myname and self.options.myname == name:
			return self.me()
		key = self.__mkPlayerKey(name)
		return self.players.setdefault(key, Player(key, name, self))

	def me(self):
		return self.players["self"]

	def playerOrMe(self, name):
		if not name or name in self.selfIDs:
			return self.me()
		return self.player(name)

	def getPlayersUnfiltered(self):
		return list(self.players.values())

	def getPlayers(self):
		return filterPlayers(self.options, self.getPlayersUnfiltered())

	def renamePlayer(self, oldName, newName):
		player = self.players.pop(self.__mkPlayerKey(oldName))
		player.name = self.__mkPlayerKey(newName)
		player.realName = newName
		self.players[player.name] = player

	def isCtf(self):
		return self.mode in ("ctf", "insta ctf", "efficiency ctf")

	def generateStats(self):
		ret = []
		if self.ended:
			prefix = "<GAME ENDED %s> " % self.ended.ctime()
		else:
			if self.options.liveUpdate:
				prefix = "<game running> "
			else:
				prefix = "<GAME INTERRUPTED> "
		ret.append("%s'%s' on map '%s' started %s:" %\
			   (prefix, self.mode, self.mapname, self.started.ctime()))
		players = list(self.getPlayers())[:]
		if self.isCtf() and not self.options.alwaysSortByFrags:
			key = lambda p: p.getNrCtfScores()
		else:
			key = lambda p: p.getNrFrags()
		players.sort(key=key, reverse=True)
		for player in players:
			ret.append(player.generateStats())
		return "\n".join(ret)

class Parser(object):
	def __init__(self, options):
		self.options = options
		self.currentGame = None
		self.games = []

	def parseLine(self, line):
		if not self.lineHasTimestamp(line):
			now = datetime.datetime.now().isoformat()
			line = "%s/%s" % (now, line)
		lineNoStamp, stamp = self.parseIsoTimestamp(line)
		self.doParseLine(stamp, lineNoStamp)
		if not line.endswith("\n"):
			line += "\n"
		writeRawLog(self.options.rawlogdir, line)

	def doParseLine(self, timestamp, line):
		# This is the actual game specific parser.
		# Reimplement this method in the subclass.
		raise NotImplementedError

	def parseFile(self, fd):
		while True:
			try:
				line = fd.readline()
				if not line:
					break
				self.parseLine(line)
				if self.options.liveUpdate:
					sys.stdout.write(self.generateStats())
					sys.stdout.flush()
			except Warn as e:
				print("Warning: " + str(e))
		stats = self.generateStats()
		if stats:
			sys.stdout.write(stats + "\n\n\n")
			sys.stdout.flush()

	def assertCurrentGame(self, msg):
		if not self.currentGame:
			print(str(msg) + ", but there's no game")
			return False
		return True

	def generateStats(self):
		if not self.games:
			return ""
		if self.options.liveUpdate:
			clearscreen()
			return self.games[-1].generateStats()
		else:
			ret = []
			for game in self.games:
				ret.append(game.generateStats())
			return "\n\n\n".join(ret)

	def gameEnded(self):
		if not self.currentGame or\
		   not self.options.fragGraphDir:
			return
		fg = FragGraph(self.currentGame)
		for algo in ("dot", "circo"):
			filename = "%s/frags-%s-%s.svg" %\
				(self.options.fragGraphDir, algo,
				 self.currentGame.getSaneName())
			fg.generateSVG(filename, algo)

	def parseIsoTimestamp(self, line):
		# Returns a tuple (rest-of-line, datetime-instance)
		idx = line.find("/")
		if idx < 0:
			raise Error("Parser: Did not find timestamp on line: " + line)
		try:
			stamp = line[0:idx]
			line = line[idx+1:]

			if len(stamp) != ISO_TIMESTAMP_LEN:
				raise ValueError
			m = re_iso_timestamp.match(stamp)
			if not m:
				raise ValueError
			stamp = datetime.datetime(
				year=int(m.group(1)), month=int(m.group(2)), day=int(m.group(3)),
				hour=int(m.group(4)), minute=int(m.group(5)), second=int(m.group(6)),
				microsecond=int(m.group(7)))
		except (IndexError, ValueError) as e:
			raise Error("Parser: Invalid timestamp")
		return line, stamp

	@staticmethod
	def lineHasTimestamp(line):
		try:
			m = re_iso_timestamp.match(line[0:ISO_TIMESTAMP_LEN])
			if m:
				return True
		except IndexError as e:
			pass
		return False

class FragGraph(object):
	# Graph tuning parameters
	ARROW_SCALE	= 2.0
	ARROW_BASE	= 0.5
	WEIGHT_SCALE	= 0.5
	PEN_SCALE	= 8.0
	NAME_BASE	= 12
	NAME_SCALE	= 14.0

	def __init__(self, game):
		self.game = game

	def __p2n(self, player):
		return "%s (%d)" % (player.realName, player.getNrFrags())

	def __genEdge(self, player, fraggedPlayer, nrFrags, maxPerTargetKillCnt,
		      color="#000000"):
		assert(nrFrags <= maxPerTargetKillCnt)
		if maxPerTargetKillCnt != 0:
			arrowSize = ((nrFrags / maxPerTargetKillCnt) * self.ARROW_SCALE) + self.ARROW_BASE
			penWidth = max(1, ((nrFrags / maxPerTargetKillCnt) * self.PEN_SCALE))
		else:
			arrowSize = self.ARROW_BASE
			penWidth = 1
		edgeWeight = float(nrFrags) * self.WEIGHT_SCALE
		self.g.add_edge(self.__p2n(player),
				self.__p2n(fraggedPlayer),
				key="%s->%s" % (player.realName, fraggedPlayer.realName),
				dir="forward",
				arrowhead="normal",
				weight=edgeWeight,
				arrowsize=arrowSize,
				penwidth=penWidth,
				color=color)

	def __generate(self, layoutAlgorithm):
		self.g = gv.AGraph(strict=False, directed=False,
				   landscape=False,
				   name=self.game.getSaneName(),
				   label=self.game.getSaneName("  -  "),
				   labelfontsize=22,
				   labelloc="t",
				   dpi=70)
		# Find extrema
		maxPerTargetKillCnt = 0 # Max per-target kill count
		maxNrFrags = 0 # Max frags (no SKs, no TKs, any target)
		for player in self.game.getPlayers():
			for fraggedPlayer in player.getFrags().getPlayers():
				maxPerTargetKillCnt = max(maxPerTargetKillCnt,
					player.getFrags().countFor(fraggedPlayer))
			for fraggedPlayer in player.getTeamkills().getPlayers():
				maxPerTargetKillCnt = max(maxPerTargetKillCnt,
					player.getTeamkills().countFor(fraggedPlayer))
			maxPerTargetKillCnt = max(maxPerTargetKillCnt,
				player.getNrSuicides())
			maxNrFrags = max(maxNrFrags, player.getNrFrags())
		# Create all nodes
		for player in self.game.getPlayers():
			nrFrags = player.getNrFrags()
			if maxNrFrags != 0:
				fontsize = ((nrFrags / maxNrFrags) * self.NAME_SCALE) + self.NAME_BASE
			else:
				fontsize = self.NAME_BASE
			self.g.add_node(self.__p2n(player),
					margin="0.2, 0.1",
					fontsize=int(round(fontsize)))
		# Create all edges
		for player in self.game.getPlayers():
			for fraggedPlayer in player.getFrags().getPlayers():
				self.__genEdge(player, fraggedPlayer,
					       player.getFrags().countFor(fraggedPlayer),
					       maxPerTargetKillCnt)
			for fraggedPlayer in player.getTeamkills().getPlayers():
				self.__genEdge(player, fraggedPlayer,
					       player.getTeamkills().countFor(fraggedPlayer),
					       maxPerTargetKillCnt,
					       color="#FF0000")
			if player.getNrSuicides():
				self.__genEdge(player, player, player.getNrSuicides(),
					       maxPerTargetKillCnt,
					       color="#0000FF")
		self.g.layout(prog=layoutAlgorithm)

	def generateSVG(self, filename, layoutAlgorithm):
		self.__generate(layoutAlgorithm)
		self.g.draw(filename, format="svg")

rawlogfile = None

def writeRawLog(directory, line):
	global rawlogfile
	if not directory:
		return
	try:
		if not rawlogfile:
			count = 0
			datestr = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
			while True:
				name = "%s/%s-%03d.log" % (directory, datestr, count)
				try:
					open(name, "r").close()
				except IOError as e:
					if e.errno == errno.ENOENT:
						break
				if count >= 999:
					raise Warn("Could not find possible filename")
				count += 1
			rawlogfile = open(name, "w")
		rawlogfile.write(line)
		rawlogfile.flush()
	except IOError as e:
		raise Warn("Failed to write logfile: %s" % str(e))

def closeRawLog():
	global rawlogfile
	if rawlogfile:
		rawlogfile.flush()
		rawlogfile.close()
		rawlogfile = None

def genericUsage(scriptname, additionalInfo):
	print("Usage: %s [OPTIONS] [LOGFILES]" % scriptname)
	print("")
	print("The optional LOGFILES are files logged with the -l|--logdir option")
	print("If no logfiles are given, %s will listen to raw logdata" % scriptname)
	print("input on stdin.")
	if additionalInfo:
		print("\n" + additionalInfo)
	print("")
	print(" -n|--myname NAME       my nickname ('self', if not given)")
	print(" -l|--logdir DIR        Write the raw logs to DIRectory")
	print(" -s|--splitlogs         Split logs by map")
	print(" -F|--fraggraphdir DIR  Write frag-graph SVGs to DIRectory")
	print(" -L|--filterleft        Filter all players who left the game early")
	print(" -J|--filterjoinig      Filter all players who joined the game late")
	print(" -f|--sortbyfrags       Always sort by # of frags")
	print(" -d|--debug             Enable debugging")

def genericMain(scriptname, usageinfo, parserClass):
	global debug

	options = Options()
	try:
		(opts, args) = getopt.getopt(sys.argv[1:],
			"hdn:l:fF:LJs",
			[ "help", "debug", "myname=", "logdir=", "sortbyfrags",
			  "fraggraphdir=", "filterleft", "filterjoinig",
			  "splitlogs", ])
		for (o, v) in opts:
			if o in ("-h", "--help"):
				genericUsage(scriptname, usageinfo)
				return 0
			if o in ("-d", "--debug"):
				debug = True
			if o in ("-n", "--myname"):
				options.myname = v
			if o in ("-l", "--logdir"):
				options.rawlogdir = v
			if o in ("-f", "--sortbyfrags"):
				options.alwaysSortByFrags = True
			if o in ("-F", "--fraggraphdir"):
				options.fragGraphDir = v
			if o in ("-L", "--filterleft"):
				options.filterLeft = True
			if o in ("-J", "--filterjoinig"):
				options.filterJoinIG = True
			if o in ("-s", "--splitlogs"):
				options.splitLogs = True
	except (getopt.GetoptError):
		genericUsage(scriptname, usageinfo)
		return 1
	try:
		if args:
			for arg in args:
				fd = open(arg, "r")
				parserClass(options).parseFile(fd)
		else:
			options.liveUpdate = True
			parserClass(options).parseFile(sys.stdin)
	except (Warn, Error) as e:
		print("Exception: " + str(e))
		return 1
	return 0
