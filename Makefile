release: flash.tar.gz rootfs.ubi.sparse modules.tar.gz rescue.tar.gz

DL_URL := http://opensource.nextthing.co/chip/images
FLAVOR := server
BRANCH := stable
CACHENUM := 149
UBI_TYPE := 400000-4000-680

do-flash: flash prebuilt/sunxi-spl.bin prebuilt/u-boot-dtb.bin enter-fastboot.scr rootfs.ubi.sparse
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

# also update boot-rescue script
KERNEL_VERSION := 4.4.13-ntc-mlc
KERNEL_REV_ARCH := 4.4.13-58_armhf

modules.tar.gz: CHIP-linux-debian-$(KERNEL_VERSION)/drivers/md/dm-crypt.ko
	tar -czvf $@ --owner=root --group=root -C CHIP-linux-debian-$(KERNEL_VERSION) \
		drivers/md/dm-crypt.ko

CHIP-linux-debian-$(KERNEL_VERSION)/drivers/md/dm-crypt.ko: | CHIP-linux-debian-$(KERNEL_VERSION)
	make -C CHIP-linux-debian-$(KERNEL_VERSION) ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- LOCALVERSION=-ntc-mlc KCFLAGS=-fno-pie drivers/md/dm-crypt.ko

CHIP-linux-debian-$(KERNEL_VERSION): $(KERNEL_VERSION).tar.gz linux-image/boot/config-$(KERNEL_VERSION)
	tar -xf $<
	cp linux-image/boot/config-$(KERNEL_VERSION) $@/.config
	echo CONFIG_DM_CRYPT=m >>$@/.config
	make -C CHIP-linux-debian-$(KERNEL_VERSION) ARCH=arm olddefconfig
	make -C CHIP-linux-debian-$(KERNEL_VERSION) ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- prepare

$(KERNEL_VERSION).tar.gz:
	wget $(WGET_OPTS) "https://github.com/NextThingCo/CHIP-linux/archive/debian/$@"

linux-image/boot/vmlinuz-% linux-image/usr/lib/linux-image-%/sun5i-r8-chip.dtb linux-image/boot/config-%: linux-image-%_$(KERNEL_REV_ARCH).deb
	mkdir linux-image
	dpkg-deb --fsys-tarfile $< | \
	tar -xv -C linux-image \
		./boot/vmlinuz-$* \
		./usr/lib/linux-image-$*/sun5i-r8-chip.dtb \
		./boot/config-$*

linux-image-$(KERNEL_VERSION)_$(KERNEL_REV_ARCH).deb:
	wget $(WGET_OPTS) "http://opensource.nextthing.co/chip/debian/repo/pool/main/l/linux-$(KERNEL_VERSION)/$@"

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

prebuilt/pocket-pieces: prebuilt/pocket44_01.chp unhowitzer.py
	mkdir $@
	cd $@ && ../../unhowitzer.py 3<../$(<F)

prebuilt/pocket.ubi: prebuilt/pocket-pieces densify.py
	./densify.py 3<$</11-rootfs.ubi.sparse 4<>$@

prebuilt/pocket.ubifs: prebuilt/pocket.ubi unubinize.py
	./unubinize.py 3<$< 4<>$@

prebuilt/pocket-root: prebuilt/pocket.ubifs | ubi_reader
	PYTHONPATH=./ubi_reader ./ubi_reader/scripts/ubireader_extract_files -o $@ $<

prebuilt/pocket44_01.squashfs: prebuilt/pocket-root
	mksquashfs $< $@

prebuilt/server.ubi: prebuilt/chip-$(UBI_TYPE).ubi.sparse
	simg2img $< $@

prebuilt/server.ubifs: prebuilt/server.ubi unubinize.py
	./unubinize.py 3<$< 4<>$@

prebuilt/server-root: prebuilt/server.ubifs | ubi_reader
	PYTHONPATH=./ubi_reader ./ubi_reader/scripts/ubireader_extract_files -o $@ $<

prebuilt/server.squashfs: prebuilt/server-root
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

repo/InRelease: | repo
	cd $(@D) && wget $(WGET_OPTS) "http://opensource.nextthing.co/chip/debian/repo/dists/jessie/$(@F)"

repo/Packages: | repo
	cd $(@D) && wget $(WGET_OPTS) "http://opensource.nextthing.co/chip/debian/repo/dists/jessie/main/binary-armhf/$(@F)"

# https://pkgs.alpinelinux.org/packages?name=busybox-static&arch=armhf
BUSYBOX_VERSION := 1.25.1-r0

# this depends on tmp existing from making rootfs.ubifs
do-boot-rescue: boot-rescue prebuilt/sunxi-spl.bin prebuilt/u-boot-dtb.bin linux-image/boot/vmlinuz-$(KERNEL_VERSION) linux-image/usr/lib/linux-image-$(KERNEL_VERSION)/sun5i-r8-chip.dtb boot-rescue.scr rescue-rd.gz.img
	./$<

rescue.tar.gz: boot-rescue prebuilt/sunxi-spl.bin prebuilt/u-boot-dtb.bin linux-image/boot/vmlinuz-$(KERNEL_VERSION) linux-image/usr/lib/linux-image-$(KERNEL_VERSION)/sun5i-r8-chip.dtb boot-rescue.scr rescue-rd.gz.img
	tar -czvf $@ $+

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
.INTERMEDIATE: rootfs.ubi rootfs.ubifs
.INTERMEDIATE: linux-image-$(KERNEL_VERSION)_$(KERNEL_REV_ARCH).deb
.INTERMEDIATE: rescue-rd.gz.img rescue-rd.gz busybox-static-$(BUSYBOX_VERSION).apk
.INTERMEDIATE: prebuilt/pocket44_01.chp prebuilt/pocket.ubi prebuilt/pocket.ubifs
.INTERMEDIATE: prebuilt/chip-$(UBI_TYPE).ubi.sparse prebuilt/server.ubi prebuilt/server.ubifs
