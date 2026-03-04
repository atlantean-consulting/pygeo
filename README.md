# PyGeo
*Geomancy can tickle your fancy*

PyGeo is a command-line geomantic divination engine for the Linux OS.

It leverages `/dev/urandom` to extract entropy from the fabric of local spacetime.

When you ask a question, PyGeo hashes it with SHA-256, grabs the first two bytes, and XORs them with two bytes of `/dev/urandom` to generate the four Mother figures. From there, we generate the other twelve figures with simple XOR operations. In a very real sense, the contents of `/dev/urandom` are a snapshot of the physical state of your current corner of the Universe, making it a wonderful source of an entropic seed. Is `/dev/urandom` *perfectly* random, in the same sense that dice are? Who knows? Who *cares*? Don't worry about it!

Simply launch it with `python3 geomancy.py`, enter your question, and ponder the result.

Note: It wasn't feasible to fit this into the standard 80-column terminal. You'll need to expand the terminal window to ~140 characters to fit everything.

This is v1.0 - in v1.1, we'll add a House Chart.

Valeo Valui Valiturus
