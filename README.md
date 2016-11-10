# C.H.I.P. Setup
This repo actually has three things.
They're all related to [this computer](https://www.getchip.com/pages/chip).

## A root filesystem flashing tool
There's a tool for flashing just a root filesystem.
This is released as `flash.tar.gz`.
You'd unpack it, plug in your C.H.I.P. in FEL mode, and run `./flash`, which will flash the `rootfs.ubi.sparse` file to the UBI partition.
It uses the prebuilt SPL and U-Boot images from Next Thing.
The point is to avoid rewriting the SPL, SPL backup, U-Boot, and U-Boot environment partitions when we don't have anything to change.

## A Debian root filesystem
There's an experimental root filesystem with Debian on it.
This is released as `rootfs.ubi.sparse`.
You'd flash it, connect to it with a USB cable, and set it up over the serial gadget interface.
It's built with multistrap, so that it can include the kernel and drivers from Next Thing's repository, but which also comes with its own problems.
The point is to have a customizable flashable image, so you can have a convenient starting point if your storage ever gets corrupted.

## A rescue tool
There's a tool for accessing the root filesystem when you can't boot normally or log in or something.
This is released as `rescue.tar.gz`.
You'd unpack it, plug in your C.H.I.P. in FEL mode, and run `./boot-rescue`, which boots into a ramdisk with BusyBox.
Connect to the serial gadget interface for a root shell with the root filesystem in `/mnt`.
It uses the prebuilt SPL, U-Boot, and Linux images from Next Thing, as well as a statically linked BusyBox binary from Alpine.
The point is to have some way to inspect and modify your root filesystem entirely using code uploaded over FEL.
