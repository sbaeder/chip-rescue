#!/usr/bin/python3
import mmap
import os
import struct

src = mmap.mmap(3, 0, prot=mmap.PROT_READ)

SPARSE_HEADER_MAGIC = 0xed26ff3a

CHUNK_TYPE_RAW = 0xCAC1
CHUNK_TYPE_FILL = 0xCAC2
CHUNK_TYPE_DONT_CARE = 0xCAC3
CHUNK_TYPE_CRC32 = 0xCAC4

in_pos = 0

def read_file_header():
	global in_pos
	magic, major_version, minor_version, file_hdr_sz, chunk_hdr_sz, blk_sz, total_blks, total_chunks, image_checksum = struct.unpack_from('<IHHHHIIII', src, in_pos)
	assert magic == SPARSE_HEADER_MAGIC
	assert major_version == 1
	assert minor_version == 0
	assert file_hdr_sz == 28
	assert chunk_hdr_sz == 12
	in_pos += 28
	return blk_sz, total_blks, total_chunks

def read_chunk_header():
	global in_pos
	chunk_type, reserved1, chunk_sz, total_sz = struct.unpack_from('<HHII', src, in_pos)
	in_pos += 12
	return chunk_type, reserved1, chunk_sz, total_sz

dense_sz = 0

if in_pos < len(src):
	blk_sz, total_blks, total_chunks = read_file_header()
	dense_sz = blk_sz * total_blks
	in_pos = 0

os.ftruncate(4, 0)
os.ftruncate(4, dense_sz)
dst = mmap.mmap(4, dense_sz, prot=mmap.PROT_WRITE)

while in_pos < len(src):
	blk_sz, total_blks, total_chunks = read_file_header()
	chunk_idx = 0
	for i in range(total_chunks):
		chunk_type, reserved1, chunk_sz, total_sz = read_chunk_header()
		data_sz = total_sz - 12
		if chunk_type == CHUNK_TYPE_DONT_CARE:
			pass
		elif chunk_type == CHUNK_TYPE_RAW:
			print('0x%08x <- 0x%08x [0x%x]' % (chunk_idx * blk_sz, in_pos, data_sz))
			dst[chunk_idx * blk_sz:(chunk_idx + chunk_sz) * blk_sz] = src[in_pos:in_pos + data_sz]
		else:
			print('unsupported chunk type %d' % chunk_type)
		in_pos += data_sz
		chunk_idx += chunk_sz
