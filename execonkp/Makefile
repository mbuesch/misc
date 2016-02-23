CC		:= gcc
INSTALL		:= install

CFLAGS		+= -g -O2 -flto -Wall
LDFLAGS		:=
LIBS		:= -lX11 -lXi
DESTDIR		:=
PREFIX		:= /usr/local

CFLAGS		+= -DPREFIX=$(PREFIX)

BIN		= execonkp
SRCS		= main.c

V		= @             # Verbose build:  make V=1
Q		= $(V:1=)
QUIET_CC	= $(Q:@=@echo '     CC       '$@;)$(CC)
QUIET_DEPEND	= $(Q:@=@echo '     DEPEND   '$@;)$(CC)

DEPS		= $(patsubst %.c,dep/%.d,$(1))
OBJS		= $(patsubst %.c,obj/%.o,$(1))

.SUFFIXES:
.PHONY: all install clean
.DEFAULT_GOAL := all

# Generate dependencies
$(call DEPS,$(SRCS)): dep/%.d: %.c
	@mkdir -p $(dir $@)
	$(QUIET_DEPEND) -o $@.tmp -MM -MT "$@ $(patsubst dep/%.d,obj/%.o,$@)" $(CFLAGS) $< && mv -f $@.tmp $@

-include $(call DEPS,$(SRCS))

# Generate object files
$(call OBJS,$(SRCS)): obj/%.o:
	@mkdir -p $(dir $@)
	$(QUIET_CC) -o $@ -c $(CFLAGS) $<

all: $(BIN)

$(BIN): $(call OBJS,$(SRCS))
	$(QUIET_CC) $(CFLAGS) -o $(BIN) $(LDFLAGS) $(LIBS) $(call OBJS,$(SRCS))

clean:
	rm -Rf dep obj core *~ $(BIN)

install: $(BIN)
	$(INSTALL) -d -m755 $(DESTDIR)$(PREFIX)/bin/
	$(INSTALL) -m755 $(BIN) $(DESTDIR)$(PREFIX)/bin/
