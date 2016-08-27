DL_URL := http://opensource.nextthing.co/chip/images
FLAVOR := serv
BRANCH := stable
CACHENUM := 1

do-flash: flash prebuilt enter-fastboot.scr rootfs.ubi.sparse
	./$<

rootfs.ubi.sparse: rootfs.ubi
	img2simg $< $@ 2097152

rootfs.ubi: rootfs.ubifs ubinize.cfg
	ubinize -o $@ -p 0x200000 -m 0x4000 ubinize.cfg

rootfs.ubifs: multistrap.conf init.template
	fakeroot -s rootfs.db ./buildrootfs

migrate-db:
	sed -i "s/dev=[^,]+/$$(stat -c %D tmp)/" rootfs.db

enter-fakeroot:
	fakeroot -i rootfs.db -s rootfs.db

do-update-init: update-init
	fakeroot -i rootfs.db -s rootfs.db ./$<
	make rootfs.ubi.sparse

enter-fastboot.scr: enter-fastboot.cmd
	mkimage -A arm -T script -C none -n "enter fastboot" -d $< $@

prebuilt:
	mkdir $@
	curl "$(DL_URL)/$(BRANCH)/$(FLAVOR)/$(CACHENUM)/img-$(FLAVOR)-fb.tar.gz" | \
	tee $@/img-$(FLAVOR)-fb.tar.gz | \
	tar -xzv --strip-components=2 -C $@ \
		img-$(FLAVOR)-fb/images/sunxi-spl.bin \
		img-$(FLAVOR)-fb/images/u-boot-dtb.bin

print-latest:
	curl "$(DL_URL)/$(BRANCH)/$(FLAVOR)/latest"

# this depends on tmp existing from making rootfs.ubifs
do-boot-rescue: boot-rescue boot-rescue.scr rescue-rd.gz.img
	./$<

# should write recipes to extract files from this instead of mooching off tmp
linux-image-4.4.11-ntc_4.4.11-9_armhf.deb:
	wget "http://opensource.nextthing.co/chip/debian/repo/pool/main/l/linux-4.4.11-ntc/linux-image-4.4.11-ntc_4.4.11-9_armhf.deb"

rescue-rd.gz.img: rescue-rd.gz
	mkimage -A arm -T ramdisk -n "rescue ramdisk" -d $< $@

rescue-rd.gz: rescue/init rescue/bin/sh rescue/bin/busybox
	cd rescue && find . -not -type d | cpio -ov --owner root:root | gzip > ../$@

rescue/bin/sh: rescue/bin/busybox
	ln -s busybox $@

rescue/bin/busybox: busybox-static-1.24.2-r11.apk
	tar -xzvf $< -C rescue bin/busybox.static
	mv rescue/bin/busybox.static $@
	# reset modification time so we don't have to remake it
	touch $@

busybox-static-1.24.2-r11.apk:
	wget "http://dl-cdn.alpinelinux.org/alpine/latest-stable/main/armhf/$@"

boot-rescue.scr: boot-rescue.cmd
	mkimage -A arm -T script -C none -n "boot to rescue ramdisk" -d $< $@

.PHONY: migrate-db enter-fakeroot print-latest do-boot-rescue
