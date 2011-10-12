#!/usr/bin/env python2.7
"""
# sauerstats.py
# Copyright (c) 2010-2011 Michael Buesch <m@bues.ch>
# Licensed under the GNU/GPL version 2 or later.
"""

import sys
import getopt
from gamestats import *


class SauerbratenParser(Parser):
	_re_name = r'(.*)' # Player/item name

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
	re_connected_from = re.compile(r'^' + _re_name + r' connected from ' +\
				       _re_name + r'$')
	re_connected_from2 = re.compile(r'^' + _re_name + r' is fragging in ' +\
					_re_name + r'$')
	re_disconn_attempt = re.compile(r'^attempting to disconnect\.\.\.$')
	re_rename = re.compile(r'^' + _re_name + r' is now known as ' + _re_name + r'$')

	re_read_map = re.compile(r'^read map (.*) \(\d+\.\d+ seconds\)$')
	re_suggest = re.compile(r'^' + _re_name + r' suggests ' + _re_name + r' on map ' +
				_re_name + r' \(select map to vote\)$')

	re_you_got_fragged = re.compile(r'^you got fragged by ' + _re_name + r'$')
	re_fragged = re.compile(r'^' + _re_name + r' fragged ' + _re_name + r'$')
	re_fragged_teammate = re.compile(r'^' + _re_name + r' fragged a teammate \(' +\
					 _re_name + r'\)$')
	re_yougotkilledby_teammate = re.compile(r'^you got fragged by a teammate \(' +\
						_re_name + r'\)$')
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

	def __init__(self, options):
		Parser.__init__(self, options)

		self.lastReadMap = "unknown"

	def __parseKill(self, timestamp, name0, name1, tk=False):
		# name0 fragged name1
		if not self.assertCurrentGame("kill"):
			return
		player0 = self.currentGame.playerOrMe(name0)
		player1 = self.currentGame.playerOrMe(name1)
		if tk:
			player0.addTeamkill(timestamp, player1)
		else:
			player0.addFrag(timestamp, player1)
		self.currentGame.hadFirstBlood = True

	def doParseLine(self, stamp, line):
		line = line.strip()
		m = self.re_chat.match(line)
		if m:
			debugMsg("Chat (%s: %s)" % (m.group(1), m.group(2)))
			return
		m = self.re_teamchat.match(line)
		if m:
			debugMsg("Teamchat (%s: %s)" % (m.group(1), m.group(2)))
			return
		m = self.re_info.match(line)
		if m:
			debugMsg("Info (%s)" % line)
			return
		m = self.re_game_ended.match(line)
		if m:
			if not self.assertCurrentGame("game ended"):
				return
			debugMsg("Game ended (%s)" % line)
			if self.currentGame.ended:
				print("Current game ended twice?!")
				return
			self.currentGame.ended = stamp
			self.gameEnded()
			return
		m = self.re_game_mode.match(line)
		if m:
			self.currentGame = None
			debugMsg("Game mode (%s)" % line)
			newGame = Game(options=self.options,
				       timestamp=stamp, mode=m.group(1),
				       mapname=self.lastReadMap,
				       selfIDs=("you",))
			self.currentGame = newGame
			self.games.append(newGame)
			return
		m = self.re_yougotkilledby_teammate.match(line)
		if m:
			debugMsg("TK 1 (%s)" % line)
			self.__parseKill(stamp, m.group(1), None, tk=True)
			return
		m = self.re_fragged_teammate.match(line)
		if m:
			debugMsg("TK 2 (%s)" % line)
			self.__parseKill(stamp, m.group(1), m.group(2), tk=True)
			return
		m = self.re_you_got_fragged.match(line)
		if m:
			debugMsg("Frag 1 (%s)" % line)
			self.__parseKill(stamp, m.group(1), None)
			return
		m = self.re_fragged.match(line)
		if m:
			debugMsg("Frag 2 (%s)" % line)
			self.__parseKill(stamp, m.group(1), m.group(2))
			return
		m = self.re_suicide.match(line)
		if m:
			debugMsg("Suicide (%s)" % line)
			if not self.assertCurrentGame("suicide"):
				return
			player = self.currentGame.playerOrMe(m.group(1))
			player.addSuicide(stamp)
			return
		m = self.re_dropped_your.match(line)
		if m:
			debugMsg("Dropped your flag (%s)" % line)
			if not self.assertCurrentGame("dropped-your"):
				return
			player = self.currentGame.player(m.group(1))
			player.addCtfDrop(stamp)
			return
		m = self.re_dropped_enemy.match(line)
		if m:
			debugMsg("Dropped enemy flag (%s)" % line)
			if not self.assertCurrentGame("dropped-enemy"):
				return
			player = self.currentGame.playerOrMe(m.group(1))
			player.addCtfDrop(stamp)
			return
		m = self.re_stole_your.match(line)
		if m:
			debugMsg("Stole your flag (%s)" % line)
			if not self.assertCurrentGame("stole-your"):
				return
			player = self.currentGame.player(m.group(1))
			player.addCtfSteal(stamp)
			return
		m = self.re_stole_enemy.match(line)
		if m:
			debugMsg("Stole enemy flag (%s)" % line)
			if not self.assertCurrentGame("stole-enemy"):
				return
			player = self.currentGame.playerOrMe(m.group(1))
			player.addCtfSteal(stamp)
			return
		m = self.re_picked_your.match(line)
		if m:
			debugMsg("Picked your flag (%s)" % line)
			if not self.assertCurrentGame("picked-your"):
				return
			player = self.currentGame.player(m.group(1))
			player.addCtfPick(stamp)
			return
		m = self.re_picked_enemy.match(line)
		if m:
			debugMsg("Picked enemy flag (%s)" % line)
			if not self.assertCurrentGame("picked-enemy"):
				return
			player = self.currentGame.playerOrMe(m.group(1))
			player.addCtfPick(stamp)
			return
		m = self.re_score_your.match(line)
		if m:
			debugMsg("Scored for your team (%s)" % line)
			if not self.assertCurrentGame("scored-your"):
				return
			player = self.currentGame.playerOrMe(m.group(1))
			player.addCtfScore(stamp)
			return
		m = self.re_score_enemy.match(line)
		if m:
			debugMsg("Scored for enemy team (%s)" % line)
			if not self.assertCurrentGame("scored-enemy"):
				return
			player = self.currentGame.player(m.group(1))
			player.addCtfScore(stamp)
			return
		m = self.re_returned_your.match(line)
		if m:
			debugMsg("Returned your flag (%s)" % line)
			if not self.assertCurrentGame("returned-your"):
				return
			player = self.currentGame.playerOrMe(m.group(1))
			player.addCtfReturn(stamp)
			return
		m = self.re_returned_enemy.match(line)
		if m:
			debugMsg("Returned enemy flag (%s)" % line)
			if not self.assertCurrentGame("returned-enemy"):
				return
			player = self.currentGame.player(m.group(1))
			player.addCtfReturn(stamp)
			return
		m = self.re_stopped_by.match(line)
		if m:
			debugMsg("Stopped by (%s)" % line)
			return
		m = self.re_rampage.match(line)
		if m:
			debugMsg("Rampage (%s)" % line)
			return
		m = self.re_dominate.match(line)
		if m:
			debugMsg("Dominate (%s)" % line)
			return
		m = self.re_triplekill.match(line)
		if m:
			debugMsg("Triplekill (%s)" % line)
			return
		m = self.re_suggest.match(line)
		if m:
			debugMsg("Suggest (%s)" % line)
			return
		m = self.re_player_connected.match(line)
		if m:
			debugMsg("Player connected (%s)" % line)
			if not self.assertCurrentGame("player connected"):
				return
			name = m.group(1)
			self.currentGame.player(name).connected()
			return
		m = self.re_player_disconn.match(line)
		if m:
			debugMsg("Player disconnected (%s)" % line)
			if not self.assertCurrentGame("player connected"):
				return
			name = m.group(1)
			self.currentGame.player(name).disconnected()
			return
		m = self.re_conn_attempt.match(line)
		if m:
			debugMsg("Connection attempt (%s)" % line)
			return
		m = self.re_connected.match(line)
		if m:
			debugMsg("Connected (%s)" % line)
			return
		m = self.re_connected_from.match(line)
		if m:
			debugMsg("Connected from (%s)" % line)
			return
		m = self.re_connected_from2.match(line)
		if m:
			debugMsg("Connected from (%s)" % line)
			return
		m = self.re_disconn_attempt.match(line)
		if m:
			debugMsg("Disconnect attempt (%s)" % line)
			return
		m = self.re_you_disconn.match(line)
		if m:
			debugMsg("Disconnected (%s)" % line)
			return
		m = self.re_rename.match(line)
		if m:
			debugMsg("Player rename (%s)" % line)
			if not self.assertCurrentGame("player rename"):
				return
			oldName = m.group(1)
			newName = m.group(2)
			self.currentGame.player(oldName).rename(newName)
			return
		m = self.re_read_map.match(line)
		if m:
			if self.options.splitLogs:
				closeRawLog()
			debugMsg("Map (%s)" % line)
			mapname = m.group(1)
			mapname = mapname.split('/')[-1]
			if mapname.endswith(".ogz"):
				mapname = mapname[0:-4]
			self.lastReadMap = mapname
			return
		m = self.re_rendering.match(line)
		if m:
			debugMsg("Renderer (%s)" % line)
			return
		m = self.re_init.match(line)
		if m:
			debugMsg("Init (%s)" % line)
			return
		m = self.re_waypoints.match(line)
		if m:
			debugMsg("Waypoints (%s)" % line)
			return
		m = self.re_intermission.match(line)
		if m:
			debugMsg("Intermission (%s)" % line)
			return
		m = self.re_msg.match(line)
		if m:
			debugMsg("Message (%s)" % line)
			return
		if not line.replace("*", "") or\
		   not line.replace(">", ""):
			debugMsg("Spacer (%s)" % line)
			return
		debugMsg("UNKNOWN console message: '%s'" % line)

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
	print(" -s|--splitlogs         Split logs by map")
	print(" -F|--fraggraphdir DIR  Write frag-graph SVGs to DIRectory")
	print(" -L|--filterleft        Filter all players who left the game early")
	print(" -J|--filterjoinig      Filter all players who joined the game late")
	print(" -f|--sortbyfrags       Always sort by # of frags")
	print(" -d|--debug             Enable debugging")

def main():
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
				usage()
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
		usage()
		return 1
	try:
		if args:
			for arg in args:
				fd = open(arg, "r")
				SauerbratenParser(options).parseFile(fd)
		else:
			options.liveUpdate = True
			SauerbratenParser(options).parseFile(sys.stdin)
	except (Warn, Error), e:
		print("Exception: " + str(e))
		return 1
	return 0

if __name__ == "__main__":
	sys.exit(main())
