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

def expect(t, first):
	assert t[0] == first, t[0]
	return t[1:]

def get_singular(i):
	for v in i:
		pass
	return v

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
			yield 'MAGIC', l1, l2, version
		elif command == 1:
			yield 'ExpectComment', pos, pos + l2
			pos += l2
		elif command == 2:
			yield 'ExpectRead', pos, pos + l2
			pos += l2
		elif command == 3:
			yield 'ExpectWrite', pos, pos + l2
			pos += l2
		elif command == 4:
			yield 'Usleep', l1
		else:
			raise ValueError('unsupported command %d' % command)

def extract_bulk_read(source, headers, length):
	while length > 0:
		start, end = expect(headers.__next__(), 'ExpectRead')
		yield start, end
		length -= end - start

def extract_bulk_write(source, headers, length):
	while length > 0:
		start, end = expect(headers.__next__(), 'ExpectWrite')
		yield start, end
		length -= end - start

def parse_awusb(source, headers):
	while True:
		# request
		start, end = expect(headers.__next__(), 'ExpectWrite')
		length, request = struct.unpack_from('<xxxxxxxxIxxxxHxxxxxxxxxxxxxx', source, start)
		# payload
		if request == 0x11:
			# print('    awusb_read') # %%%
			yield 'read', extract_bulk_read(source, headers, length)
		elif request == 0x12:
			# print('    awusb_write') # %%%
			yield 'write', extract_bulk_write(source, headers, length)
		else:
			raise ValueError('unsupported USB request %d' % request)
		# response
		expect(headers.__next__(), 'ExpectRead')

def parse_fel(source, headers):
	awusb = parse_awusb(source, headers)
	while True:
		# request
		chunks, = expect(awusb.__next__(), 'write')
		start, end = get_singular(chunks)
		request, address, length = struct.unpack_from('<IIIxxxx', source, start)
		# payload
		if request == 0x1:
			# print('  fel_ver') # %%%
			chunks, = expect(awusb.__next__(), 'read')
			start, end = get_singular(chunks)
			soc_id, protocol, scratchpad = struct.unpack_from('<xxxxxxxxIxxxxHxxIxxxxxxxx', source, start)
			yield 'ver', soc_id, protocol, scratchpad
		elif request == 0x101:
			# print('  fel_write') # %%%
			chunks, = expect(awusb.__next__(), 'write')
			yield 'write', address, length, chunks
		elif request == 0x102:
			# print('  fel_exe') # %%%
			yield 'exe', address
		elif request == 0x103:
			# print('  fel_read') # %%%
			chunks, = expect(awusb.__next__(), 'read')
			yield 'read', address, length, chunks
		else:
			raise ValueError('unsupported FEL request %d' % request)
		# response
		chunks, = expect(awusb.__next__(), 'read')
		discard(chunks)

# keep this up to date with fel.c. thunk addr and chunks are about to change.
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
			discard(operation[3])
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
			else:
				discard(operation[3])

def extract_fel_write(source, headers):
	fel = parse_fel(source, headers)
	address, length, chunks = expect(fel.__next__(), 'write')
	yield from chunks

def extract_fastboot_flash(source, headers):
	for header in headers:
		start, end = expect(header, 'ExpectWrite')
		fb_command = source[start:end]
		print('fastboot', fb_command) # %%%
		m = re.match(rb'download:(.{8})', fb_command)
		if m is not None:
			expect(headers.__next__(), 'ExpectRead')
			length = int(m.group(1), 16)
			yield from extract_bulk_write(source, headers, length)
		expect(headers.__next__(), 'ExpectRead')

def extract_files(source):
	headers = parse_headers(source)
	expect(headers.__next__(), 'MAGIC')
	for header in headers:
		start, end = expect(header, 'ExpectComment')
		def generate_io_headers():
			for header in headers:
				# print('      io_header', header) # %%%
				if header[0] == 'MAGIC':
					break
				yield header
		io_headers = generate_io_headers()
		comment = source[start:end]
		words = comment.split(b', ')
		print('comment %r' % words) # %%%
		if words[0] == b'fel':
			if words[1] == b'spl':
				yield words[2].decode('ascii'), extract_fel_spl(source, io_headers)
			elif words[1] == b'write':
				yield words[3].decode('ascii'), extract_fel_write(source, io_headers)
		elif words[0] == b'fastboot':
			pos = 1
			while pos < len(words):
				if words[pos] == b'-i':
					pos += 2
				elif words[pos] == b'-u':
					pos += 1
				elif words[pos] == b'devices':
					break
				elif words[pos] == b'flash':
					yield words[pos + 2].decode('ascii'), extract_fastboot_flash(source, io_headers)
					break
				elif words[pos] == b'continue':
					break
				else:
					raise ValueError('unsupported fastboot command %s' % comment)
		discard(io_headers)

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
if False:
	print_files(chp, files)
else:
	save_files(chp, files)
