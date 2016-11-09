#!/usr/bin/python3
for b in blocks:
	ec_magic, image_seq = struct.unpack_from('<Ix3x8x4x4xI32x4x', b, 0x0000)
	assert ec_magic == X
	assert image_seq == T
	for i in range(2):
		vid_magic, vol_id, lnum = struct.unpack_from('<IxxxxII4x4x4x4x4x4x8x12x4x', b, 0x4000 + 0x40 * i)
		assert vid_magic == Y
		assert vol_id == U
		emit(b, 0x8000 + data_len * i, data_len)
