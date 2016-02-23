/*
 *   Helper to run programs on X11 keyboard events.
 *
 *   Copyright (C) 2016 Michael Buesch <m@bues.ch>
 *
 *   This program is free software; you can redistribute it and/or
 *   modify it under the terms of the GNU General Public License
 *   as published by the Free Software Foundation; either version 2
 *   of the License, or (at your option) any later version.
 *
 *   This program is distributed in the hope that it will be useful,
 *   but WITHOUT ANY WARRANTY; without even the implied warranty of
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *   GNU General Public License for more details.
 */

#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <signal.h>
#include <errno.h>

#include <X11/Xlib.h>
#include <X11/extensions/XInput2.h>

#define PFX	"execonkp: "


static void handle_event(char * const * run_prog)
{
	printf(PFX "Key event detected. Running %s...\n", run_prog[0]);

	execv(run_prog[0], run_prog);
	fprintf(stderr, PFX "execv(\"%s\") failed: %s\n",
		run_prog[0], strerror(errno));
	exit(1);
}

static void signal_handler(int signal)
{
	printf(PFX "terminated\n");
	exit(0);
}

static int install_sighandler(int signal, void (*handler)(int))
{
	struct sigaction act;

	memset(&act, 0, sizeof(act));
	sigemptyset(&act.sa_mask);
	act.sa_flags = 0;
	act.sa_handler = handler;

	return sigaction(signal, &act, NULL);
}

static void usage(void)
{
	printf("Usage: execonkp [OPTIONS] COMMAND [ARGS]\n");
	printf("\n");
	printf("Options:\n");
	printf("  -p|--on-press     Run the command on key press.\n");
	printf("  -r|--on-release   Run the command on key release.\n");
	printf("\n");
	printf("By default only -p is set.\n");
	printf("Setting -r clears -p unless -p is also specified afterwards.\n");
}

int main(int argc, char **argv)
{
	Display *display;
	Window window;
	XIEventMask evmask;
	unsigned char evmask_bits[(XI_LASTEVENT + 8) / 8] = { 0, };
	int res, tmp0, tmp1, xi_opcode;
	sigset_t sigset;
	char * const * run_prog;
	int on_press = 1, on_release = 0;

	argc--;
	argv++;
	while (argc >= 1 && argv[0][0] == '-') {
		if (strcmp(argv[0], "-p") == 0 ||
		    strcmp(argv[0], "--on-press") == 0) {
			on_press = 1;
		} else if (strcmp(argv[0], "-r") == 0 ||
		    strcmp(argv[0], "--on-release") == 0) {
			on_press = 0;
			on_release = 1;
		} else {
			usage();
			return 1;
		}
		argc--;
		argv++;
	}
	if (argc < 1) {
		usage();
		return 1;
	}
	run_prog = argv;

	display = XOpenDisplay(NULL);
	if (!display) {
		/* Fallback to the first display. */
		display = XOpenDisplay(":0");
		if (!display) {
			fprintf(stderr, PFX "Failed to open DISPLAY\n");
			return 1;
		}
	}
	window = DefaultRootWindow(display);

	res = XQueryExtension(display, "XInputExtension", &xi_opcode, &tmp0, &tmp1);
	if (!res) {
		fprintf(stderr, PFX "X Input extension not available.\n");
		return 1;
	}

	sigemptyset(&sigset);
	res = sigprocmask(SIG_SETMASK, &sigset, NULL);
	res |= install_sighandler(SIGINT, signal_handler);
	res |= install_sighandler(SIGTERM, signal_handler);
	if (res) {
		fprintf(stderr, PFX "Failed to setup signal handlers\n");
		return 1;
	}

	if (on_press)
		XISetMask(evmask_bits, XI_KeyPress);
	if (on_release)
		XISetMask(evmask_bits, XI_KeyRelease);
	memset(&evmask, 0, sizeof(evmask));
	evmask.deviceid = XIAllDevices;
	evmask.mask_len = sizeof(evmask_bits);
	evmask.mask = evmask_bits;

	res = XISelectEvents(display, window, &evmask, 1);
	if (res != Success) {
		fprintf(stderr, PFX "Failed to set event mask (%d)\n", res);
		return 1;
	}

	printf(PFX "Waiting for keyboard event...\n");
	while (1) {
		XEvent ev;
		XGenericEventCookie *cookie = &ev.xcookie;

		XNextEvent(display, &ev);
		if (XGetEventData(display, cookie) &&
		    cookie->type == GenericEvent &&
		    cookie->extension == xi_opcode) {
			handle_event(run_prog);
		}
		XFreeEventData(display, cookie);
	}
}
