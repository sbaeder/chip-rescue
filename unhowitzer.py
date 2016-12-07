#!/usr/bin/python3
import base64
import collections
import hashlib
import mmap
import os
import re
import struct
import sys

def format_snippet(snippet):
	h = re.sub(rb'..', b'\g<0> ', base64.b16encode(snippet))
	a = re.sub(rb'[\x00-\x1f\x7f-\xff]', b'.', snippet)
	return '%-96s %s' % (h.decode('ascii'), a.decode('ascii'))

def expect(i, t):
	v = next(i)
	assert type(v) is t, v
	return v

def expect_end(i):
	try:
		v = next(i)
		raise AssertionError(v)
	except StopIteration:
		pass

def discard(i):
	for v in i:
		pass

HeaderMagic = collections.namedtuple('HeaderMagic', ['l1', 'l2', 'version'])
HeaderExpectComment = collections.namedtuple('HeaderExpectComment', ['start', 'end'])
HeaderExpectRead = collections.namedtuple('HeaderExpectRead', ['start', 'end'])
HeaderExpectWrite = collections.namedtuple('HeaderExpectWrite', ['start', 'end'])
HeaderUsleep = collections.namedtuple('HeaderUsleep', ['duration'])
HeaderExpectManifest = collections.namedtuple('HeaderExpectManifest', ['start', 'end'])

def parse_headers(source):
	pos = 0
	while pos < len(source):
		l1, command, compressed, version, l2 = struct.unpack_from('<IBBBxI', source, pos)
		pos += 12
		assert version <= 2
		assert compressed == 0
		if command == 0:
			yield HeaderMagic(l1, l2, version)
		elif command == 1:
			yield HeaderExpectComment(pos, pos + l2)
			pos += l2
		elif command == 2:
			yield HeaderExpectRead(pos, pos + l2)
			pos += l2
		elif command == 3:
			yield HeaderExpectWrite(pos, pos + l2)
			pos += l2
		elif command == 4:
			yield HeaderUsleep(l1)
		elif command == 5:
			yield HeaderExpectManifest(pos, pos + l2)
			pos += l2
		else:
			raise ValueError('unsupported command %d' % command)

def extract_bulk_read(source, headers, length):
	while length > 0:
		header = expect(headers, HeaderExpectRead)
		yield header
		length -= header.end - header.start

def extract_bulk_write(source, headers, length):
	while length > 0:
		header = expect(headers, HeaderExpectWrite)
		yield header
		length -= header.end - header.start

AWUSBRead = collections.namedtuple('AWUSBRead', ['chunks'])
AWUSBWrite = collections.namedtuple('AWUSBWrite', ['chunks'])

def parse_awusb(source, headers):
	while True:
		header = next(headers)
		if type(header) is HeaderUsleep:
			pass
		elif type(header) is HeaderExpectWrite:
			# request
			length, request = struct.unpack_from('<xxxxxxxxIxxxxHxxxxxxxxxxxxxx', source, header.start)
			# payload
			if request == 0x11:
				# print('    awusb_read') # %%%
				yield AWUSBRead(extract_bulk_read(source, headers, length))
			elif request == 0x12:
				# print('    awusb_write') # %%%
				yield AWUSBWrite(extract_bulk_write(source, headers, length))
			else:
				raise ValueError('unsupported USB request %d' % request)
			# response
			expect(headers, HeaderExpectRead)
		else:
			raise ValueError('unexpected header %s' % (header,))

def fel_locate_struct(awusb, t):
	operation = expect(awusb, t)
	chunk = next(operation.chunks)
	expect_end(operation.chunks)
	return chunk.start

FELVer = collections.namedtuple('FELVer', ['soc_id', 'protocol', 'scratchpad'])
FELWrite = collections.namedtuple('FELWrite', ['address', 'length', 'chunks'])
FELExe = collections.namedtuple('FELExe', ['address'])
FELRead = collections.namedtuple('FELRead', ['address', 'length', 'chunks'])

def parse_fel(source, headers):
	awusb = parse_awusb(source, headers)
	while True:
		# request
		request, address, length = struct.unpack_from('<IIIxxxx', source, fel_locate_struct(awusb, AWUSBWrite))
		# payload
		if request == 0x1:
			# print('  fel_ver') # %%%
			soc_id, protocol, scratchpad = struct.unpack_from('<xxxxxxxxIxxxxHxxIxxxxxxxx', source, fel_locate_struct(awusb, AWUSBRead))
			yield FELVer(soc_id, protocol, scratchpad)
		elif request == 0x101:
			# print('  fel_write') # %%%
			yield FELWrite(address, length, expect(awusb, AWUSBWrite).chunks)
		elif request == 0x102:
			# print('  fel_exe') # %%%
			yield FELExe(address)
		elif request == 0x103:
			# print('  fel_read') # %%%
			yield FELRead(address, length, expect(awusb, AWUSBRead).chunks)
		else:
			raise ValueError('unsupported FEL request %d' % request)
		# response
		discard(expect(awusb, AWUSBRead).chunks)

File = collections.namedtuple('File', ['name', 'chunks'])

def access_chunks(source, i):
	for header in i:
		# print('    accessing', header) # %%%
		yield source[header.start:header.end]

# keep this up to date with fel.c.
SPL_SOC_ID = 0x00162500
SPL_THUNK_ADDR = 0xA200
SPL_CHUNKS = [
	(0x0000, 0x1C00),
	(0xA400, 0x0400),
	(0x2000, 0x3C00),
	(0xA800, 0x1400),
	(0x7000, 0x0C00),
	(0xBC00, 0x0400)
]

def extract_fel_spl(source, headers):
	spl_chunk_index = 0
	fel = parse_fel(source, headers)
	for operation in fel:
		# print(' ', operation) # %%%
		if type(operation) is FELVer:
			assert operation.soc_id == SPL_SOC_ID
		elif type(operation) is FELRead:
			discard(operation.chunks)
		elif type(operation) is FELExe:
			if operation.address == SPL_THUNK_ADDR:
				spl_chunk_index = len(SPL_CHUNKS)
		elif type(operation) is FELWrite:
			if spl_chunk_index < len(SPL_CHUNKS):
				address, capacity = SPL_CHUNKS[spl_chunk_index]
				if operation.address == address:
					yield from access_chunks(source, operation.chunks)
					spl_chunk_index += 1
				else:
					discard(operation.chunks)
			else:
				discard(operation.chunks)

def extract_fel_write(source, headers):
	fel = parse_fel(source, headers)
	operation = expect(fel, FELWrite)
	# print(' ', operation) # %%%
	yield from access_chunks(source, operation.chunks)
	for operation in fel:
		# print(' ', operation) # %%%
		if type(operation) is FELRead:
			discard(operation.chunks)
		elif type(operation) is FELWrite:
			discard(operation.chunks)

def extract_fastboot_flash(source, headers):
	while True:
		header = expect(headers, HeaderExpectWrite)
		fb_command = source[header.start:header.end]
		# print('  fastboot', fb_command) # %%%
		m = re.match(rb'download:(.{8})', fb_command)
		if m is not None:
			expect(headers, HeaderExpectRead)
			length = int(m.group(1), 16)
			yield from access_chunks(source, extract_bulk_write(source, headers, length))
		expect(headers, HeaderExpectRead)

def ignore(io_headers):
	discard(io_headers)
	return None

def handle_fel(source, words, io_headers):
	if words[1] == b'spl':
		return File(words[2], extract_fel_spl(source, io_headers))
	elif words[1] == b'write':
		return File(words[3], extract_fel_write(source, io_headers))
	return ignore(io_headers)

def handle_fastboot(source, words, io_headers):
	pos = 1
	positional = []
	while pos < len(words):
		if words[pos] == b'-i':
			pos += 2
		elif words[pos] == b'-u':
			pos += 1
		else:
			positional.append(words[pos])
			pos += 1
	if positional[0] == b'flash':
		return File(positional[2], extract_fastboot_flash(source, io_headers))
	return ignore(io_headers)

def handle(source, magic, comment, io_headers):
	# print(magic) # %%%
	if comment is None:
		return ignore(io_headers)
	comment_bytes = source[comment.start:comment.end]
	# print(comment_bytes.decode('ascii')) # %%%
	words = comment_bytes.split(b', ')
	if words[0] == b'fel' or words[0] == b'sunxi-fel':
		return handle_fel(source, words, io_headers)
	elif words[0] == b'fastboot' or words[0] == b'/usr/local/bin/fastboot':
		return handle_fastboot(source, words, io_headers)
	return ignore(io_headers)

def extract_files(source):
	start_item = object()
	end_item = object()
	def transduce(raw):
		in_magic = False
		check_comment = False
		for header in raw:
			if check_comment:
				if type(header) is not HeaderExpectComment:
					yield None
				check_comment = False
			if type(header) is HeaderMagic:
				if in_magic:
					yield end_item
				yield start_item
				in_magic = True
				check_comment = True
			yield header
	i = transduce(parse_headers(source))
	for v in i:
		assert v is start_item
		magic = expect(i, HeaderMagic)
		comment = next(i)
		def generate_io_headers():
			for v in i:
				if v is end_item:
					break
				yield v
		file = handle(source, magic, comment, generate_io_headers())
		if file is not None:
			yield file

def print_files(files):
	for file in files:
		size = 0
		md5 = hashlib.md5()
		for chunk in file.chunks:
			size += len(chunk)
			md5.update(chunk)
		print('%s\t%9d\t%s' % (md5.hexdigest(), size, file.name.decode('ascii')))

def save_files(files):
	for i, file in enumerate(files):
		output_name = '%02d-%s' % (i + 1, os.path.basename(file.name).decode('ascii'))
		with open(output_name, 'wb') as f:
			for chunk in file.chunks:
				f.write(chunk)

chp = mmap.mmap(3, 0, prot=mmap.PROT_READ)
files = extract_files(chp)
if len(sys.argv) >= 2 and sys.argv[1] == '-l':
	print_files(files)
else:
	save_files(files)
