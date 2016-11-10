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
end = -1

os.ftruncate(4, 0)
os.ftruncate(4, image_sz)
dst = mmap.mmap(4, image_sz, prot=mmap.PROT_WRITE)

def check_ec_hdr(i, ec_base):
	ec_magic, image_seq = struct.unpack_from('>Ix3x8x4x4xI32x4x', src, ec_base)
	if ec_magic != UBI_EC_HDR_MAGIC:
		print('peb %d wrong magic 0x%08X' % (i, ec_magic))
		return False
	if image_seq != the_image_seq:
		print('peb %d other image_seq 0x%08X' % (i, image_seq))
		return False
	return True

def check_vid_hdr(i, j, vid_base):
	vid_magic, vol_id, lnum, sqnum = struct.unpack_from('>IxxxxII4x4x4x4x4x4xQ12x4x', src, vid_base)
	if vid_magic != UBI_VID_HDR_MAGIC:
		print('peb %d leb %d wrong magic 0x%08X' % (i, j, vid_magic))
		return None
	if vol_id != the_vol_id:
		print('peb %d leb %d other vol_id 0x%08X' % (i, j, vol_id))
		return None
	if lnum in seen:
		if sqnum > seen[lnum]:
			print('peb %d leb %d overwrites lnum %d sqnum %d -> %d' % (i, j, lnum, seen[lnum], sqnum))
		else:
			print('peb %d leb %d ignored lnum %d sqnum %d xx %d' % (i, j, lnum, seen[lnum], sqnum))
			return None
	else:
		print('peb %d leb %d writes lnum %d sqnum %d' % (i, j, lnum, sqnum))
	seen[lnum] = sqnum
	global end
	if lnum > end:
		end = lnum
	return lnum

for i in range(peb_cnt):
	peb_base = i * PEB_SIZE
	if not check_ec_hdr(i, peb_base):
		continue
	vid_base = peb_base + MIN_IO_SIZE
	upper_vid_magic, = struct.unpack_from('>I', src, vid_base + UBI_VID_HDR_SIZE)
	if upper_vid_magic == 0x00000000 or upper_vid_magic == 0xffffffff:
		lnum = check_vid_hdr(i, 9, vid_base)
		if lnum is not None:
			# 0-1 3 5
			#  / / /
			# 2 4 6-7
			for dp, sp in enumerate(range(3, PEB_SIZE // MIN_IO_SIZE - 2, 2)):
				page_base = peb_base + sp * MIN_IO_SIZE
				dst[lnum * LEB_SIZE + dp * MIN_IO_SIZE:lnum * LEB_SIZE + dp * MIN_IO_SIZE + MIN_IO_SIZE] = src[page_base:page_base + MIN_IO_SIZE]
	else:
		for j in range(2):
			lnum = check_vid_hdr(i, j, vid_base + j * UBI_VID_HDR_SIZE)
			if lnum is not None:
				leb_base = peb_base + 2 * MIN_IO_SIZE + j * LEB_SIZE
				dst[lnum * LEB_SIZE:lnum * LEB_SIZE + LEB_SIZE] = src[leb_base:leb_base + LEB_SIZE]
# todo: missed blocks should be filled with ff

dst.close()
src.close()

os.ftruncate(4, (end + 1) * LEB_SIZE)
