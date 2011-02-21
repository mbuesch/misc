CFLAGS		:= -O2 -Wall
LDFLAGS		:=
LDLIBS		:=

all: bin2iso

bin2iso: bin2iso.c
	$(CC) $(CFLAGS) $(LDFLAGS) $^ $(LDLIBS) -o $@

%.o: %.c
	$(CC) -c $(CFLAGS) $^ -o $@

clean:
	rm -f bin2iso *.o
