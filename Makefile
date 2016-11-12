release: flash.tar.gz rootfs.ubi.sparse rescue.tar.gz prebuilt/pocket44_01.squashfs

DL_URL := http://opensource.nextthing.co/chip/images
FLAVOR := server
BRANCH := stable
CACHENUM := 129
UBI_TYPE := 400000-4000

do-flash: flash prebuilt enter-fastboot.scr rootfs.ubi.sparse
	./$<

flash.tar.gz: flash prebuilt/sunxi-spl.bin prebuilt/u-boot-dtb.bin enter-fastboot.scr
	tar -czvf $@ $+

rootfs.ubi.sparse: rootfs.ubi
	img2simg $< $@ 4194304

rootfs.ubi: CHIP-mtd-utils/ubi-utils/ubinize rootfs.ubifs ubinize.cfg
	./$< -o $@ -p 0x400000 -m 0x4000 -M dist3 ubinize.cfg

rootfs.ubifs: buildrootfs multistrap.conf init.template
	fakeroot -s rootfs.db ./$<

migrate-db:
	sed -i "s/dev=[^,]+/$$(stat -c %D tmp)/" rootfs.db

enter-fakeroot:
	fakeroot -i rootfs.db -s rootfs.db

do-update-init: update-init
	fakeroot -i rootfs.db -s rootfs.db ./$<
	make rootfs.ubi.sparse

enter-fastboot.scr: enter-fastboot.cmd
	mkimage -A arm -T script -C none -n "enter fastboot" -d $< $@

print-latest:
	curl "$(DL_URL)/$(BRANCH)/$(FLAVOR)/latest"

prebuilt:
	mkdir $@

prebuilt/sunxi-spl.bin prebuilt/u-boot-dtb.bin prebuilt/chip-$(UBI_TYPE).ubi.sparse: | prebuilt
	cd $(@D) && wget $(WGET_OPTS) "$(DL_URL)/$(BRANCH)/$(FLAVOR)/$(CACHENUM)/$(@F)"

prebuilt/headless44.chp prebuilt/pocket44_01.chp: | prebuilt
	cd $(@D) && wget $(WGET_OPTS) "https://s3-us-west-2.amazonaws.com/getchip.com/extension/$(@F)"

prebuilt/p4401.txt: prebuilt/pocket44_01.chp print-chp.py
	./print-chp.py <$< >$@

prebuilt/pieces: prebuilt/pocket44_01.chp unhowitzer.py
	mkdir $@
	cd $@ && ../../unhowitzer.py 3<../$(<F)

prebuilt/rootfs.ubi: prebuilt/pieces densify.py
	./densify.py 3<$</11-rootfs.ubi.sparse 4<>$@

prebuilt/rootfs.ubifs: prebuilt/rootfs.ubi unubinize.py
	./unubinize.py 3<$< 4<>$@

prebuilt/ubifs-root: prebuilt/rootfs.ubifs | ubi_reader
	PYTHONPATH=./ubi_reader ./ubi_reader/scripts/ubireader_extract_files -o $@ $<

prebuilt/pocket44_01.squashfs: prebuilt/ubifs-root
	mksquashfs $< $@

# https://github.com/NextThingCo/CHIP-mtd-utils/commits/by/1.5.2/next-mlc-debian
CHIP-mtd-utils:
	git clone https://github.com/NextThingCo/CHIP-mtd-utils.git
	cd $@ && git checkout f6a16e575091ef315b147532ba818877fd2c1895

CHIP-mtd-utils/ubi-utils/ubinize: | CHIP-mtd-utils
	make -C CHIP-mtd-utils $$PWD/CHIP-mtd-utils/ubi-utils/ubinize

ubi_reader:
	git clone https://github.com/jrspruitt/ubi_reader

multistrap.orig:
	cp /usr/sbin/multistrap $@

do-patch-multistrap: fix-multistrap.patch | multistrap.orig
	patch /usr/sbin/multistrap $<

prebuilt/flashImages:
	cd $(@D) && wget $(WGET_OPTS) "http://flash.getchip.com/$(@F)"

repo:
	mkdir $@

repo/Release repo/Release.gpg: | repo
	cd $(@D) && wget $(WGET_OPTS) "http://opensource.nextthing.co/chip/debian/repo/dists/jessie/$(@F)"

repo/Packages: | repo
	cd $(@D) && wget $(WGET_OPTS) "http://opensource.nextthing.co/chip/debian/repo/dists/jessie/main/binary-armhf/$(@F)"

# also update boot-rescue script
RK_VERSION := 4.4.13-ntc-mlc
RK_REV_ARCH := 4.4.13-53_armhf
BUSYBOX_VERSION := 1.24.2-r12

# this depends on tmp existing from making rootfs.ubifs
do-boot-rescue: boot-rescue prebuilt rescue-kernel boot-rescue.scr rescue-rd.gz.img
	./$<

rescue.tar.gz: boot-rescue prebuilt/sunxi-spl.bin prebuilt/u-boot-dtb.bin rescue-kernel boot-rescue.scr rescue-rd.gz.img
	tar -czvf $@ $+

rescue-kernel: linux-image-$(RK_VERSION)_$(RK_REV_ARCH).deb
	mkdir $@
	dpkg-deb --fsys-tarfile $< | \
	tar -xv -C $@ \
		./boot/vmlinuz-$(RK_VERSION) \
		./usr/lib/linux-image-$(RK_VERSION)/sun5i-r8-chip.dtb

linux-image-$(RK_VERSION)_$(RK_REV_ARCH).deb:
	wget $(WGET_OPTS) "http://opensource.nextthing.co/chip/debian/repo/pool/main/l/linux-$(RK_VERSION)/$@"

rescue-rd.gz.img: rescue-rd.gz
	mkimage -A arm -T ramdisk -n "rescue ramdisk" -d $< $@

rescue-rd.gz: rescue/init rescue/etc/inittab rescue/bin/sh rescue/bin/busybox rescue/dev rescue/proc rescue/sys rescue/mnt
	cd rescue && find . | cpio -ov -R 0:0 -H newc | gzip > ../$@

rescue/bin/sh: rescue/bin/busybox
	ln -s busybox $@

rescue/bin/busybox: busybox-static-$(BUSYBOX_VERSION).apk
	tar -xzvf $< -C rescue bin/busybox.static
	mv rescue/bin/busybox.static $@
	# reset modification time so we don't have to remake it
	touch $@

busybox-static-$(BUSYBOX_VERSION).apk:
	wget $(WGET_OPTS) "http://dl-cdn.alpinelinux.org/alpine/latest-stable/main/armhf/$@"

rescue/dev rescue/proc rescue/sys rescue/mnt:
	mkdir $@

boot-rescue.scr: boot-rescue.cmd
	mkimage -A arm -T script -C none -n "boot to rescue ramdisk" -d $< $@

.PHONY: release do-flash migrate-db enter-fakeroot print-latest do-patch-multistrap do-boot-rescue
.INTERMEDIATE: rootfs.ubi rootfs.ubifs linux-image-$(RK_VERSION)_$(RK_REV_ARCH).deb rescue-rd.gz busybox-static-$(BUSYBOX_VERSION).apk
.INTERMEDIATE: prebuilt/pocket44_01.chp prebuilt/pieces prebuilt/rootfs.ubi prebuilt/rootfs.ubifs prebuilt/ubifs-root
