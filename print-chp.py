#!/usr/bin/python3
import base64
import mmap
import re
import struct

chp = mmap.mmap(0, 0, prot=mmap.PROT_READ)

def format_snippet(snippet):
	h = re.sub(rb'..', b'\g<0> ', base64.b16encode(snippet))
	a = re.sub(rb'[\x00-\x1f\x7f-\xff]', b'.', snippet)
	return '%-96s %s' % (h.decode('ascii'), a.decode('ascii'))

pos = 0
while pos < len(chp):
	l1, command, compressed, version, l2 = struct.unpack_from('<IBBBxI', chp, pos)
	pos += 12
	if version > 2:
		raise ValueError
	if command == 0:
		print('MAGIC 0x%08x 0x%08x %d' % (l1, l2, version))
	elif command == 1:
		comment = chp[pos:pos+l2]
		pos += l2
		print('ExpectComment %r' % comment.decode('ascii'))
	elif command == 2:
		snippet_len = min(32, l2)
		snippet = chp[pos:pos+snippet_len]
		pos += l2
		print('ExpectRead  (0x%8X) << %s' % (l2, format_snippet(snippet)))
	elif command == 3:
		snippet_len = min(32, l2)
		snippet = chp[pos:pos+snippet_len]
		pos += l2
		print('ExpectWrite (0x%8X) >> %s' % (l2, format_snippet(snippet)))
	elif command == 4:
		print('Usleep %d' % l1)
	elif command == 5:
		manifest = chp[pos:pos+l2]
		pos += l2
		print('ExpectManifest %r' % manifest.decode('ascii'))
	else:
		raise ValueError
