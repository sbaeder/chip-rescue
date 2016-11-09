#!/usr/bin/python3
import mmap
import os
import struct

UBI_EC_HDR_SIZE = 64
UBI_VID_HDR_SIZE = 64
UBI_EC_HDR_MAGIC = 0x55424923
UBI_VID_HDR_MAGIC = 0x55424921

PEB_SIZE = 0x400000
LEB_SIZE = 0x1f8000
MIN_IO_SIZE = 0x4000

src = mmap.mmap(3, 0, prot=mmap.PROT_READ)

peb_cnt = len(src) // PEB_SIZE
leb_cnt = 2 * peb_cnt
image_sz = leb_cnt * LEB_SIZE

the_image_seq, = struct.unpack_from('>4xx3x8x4x4xI32x4x', src, 0)
the_vol_id = 0

print('extracting image_seq 0x%08X, vol_id %d' % (the_image_seq, the_vol_id))

seen = {}

os.ftruncate(4, 0)
os.ftruncate(4, image_sz)
dst = mmap.mmap(4, image_sz, prot=mmap.PROT_WRITE)

for i in range(peb_cnt):
	peb_base = i * PEB_SIZE
	ec_base = peb_base
	ec_magic, image_seq = struct.unpack_from('>Ix3x8x4x4xI32x4x', src, ec_base)
	if ec_magic != UBI_EC_HDR_MAGIC:
		print('peb %d wrong magic 0x%08X' % (i, ec_magic))
		continue
	if image_seq != the_image_seq:
		print('peb %d other image_seq 0x%08X' % (i, image_seq))
		continue
	for j in range(2):
		vid_base = peb_base + MIN_IO_SIZE + j * UBI_VID_HDR_SIZE
		vid_magic, vol_id, lnum, sqnum = struct.unpack_from('>IxxxxII4x4x4x4x4x4xQ12x4x', src, vid_base)
		if vid_magic != UBI_VID_HDR_MAGIC:
			print('peb %d leb %d wrong magic 0x%08X' % (i, j, vid_magic))
			continue
		if vol_id != the_vol_id:
			print('peb %d leb %d other vol_id 0x%08X' % (i, j, vol_id))
			continue
		if lnum in seen:
			if sqnum > seen[lnum]:
				print('peb %d leb %d overwrites lnum %d sqnum %d -> %d' % (i, j, lnum, seen[lnum], sqnum))
				seen[lnum] = sqnum
			else:
				print('peb %d leb %d ignored lnum %d sqnum %d xx %d' % (i, j, lnum, seen[lnum], sqnum))
				continue
		leb_base = peb_base + 2 * MIN_IO_SIZE + j * LEB_SIZE
		dst[lnum * LEB_SIZE:lnum * LEB_SIZE + LEB_SIZE] = src[leb_base:leb_base + LEB_SIZE]
