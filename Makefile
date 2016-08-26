DL_URL := http://opensource.nextthing.co/chip/images
FLAVOR := serv
BRANCH := stable
CACHENUM := 1

do-flash: flash prebuilt enter-fastboot.scr rootfs.ubi.sparse
	./flash

rootfs.ubi.sparse: rootfs.ubi
	img2simg $< $@ 2097152

rootfs.ubi: rootfs.ubifs ubinize.cfg
	ubinize -o $@ -p 0x200000 -m 0x4000 ubinize.cfg

rootfs.ubifs: multistrap.conf init.template
	fakeroot -s rootfs.db ./buildrootfs

enter-fakeroot:
	fakeroot -i rootfs.db -s rootfs.db

do-update-init:
	fakeroot -i rootfs.db -s rootfs.db ./update-init
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

.PHONY: print-latest enter-fakeroot
