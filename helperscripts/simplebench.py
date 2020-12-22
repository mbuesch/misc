#!/usr/bin/env python3
import timeit
while True:
	print(timeit.timeit('"-".join(str(n) for n in range(1000))', number=10000))
