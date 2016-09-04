#!/usr/bin/python3
import base64
import mmap
import re
import struct
import sys

def format_snippet(snippet):
	h = re.sub(rb'..', b'\g<0> ', base64.b16encode(snippet))
	a = re.sub(rb'[\x00-\x1f\x7f-\xff]', b'.', snippet)
	return '%-96s %s' % (h.decode('ascii'), a.decode('ascii'))

def discard(i):
	for v in i:
		pass

def parse_headers(source):
	pos = 0
	while pos < len(source):
		l1, command, compressed, version, l2 = struct.unpack_from('<IBBBxI', source, pos)
		pos += 12
		assert version <= 2
		assert compressed == 0
		if command == 0:
			yield ('MAGIC', l1, l2, version)
		elif command == 1:
			yield ('ExpectComment', pos, pos + l2)
			pos += l2
		elif command == 2:
			yield ('ExpectRead', pos, pos + l2)
			pos += l2
		elif command == 3:
			yield ('ExpectWrite', pos, pos + l2)
			pos += l2
		elif command == 4:
			yield ('Usleep', l1)
		else:
			raise ValueError('unsupported command %d' % command)

def extract_awusb_read(source, headers, length):
	while length > 0:
		command, start, end = headers.__next__()
		assert command == 'ExpectRead'
		yield (start, end)
		length -= end - start

def extract_awusb_write(source, headers, length):
	while length > 0:
		command, start, end = headers.__next__()
		assert command == 'ExpectWrite'
		yield (start, end)
		length -= end - start

def parse_awusb(source, headers):
	while True:
		# request
		command, start, end = headers.__next__()
		assert command == 'ExpectWrite'
		length, request = struct.unpack_from('<xxxxxxxxIxxxxHxxxxxxxxxxxxxx', source, start)
		# payload
		if request == 0x11:
			yield 'read', extract_awusb_read(source, headers, length)
		elif request == 0x12:
			yield 'write', extract_awusb_write(source, headers, length)
		else:
			raise ValueError('unsupported USB request %d' % request)
		# response
		command, start, end = headers.__next__()
		assert command == 'ExpectRead'

def parse_fel(source, headers):
	awusb = parse_awusb(source, headers)
	while True:
		# request
		rw, chunks = awusb.__next__()
		assert rw == 'write'
		start, end = chunks.__next__()
		request, address, length = struct.unpack_from('<IIIxxxx', source, start)
		# payload
		if request == 0x1:
			rw, chunks = awusb.__next__()
			assert rw == 'read'
			start, end = chunks.__next__()
			soc_id, protocol, scratchpad = struct.unpack_from('<xxxxxxxxIxxxxHxxIxxxxxxxx', source, start)
			yield 'ver', soc_id, protocol, scratchpad
		elif request == 0x101:
			rw, chunks = awusb.__next__()
			assert rw == 'write'
			yield 'write', address, length, chunks
		elif request == 0x102:
			yield 'exe', address
		elif request == 0x103:
			rw, chunks = awusb.__next__()
			assert rw == 'read'
			yield 'read', address, length, chunks
		else:
			raise ValueError('unsupported FEL request %d' % request)
		# response
		rw, chunks = awusb.__next__()
		assert rw == 'read'

# Keep this up to date with fel.c. They're about to change.
SPL_SOC_ID = 0x00162500
SPL_THUNK_ADDR = 0xAE00
SPL_CHUNKS = [
	(0x0000, 0x1800),
	(0x8000, 0x0800),
	(0x2000, 0x3C00),
	(0x8800, 0x2400)
]

def extract_fel_spl(source, headers):
	chunk_index = 0
	fel = parse_fel(source, headers)
	for operation in fel:
		if operation[0] == 'ver':
			assert operation[1] == SPL_SOC_ID
		elif operation[0] == 'read':
			discard(operation[2])
		elif operation[0] == 'exe':
			if operation[1] == SPL_THUNK_ADDR:
				break
		elif operation[0] == 'write':
			addr, capacity = SPL_CHUNKS[chunk_index]
			if operation[1] == addr and operation[2] <= capacity:
				yield from operation[3]
				chunk_index += 1
				if chunk_index >= len(SPL_CHUNKS) or operation[2] < capacity:
					break

def extract_fel_write(source, headers):
	fel = parse_fel(source, headers)
	request, address, length, chunks = fel.__next__()
	assert request == 'write'
	yield from chunks

def extract_fastboot_flash(source, headers):
	while True:
		command, start, end = headers.__next__()
		assert command == 'ExpectWrite'
		fb_command = source[start:end]
		m = re.match(r'download:(.{8})', fb_command)
		if m is not None:
			command, start, end = headers.__next__()
			assert command == 'ExpectRead'
			length = int(m.group(1), 16)
			yield from extract_awusb_write(source, headers, length)
			command, start, end = headers.__next__()
			assert command == 'ExpectRead'
	# when do we stop?

def extract_files(source):
	headers = parse_headers(source)
	for header in headers:
		if header[0] == 'MAGIC' or header[0] == 'Usleep':
			pass
		elif header[0] == 'ExpectComment':
			comment = source[header[1]:header[2]]
			words = comment.split(b', ')
			if words[0] == 'fel':
				if words[1] == 'spl':
					yield words[2], extract_fel_spl(source, headers)
				elif words[2] == 'write':
					yield words[3], extract_fel_write(source, headers)
			elif words[0] == 'fastboot':
				pos = 1
				while pos < len(words):
					if words[pos] == '-i':
						pos += 2
					elif words[pos] == '-u':
						pos += 1
					elif words[pos] == 'devices':
						break
					elif words[pos] == 'flash':
						yield words[pos + 2], extract_fastboot_flash(source, headers)
						break
					else:
						raise ValueError('unrecognized fastboot command %s' % comment)
		elif header[0] == 'ExpectRead' or header[0] == 'ExpectWrite':
			pass

def print_files(source, files):
	for name, chunks in files:
		size = sum(end - start for start, end in chunks)
		print('%9d %s' % (size, name))

def save_files(source, files):
	for name, chunks in files:
		with open(name, 'wb') as f:
			for start, end in chunks:
				f.write(source[start:end])

chp = mmap.mmap(0, 0, prot=mmap.PROT_READ)
files = extract_files(chp)
if True:
	print_files(chp, files)
else:
	save_files(chp, files)
