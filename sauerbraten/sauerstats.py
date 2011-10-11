#!/usr/bin/env python2.7
"""
# sauerstats.py
# Copyright (c) 2010-2011 Michael Buesch <m@bues.ch>
# Licensed under the GNU/GPL version 2 or later.
"""

import sys
import getopt
import re
import datetime
import errno
import pygraphviz as gv


debug = False
liveUpdate = False
myname = "self"
alwaysSortByFrags = False


_re_name = r'(.*)'

re_init = re.compile(r'^init: .*$')
re_waypoints = re.compile(r'^loaded (\d+) waypoints from ' + _re_name + r'$')
re_intermission = re.compile(r'^intermission:$')
re_info = re.compile(r'^Info: .*$')
re_rendering = re.compile(r'^Rendering using .*$')

re_game_mode = re.compile(r'^game mode is ' + _re_name + r'$')
re_game_ended = re.compile(r'^game has ended!$')

re_you_disconn = re.compile(r'^disconnected$')
re_player_disconn = re.compile(r'^player ' + _re_name + r' disconnected$')
re_conn_attempt = re.compile(r'^attempting to connect.*$')
re_connected = re.compile(r'^connected to server$')
re_player_connected = re.compile(r'^connected: ' + _re_name + r'$')
re_connected_from = re.compile(r'^' + _re_name + r' connected from ' + _re_name + r'$')
re_connected_from2 = re.compile(r'^' + _re_name + r' is fragging in ' + _re_name + r'$')
re_disconn_attempt = re.compile(r'^attempting to disconnect\.\.\.$')
re_rename = re.compile(r'^' + _re_name + r' is now known as ' + _re_name + r'$')

re_read_map = re.compile(r'^read map (.*) \(\d+\.\d+ seconds\)$')
re_suggest = re.compile(r'^' + _re_name + r' suggests ' + _re_name + r' on map ' +
			_re_name + r' \(select map to vote\)$')

re_you_got_fragged = re.compile(r'^you got fragged by ' + _re_name + r'$')
re_fragged = re.compile(r'^' + _re_name + r' fragged ' + _re_name + r'$')
re_fragged_teammate = re.compile(r'^' + _re_name + r' fragged a teammate \(' + _re_name + r'\)$')
re_yougotkilledby_teammate = re.compile(r'^you got fragged by a teammate \(' + _re_name + r'\)$')
re_suicide = re.compile(r'^' + _re_name + r' suicided!?$')

re_dropped_your = re.compile(r'^' + _re_name + r' dropped your flag$')
re_dropped_enemy = re.compile(r'^' + _re_name + r' dropped the enemy flag$')
re_stole_your = re.compile(r'^' + _re_name + r' stole your flag$')
re_stole_enemy = re.compile(r'^' + _re_name + r' stole the enemy flag$')
re_picked_your = re.compile(r'^' + _re_name + r' picked up your flag$')
re_picked_enemy = re.compile(r'^' + _re_name + r' picked up the enemy flag$')
re_score_your = re.compile(r'^' + _re_name + r' scored for your team$')
re_score_enemy = re.compile(r'^' + _re_name + r' scored for the enemy team$')
re_returned_your = re.compile(r'^' + _re_name + r' returned your flag$')
re_returned_enemy = re.compile(r'^' + _re_name + r' returned the enemy flag$')
re_stopped_by = re.compile(r'^' + _re_name + r' was stopped by ' + _re_name + r'$')

re_rampage = re.compile(r'^' + _re_name + r' is on a RAMPAGE!!$')
re_dominate = re.compile(r'^' + _re_name + r' is DOMINATING!!$')
re_triplekill = re.compile(r'^' + _re_name + r' scored a TRIPLE KILL!$')

re_msg = re.compile(r'^' + _re_name + r': .*$')
# chat annotation patch
re_chat = re.compile(r'^chat-message: ' + _re_name + r':\s*(.*)$')
re_teamchat = re.compile(r'^teamchat-message: ' + _re_name + r':\s*(.*)$')


def debugMsg(msg):
	if debug:
		print(msg)

def clearscreen():
	sys.stdout.write("\33[2J\33[0;0H")
	sys.stdout.flush()

def filterPlayers(players):
	if filterLeft:
		players = filter(lambda p: not p.disconnectedInGame, players)
	if filterJoinIG:
		players = filter(lambda p: not p.connectedInGame, players)
	return players

class Event(object):
	def __init__(self, timestamp):
		self.timestamp = timestamp

class Events(object):
	def __init__(self):
		self.events = []

	def addEvent(self, event):
		self.events.append(event)

	def countAll(self):
		return len(self.events)

class PlayerEvents(object):
	def __init__(self, players={}):
		self.players = players.copy()

	def copy(self):
		return PlayerEvents(self.players.copy())

	def extend(self, other):
		self.players.update(other.players)

	def addEvent(self, event, player):
		self.players.setdefault(player, []).append(event)

	def countAll(self):
		return sum([ len(evs) for evs in self.players.values() ])

	def countFor(self, player):
		return len(self.players[player])

	def getPlayersUnfiltered(self):
		return self.players.keys()

	def getPlayers(self):
		return filterPlayers(self.getPlayersUnfiltered())

class Player(object):
	def __init__(self, name, realName, game):
		self.name = name
		self.realName = realName
		self.game = game
		self.frags = PlayerEvents()
		self.teamkills = PlayerEvents()
		self.deaths = PlayerEvents()
		self.ctfScores = Events()
		self.ctfDrops = Events()
		self.ctfPicks = Events()
		self.ctfStolen = Events()
		self.ctfReturns = Events()
		self.suicides = Events()
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
	def __init__(self, timestamp, mode, mapname):
		self.mode = mode.lower()
		self.mapname = mapname
		self.hadFirstBlood = False
		self.started = timestamp
		self.ended = False
		self.players = {
			"self"	: Player("self", myname, self)
		}
		debugMsg("New game: mode=%s" % mode)

	def __saneName(self, name):
		return re.sub(r'\s+', '-', name)

	def getSaneMapName(self):
		items = []
		items.append(self.__saneName(self.started.strftime("%Y%m%d-%H%M%S")))
		items.append(self.__saneName(self.mode))
		items.append(self.__saneName(self.mapname))
		return "-".join(items)

	def __mkPlayerKey(self, name):
		return "player_" + name

	def player(self, name):
		key = self.__mkPlayerKey(name)
		return self.players.setdefault(key, Player(key, name, self))

	def me(self):
		return self.players["self"]

	def playerOrMe(self, name):
		if not name or name == "you":
			return self.me()
		return self.player(name)

	def getPlayersUnfiltered(self):
		return self.players.values()

	def getPlayers(self):
		return filterPlayers(self.getPlayersUnfiltered())

	def renamePlayer(self, oldName, newName):
		player = self.players.pop(self.__mkPlayerKey(oldName))
		player.name = self.__mkPlayerKey(newName)
		player.realName = newName
		self.players[player.name] = player

	def isCtf(self):
		return self.mode in ("ctf", "insta ctf", "efficiency ctf")

	def generateStats(self):
		ret = []
		prefix = ""
		if liveUpdate:
			if self.ended:
				prefix = "<GAME ENDED %s> " % self.ended.ctime()
		else:
			if not self.ended:
				prefix = "<GAME INTERRUPTED> "
		ret.append("%s'%s' on map '%s' started %s:" %\
			   (prefix, self.mode, self.mapname, self.started.ctime()))
		players = list(self.getPlayers())[:]
		if self.isCtf() and not alwaysSortByFrags:
			key = lambda p: p.getNrCtfScores()
		else:
			key = lambda p: p.getNrFrags()
		players.sort(key=key, reverse=True)
		for player in players:
			ret.append(player.generateStats())
		if not liveUpdate:
			ret.append("")
		return "\n".join(ret)

class Parser(object):
	def __init__(self, fragGraphDir=None):
		self.fragGraphDir = fragGraphDir
		self.currentGame = None
		self.games = []
		self.lastReadMap = "unknown"

	def __assertCurrentGame(self, msg):
		if not self.currentGame:
			print(msg + ", but there's no game")
			return False
		return True

	def generateStats(self):
		if not self.games:
			return
		if liveUpdate:
			clearscreen()
			print(self.games[-1].generateStats())
		else:
			for game in self.games:
				print(game.generateStats())

	def __parseKill(self, timestamp, name0, name1, tk=False):
		# name0 fragged name1
		if not self.__assertCurrentGame("kill"):
			return
		player0 = self.currentGame.playerOrMe(name0)
		player1 = self.currentGame.playerOrMe(name1)
		if tk:
			player0.addTeamkill(timestamp, player1)
		else:
			player0.addFrag(timestamp, player1)
		self.currentGame.hadFirstBlood = True

	def __parseStamp(self, line):
		idx = line.find("/")
		if idx < 0:
			print("Parser: Did not find timestamp on line: " + line)
			sys.exit(1)
		try:
			stamp = line[0:idx]
			line = line[idx+1:]

			stamp = stamp.split("T")
			date, time = stamp[0], stamp[1]
			date = date.split("-")
			time = time.replace(".", ":").split(":")
			stamp = datetime.datetime(
				year=int(date[0]), month=int(date[1]), day=int(date[2]),
				hour=int(time[0]), minute=int(time[1]), second=int(date[2]),
				microsecond=int(time[3]))
		except (IndexError, ValueError), e:
			print("Parser: Invalid timestamp")
			sys.exit(1)
		return line, stamp

	def parseLine(self, line):
		line, stamp = self.__parseStamp(line)
		m = re_chat.match(line)
		if m:
			debugMsg("Chat (%s: %s)" % (m.group(1), m.group(2)))
			return
		m = re_teamchat.match(line)
		if m:
			debugMsg("Teamchat (%s: %s)" % (m.group(1), m.group(2)))
			return
		m = re_info.match(line)
		if m:
			debugMsg("Info (%s)" % line)
			return
		m = re_game_ended.match(line)
		if m:
			if not self.__assertCurrentGame("game ended"):
				return
			debugMsg("Game ended (%s)" % line)
			if self.currentGame.ended:
				print("Current game ended twice?!")
				return
			self.currentGame.ended = stamp
			self.__gameEnded()
			return
		m = re_game_mode.match(line)
		if m:
			closeRawLog()
			self.currentGame = None
			debugMsg("Game mode (%s)" % line)
			newGame = Game(timestamp=stamp, mode=m.group(1),
				       mapname=self.lastReadMap)
			self.currentGame = newGame
			self.games.append(newGame)
			return
		m = re_yougotkilledby_teammate.match(line)
		if m:
			debugMsg("TK 1 (%s)" % line)
			self.__parseKill(stamp, m.group(1), None, tk=True)
			return
		m = re_fragged_teammate.match(line)
		if m:
			debugMsg("TK 2 (%s)" % line)
			self.__parseKill(stamp, m.group(1), m.group(2), tk=True)
			return
		m = re_you_got_fragged.match(line)
		if m:
			debugMsg("Frag 1 (%s)" % line)
			self.__parseKill(stamp, m.group(1), None)
			return
		m = re_fragged.match(line)
		if m:
			debugMsg("Frag 2 (%s)" % line)
			self.__parseKill(stamp, m.group(1), m.group(2))
			return
		m = re_suicide.match(line)
		if m:
			debugMsg("Suicide (%s)" % line)
			if not self.__assertCurrentGame("suicide"):
				return
			player = self.currentGame.playerOrMe(m.group(1))
			player.addSuicide(stamp)
			return
		m = re_dropped_your.match(line)
		if m:
			debugMsg("Dropped your flag (%s)" % line)
			if not self.__assertCurrentGame("dropped-your"):
				return
			player = self.currentGame.player(m.group(1))
			player.addCtfDrop(stamp)
			return
		m = re_dropped_enemy.match(line)
		if m:
			debugMsg("Dropped enemy flag (%s)" % line)
			if not self.__assertCurrentGame("dropped-enemy"):
				return
			player = self.currentGame.playerOrMe(m.group(1))
			player.addCtfDrop(stamp)
			return
		m = re_stole_your.match(line)
		if m:
			debugMsg("Stole your flag (%s)" % line)
			if not self.__assertCurrentGame("stole-your"):
				return
			player = self.currentGame.player(m.group(1))
			player.addCtfSteal(stamp)
			return
		m = re_stole_enemy.match(line)
		if m:
			debugMsg("Stole enemy flag (%s)" % line)
			if not self.__assertCurrentGame("stole-enemy"):
				return
			player = self.currentGame.playerOrMe(m.group(1))
			player.addCtfSteal(stamp)
			return
		m = re_picked_your.match(line)
		if m:
			debugMsg("Picked your flag (%s)" % line)
			if not self.__assertCurrentGame("picked-your"):
				return
			player = self.currentGame.player(m.group(1))
			player.addCtfPick(stamp)
			return
		m = re_picked_enemy.match(line)
		if m:
			debugMsg("Picked enemy flag (%s)" % line)
			if not self.__assertCurrentGame("picked-enemy"):
				return
			player = self.currentGame.playerOrMe(m.group(1))
			player.addCtfPick(stamp)
			return
		m = re_score_your.match(line)
		if m:
			debugMsg("Scored for your team (%s)" % line)
			if not self.__assertCurrentGame("scored-your"):
				return
			player = self.currentGame.playerOrMe(m.group(1))
			player.addCtfScore(stamp)
			return
		m = re_score_enemy.match(line)
		if m:
			debugMsg("Scored for enemy team (%s)" % line)
			if not self.__assertCurrentGame("scored-enemy"):
				return
			player = self.currentGame.player(m.group(1))
			player.addCtfScore(stamp)
			return
		m = re_returned_your.match(line)
		if m:
			debugMsg("Returned your flag (%s)" % line)
			if not self.__assertCurrentGame("returned-your"):
				return
			player = self.currentGame.playerOrMe(m.group(1))
			player.addCtfReturn(stamp)
			return
		m = re_returned_enemy.match(line)
		if m:
			debugMsg("Returned enemy flag (%s)" % line)
			if not self.__assertCurrentGame("returned-enemy"):
				return
			player = self.currentGame.player(m.group(1))
			player.addCtfReturn(stamp)
			return
		m = re_stopped_by.match(line)
		if m:
			debugMsg("Stopped by (%s)" % line)
			return
		m = re_rampage.match(line)
		if m:
			debugMsg("Rampage (%s)" % line)
			return
		m = re_dominate.match(line)
		if m:
			debugMsg("Dominate (%s)" % line)
			return
		m = re_triplekill.match(line)
		if m:
			debugMsg("Triplekill (%s)" % line)
			return
		m = re_suggest.match(line)
		if m:
			debugMsg("Suggest (%s)" % line)
			return
		m = re_player_connected.match(line)
		if m:
			debugMsg("Player connected (%s)" % line)
			if not self.__assertCurrentGame("player connected"):
				return
			name = m.group(1)
			self.currentGame.player(name).connected()
			return
		m = re_player_disconn.match(line)
		if m:
			debugMsg("Player disconnected (%s)" % line)
			if not self.__assertCurrentGame("player connected"):
				return
			name = m.group(1)
			self.currentGame.player(name).disconnected()
			return
		m = re_conn_attempt.match(line)
		if m:
			debugMsg("Connection attempt (%s)" % line)
			return
		m = re_connected.match(line)
		if m:
			debugMsg("Connected (%s)" % line)
			return
		m = re_connected_from.match(line)
		if m:
			debugMsg("Connected from (%s)" % line)
			return
		m = re_connected_from2.match(line)
		if m:
			debugMsg("Connected from (%s)" % line)
			return
		m = re_disconn_attempt.match(line)
		if m:
			debugMsg("Disconnect attempt (%s)" % line)
			return
		m = re_you_disconn.match(line)
		if m:
			debugMsg("Disconnected (%s)" % line)
			return
		m = re_rename.match(line)
		if m:
			debugMsg("Player rename (%s)" % line)
			if not self.__assertCurrentGame("player rename"):
				return
			oldName = m.group(1)
			newName = m.group(2)
			self.currentGame.player(oldName).rename(newName)
			return
		m = re_read_map.match(line)
		if m:
			debugMsg("Map (%s)" % line)
			mapname = m.group(1)
			mapname = mapname.split('/')[-1]
			if mapname.endswith(".ogz"):
				mapname = mapname[0:-4]
			self.lastReadMap = mapname
			return
		m = re_rendering.match(line)
		if m:
			debugMsg("Renderer (%s)" % line)
			return
		m = re_init.match(line)
		if m:
			debugMsg("Init (%s)" % line)
			return
		m = re_waypoints.match(line)
		if m:
			debugMsg("Waypoints (%s)" % line)
			return
		m = re_intermission.match(line)
		if m:
			debugMsg("Intermission (%s)" % line)
			return
		m = re_msg.match(line)
		if m:
			debugMsg("Message (%s)" % line)
			return
		if not line.replace("*", "") or\
		   not line.replace(">", ""):
			debugMsg("Spacer (%s)" % line)
			return
		debugMsg("UNKNOWN console message: '%s'" % line)

	def __gameEnded(self):
		if not self.currentGame:
			return
		if self.fragGraphDir:
			fg = FragGraph(self.currentGame)
			filename = "%s/frags-%s.svg" %\
				(self.fragGraphDir, self.currentGame.getSaneMapName())
			fg.generateSVG(filename)

class FragGraph(object):
	# Graph tuning parameters
	ALGORITHM	= "circo"
	ARROW_SCALE	= 3.0
	ARROW_BIAS	= 0.5
	WEIGHT_SCALE	= 0.5

	def __init__(self, game):
		self.game = game

	def __genEdge(self, player, fraggedPlayer, maxPerTargetFragCnt):
		nrFrags = player.getKills().countFor(fraggedPlayer)
		assert(nrFrags <= maxPerTargetFragCnt)
		arrowSize = ((float(nrFrags) / maxPerTargetFragCnt) * self.ARROW_SCALE) +\
			self.ARROW_BIAS
		edgeWeight = float(nrFrags) * self.WEIGHT_SCALE
		self.g.add_edge(player.realName,
				fraggedPlayer.realName,
				key=player.realName,
				dir="forward",
				arrowhead="normal",
				weight=edgeWeight,
				arrowsize=arrowSize)

	def __generate(self):
		self.g = g = gv.AGraph(strict=False, directed=False,
				       landscape=False)
		maxPerTargetFragCnt = 0
		for player in self.game.getPlayers():
			for fraggedPlayer in player.getKills().getPlayers():
				cnt = player.getKills().countFor(fraggedPlayer)
				maxPerTargetFragCnt = max(maxPerTargetFragCnt, cnt)
		for player in self.game.getPlayers():
			for fraggedPlayer in player.getKills().getPlayers():
				self.__genEdge(player, fraggedPlayer,
					       maxPerTargetFragCnt)
				if player in fraggedPlayer.getKills().getPlayers():
					self.__genEdge(fraggedPlayer, player,
						       maxPerTargetFragCnt)
		g.layout(prog=self.ALGORITHM)

	def generateSVG(self, filename):
		self.__generate()
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
				except IOError, e:
					if e.errno == errno.ENOENT:
						break
				if count >= 999:
					print("Could not find possible filename")
					sys.exit(1)
				count += 1
			rawlogfile = open(name, "w")
		rawlogfile.write(line)
		rawlogfile.flush()
	except IOError, e:
		print("Failed to write logfile: %s" % str(e))
		sys.exit(1)

def closeRawLog():
	global rawlogfile
	if rawlogfile:
		rawlogfile.flush()
		rawlogfile.close()
		rawlogfile = None

def readInput(fd, rawlogdir, fragGraphDir, addStamp):
	p = Parser(fragGraphDir)
	while True:
		line = fd.readline()
		if not line:
			break
		if addStamp:
			now = datetime.datetime.now().isoformat()
			line = "%s/%s" % (now, line)
		line = line.strip()
		p.parseLine(line)
		writeRawLog(rawlogdir, line + "\n")
		if liveUpdate:
			p.generateStats()
	p.generateStats()

def usage():
	print("Usage: sauerstats.py [OPTIONS] [LOGFILES]")
	print("")
	print("The optional LOGFILES are files logged with the -l|--logdir option")
	print("If no logfiles are given, sauerstats will listen to raw sauerbraten")
	print("input on stdin.")
	print("")
	print(" Example: Convert and log stats into directory:")
	print("  sauerbraten_unix | sauerstats.py -n mynick -l ./logs")
	print("")
	print(" Example: Create stats from logfile:")
	print("  sauerstats.py -n mynick ./logs/2011....log")
	print("")
	print(" -n|--myname NAME       my nickname ('self', if not given)")
	print(" -l|--logdir DIR        Write the raw logs to DIRectory")
	print(" -F|--fraggraphdir DIR  Write frag-graph SVGs to DIRectory")
	print(" -L|--filterleft        Filter all players who left the game early")
	print(" -J|--filterjoinig      Filter all players who joined the game late")
	print(" -f|--sortbyfrags       Always sort by # of frags")
	print(" -d|--debug             Enable debugging")

def main():
	global myname
	global debug
	global liveUpdate
	global alwaysSortByFrags
	global filterLeft
	global filterJoinIG

	filterLeft = False
	filterJoinIG = False
	rawlogdir = None
	fragGraphDir = None
	try:
		(opts, args) = getopt.getopt(sys.argv[1:],
			"hdn:l:fF:LJ",
			[ "help", "debug", "myname=", "logdir=", "sortbyfrags",
			  "fraggraphdir=", "filterleft", "filterjoinig", ])
		for (o, v) in opts:
			if o in ("-h", "--help"):
				usage()
				return 0
			if o in ("-d", "--debug"):
				debug = True
			if o in ("-n", "--myname"):
				myname = v
			if o in ("-l", "--logdir"):
				rawlogdir = v
			if o in ("-f", "--sortbyfrags"):
				alwaysSortByFrags = True
			if o in ("-F", "--fraggraphdir"):
				fragGraphDir = v
			if o in ("-L", "--filterleft"):
				filterLeft = True
			if o in ("-J", "--filterjoinig"):
				filterJoinIG = True
	except (getopt.GetoptError):
		usage()
		return 1
	if args:
		for arg in args:
			fd = open(arg, "r")
			readInput(fd, rawlogdir, fragGraphDir, False)
	else:
		liveUpdate = True
		readInput(sys.stdin, rawlogdir, fragGraphDir, True)
	return 0

if __name__ == "__main__":
	sys.exit(main())
