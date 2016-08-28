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

prebuilt: img-$(FLAVOR)-fb.tar.gz
	mkdir $@
	tar -xvf $< --strip-components=2 -C $@ \
		img-$(FLAVOR)-fb/images/sunxi-spl.bin \
		img-$(FLAVOR)-fb/images/u-boot-dtb.bin

img-$(FLAVOR)-fb.tar.gz:
	wget "$(DL_URL)/$(BRANCH)/$(FLAVOR)/$(CACHENUM)/$@"

print-latest:
	curl "$(DL_URL)/$(BRANCH)/$(FLAVOR)/latest"

headless44.chp:
	wget "https://s3-us-west-2.amazonaws.com/getchip.com/extension/$@"

flashImages:
	wget "http://flash.getchip.com/$@"

repo/Release repo/Release.gpg:
	cd $(@D) && wget "http://opensource.nextthing.co/chip/debian/repo/dists/jessie/$(@F)"

repo/Packages:
	cd $(@D) && wget "http://opensource.nextthing.co/chip/debian/repo/dists/jessie/main/binary-armhf/$(@F)"

# also update boot-rescue script
RK_VERSION := 4.4.11-ntc
RK_REV_ARCH := 4.4.11-9_armhf
BUSYBOX_VERSION := 1.24.2-r11

# this depends on tmp existing from making rootfs.ubifs
do-boot-rescue: boot-rescue rescue-kernel boot-rescue.scr rescue-rd.gz.img
	./$<

rescue-kernel: linux-image-$(RK_VERSION)_$(RK_REV_ARCH).deb
	mkdir $@
	dpkg-deb --fsys-tarfile $< | \
	tar -xv -C $@ \
		./boot/vmlinuz-$(RK_VERSION) \
		./usr/lib/linux-image-$(RK_VERSION)/sun5i-r8-chip.dtb

# should write recipes to extract files from this instead of mooching off tmp
linux-image-$(RK_VERSION)_$(RK_REV_ARCH).deb:
	wget "http://opensource.nextthing.co/chip/debian/repo/pool/main/l/linux-$(RK_VERSION)/$@"

rescue-rd.gz.img: rescue-rd.gz
	mkimage -A arm -T ramdisk -n "rescue ramdisk" -d $< $@

rescue-rd.gz: rescue/init rescue/bin/sh rescue/bin/busybox rescue/dev rescue/proc rescue/sys rescue/mnt
	cd rescue && find . | cpio -ov -R 0:0 -H newc | gzip > ../$@

rescue/bin/sh: rescue/bin/busybox
	ln -s busybox $@

rescue/bin/busybox: busybox-static-$(BUSYBOX_VERSION).apk
	tar -xzvf $< -C rescue bin/busybox.static
	mv rescue/bin/busybox.static $@
	# reset modification time so we don't have to remake it
	touch $@

busybox-static-$(BUSYBOX_VERSION).apk:
	wget "http://dl-cdn.alpinelinux.org/alpine/latest-stable/main/armhf/$@"

rescue/dev rescue/proc rescue/sys rescue/mnt:
	mkdir $@

boot-rescue.scr: boot-rescue.cmd
	mkimage -A arm -T script -C none -n "boot to rescue ramdisk" -d $< $@

.PHONY: migrate-db enter-fakeroot print-latest do-boot-rescue
.INTERMEDIATE: rootfs.ubi rootfs.ubifs img-$(FLAVOR)-fb.tar.gz linux-image-$(RK_VERSION)_$(RK_REV_ARCH).deb rescue-rd.gz busybox-static-$(BUSYBOX_VERSION).apk
